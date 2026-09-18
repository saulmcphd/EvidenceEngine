"""
screener_abstract.py - EvidenceEngine Phase 1 (Step 5a)
========================================================
AI title/abstract screener. For each record in master_records.csv it applies criteria.txt and
returns an auditable decision (include / exclude / uncertain) with a rationale and a confidence.

Design choices (see PLAN.md):
  * Provider-agnostic via LiteLLM - switch model with --model, no code change.
  * Recall-first: the prompt over-includes at the abstract stage and never excludes on a
    criterion that can't be judged from the abstract.
  * Robust JSON parsing - an unparseable response becomes "uncertain" (logged), never a crash.
  * Human-in-the-loop: writes an audit CSV in the shared reconciliation format. For a VALIDATION
    run, the human should screen BLIND first (record decisions before seeing this output).

Outputs (in --outdir, default ./Outputs):
  Abstract_Screening_<ts>.xlsx   wide results table
  Abstract_Audit_<ts>.csv        AI_Decision | Human_Decision | Match? | Error_Category | Consensus_Decision
  Screening_Log_<ts>.txt         per-record success / parse-failure log
  stage_counts.json              counts for the PRISMA diagram
  ranked_queue.csv               (only with --ranked-output) production-arm reconciliation queue, most-likely-
                                 relevant first. NEVER shown on the blind screening screen (see RANKING_NOTES.md).

Usage
-----
    # sanity-check prompt assembly WITHOUT calling any API (free):
    python screener_abstract.py --dry-run --limit 1

    # real run (needs an API key in .env for the chosen provider):
    python screener_abstract.py --model gemini/gemini-2.5-flash
    python screener_abstract.py --model claude-opus-4-8 --limit 12
    python screener_abstract.py --model gpt-4o
    python screener_abstract.py --model ollama/llama3        # local, no key

API keys are read from .env (e.g. GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY).
"""

import argparse
import concurrent.futures
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

VALID_DECISIONS = {"include", "exclude", "uncertain"}


def load_prompt_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_prompt(template: str, criteria: str, row: pd.Series) -> str:
    abstract = str(row.get("abstract", "")).strip()
    return (
        template.replace("[CRITERIA_CONTENT]", criteria.strip())
        .replace("[RECORD_ID]", str(row["record_id"]))
        .replace("[TITLE]", str(row.get("title", "")).strip())
        .replace("[ABSTRACT]", abstract if abstract else "(no abstract provided)")
        .replace("[YEAR]", str(row.get("year", "")).strip())
    )


def robust_parse(text: str, record_id: str) -> dict:
    """Parse the model's JSON defensively. Always returns a valid decision dict."""
    fallback = {
        "record_id": record_id,
        "decision": "uncertain",
        "criteria_violated": [],
        "rationale": "PARSE_FAILURE - response could not be parsed; flagged for human review.",
        "confidence": 0,
        "parse_ok": False,
    }
    if not text:
        return fallback

    candidate = text.strip()
    # strip a markdown code fence if present
    if "```" in candidate:
        m = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
        if m:
            candidate = m.group(1).strip()

    # try strict JSON, then the first {...} block
    for attempt in (candidate, _first_json_object(candidate)):
        if not attempt:
            continue
        try:
            obj = json.loads(attempt)
            decision = str(obj.get("decision", "")).strip().lower()
            if decision not in VALID_DECISIONS:
                continue
            cv = obj.get("criteria_violated", [])
            if isinstance(cv, str):
                cv = [cv] if cv else []
            conf = obj.get("confidence", 0)
            try:
                conf = int(float(conf))
            except (TypeError, ValueError):
                conf = 0
            return {
                "record_id": record_id,
                "decision": decision,
                "criteria_violated": cv,
                "rationale": str(obj.get("rationale", "")).strip(),
                "confidence": max(0, min(100, conf)),
                "parse_ok": True,
            }
        except json.JSONDecodeError:
            continue

    # last resort: regex out a decision word. Recall-first (concept-recall-first-screening): at the ABSTRACT
    # stage a broken parse must CARRY FORWARD as 'uncertain', never become a silent exclude. So only honour an
    # 'include' or 'uncertain' here; a regex-detected 'exclude' cannot carry a trustworthy criterion from a
    # response we could not fully parse, so we keep the safe 'uncertain' default and flag it (mirroring
    # screener_fulltext.py, which likewise refuses a quote-less exclude on a broken parse).
    m = re.search(r'"?decision"?\s*[:=]\s*"?(include|exclude|uncertain)', candidate, re.IGNORECASE)
    if m and m.group(1).lower() in ("include", "uncertain"):
        fallback["decision"] = m.group(1).lower()
        fallback["rationale"] = f"Partial parse (regex fallback): '{m.group(1).lower()}' detected; verify manually."
    elif m:   # appeared to exclude, but a criterion-less exclude on a broken parse would be a silent drop
        fallback["rationale"] = ("Partial parse (regex fallback): the model appeared to exclude but the response "
                                 "could not be parsed for a criterion; kept as 'uncertain' (recall-first) and flagged for review.")
    return fallback


def _first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def relevance_score(decision: str, confidence) -> float:
    """Map (decision, confidence) onto ONE likely-relevant-first 0-100 scale for the ranked queue.

    The model's `confidence` is confidence IN ITS DECISION (screening_abstract.txt rule 5) - an
    "exclude, 95" is confidently IRRELEVANT - so sorting on raw confidence alone would interleave
    sure includes with sure excludes at the top. Instead: include -> 50 + conf/2 (50..100),
    uncertain -> 50, exclude -> 50 - conf/2 (0..50). Within includes this IS confidence-descending;
    within excludes it puts the least-sure excludes first (the ones a reconciler should check first).
    """
    try:
        c = max(0.0, min(100.0, float(confidence)))
    except (TypeError, ValueError):
        c = 0.0
    d = str(decision).strip().lower()
    if d == "include":
        return 50.0 + c / 2.0
    if d == "exclude":
        return 50.0 - c / 2.0
    return 50.0   # uncertain (or anything unexpected): undecidable, sits between the two


def build_ranked_queue(res_df: pd.DataFrame) -> pd.DataFrame:
    """Ranked reconciliation queue: all records, most-likely-relevant first (stable on ties)."""
    ranked = res_df[["record_id", "title", "decision", "confidence", "rationale"]].rename(
        columns={"decision": "ai_decision"}).copy()
    ranked["relevance_score"] = [
        relevance_score(d, c) for d, c in zip(ranked["ai_decision"], ranked["confidence"])
    ]
    # mergesort = stable: tied scores keep master_records order, so the queue is deterministic
    return ranked.sort_values("relevance_score", ascending=False, kind="mergesort").reset_index(drop=True)


def call_model(model: str, prompt: str) -> str:
    """Single LiteLLM call. Imported lazily so --dry-run works without litellm installed."""
    import litellm

    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp["choices"][0]["message"]["content"]


def screen_record(model: str, template: str, criteria: str, row: pd.Series) -> dict:
    prompt = build_prompt(template, criteria, row)
    try:
        raw = call_model(model, prompt)
        result = robust_parse(raw, str(row["record_id"]))
    except Exception as e:  # network / auth / rate-limit errors -> uncertain, logged
        result = {
            "record_id": str(row["record_id"]),
            "decision": "uncertain",
            "criteria_violated": [],
            "rationale": f"API_ERROR: {e}",
            "confidence": 0,
            "parse_ok": False,
        }
    result["title"] = str(row.get("title", ""))
    result["year"] = str(row.get("year", ""))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="EvidenceEngine AI title/abstract screener.")
    ap.add_argument("--master", default="Outputs/master_records.csv", help="master_records.csv from master_records.py")
    ap.add_argument("--criteria", default="criteria.txt", help="shared topic config")
    ap.add_argument("--prompt", default="screening_abstract.txt", help="screening prompt template")
    ap.add_argument("--model", default="gemini/gemini-2.5-flash", help="LiteLLM model string")
    ap.add_argument("--outdir", default="Outputs")
    ap.add_argument("--limit", type=int, default=0, help="screen only the first N records (0 = all)")
    ap.add_argument("--workers", type=int, default=4, help="concurrent requests")
    ap.add_argument("--dry-run", action="store_true", help="print the first assembled prompt and exit (no API call)")
    ap.add_argument("--ranked-output", dest="ranked_output", nargs="?", const="ranked_queue.csv",
                    default=None, metavar="FILENAME",
                    help="also write a ranked reconciliation queue (most-likely-relevant first) after the "
                         "main outputs; default filename ranked_queue.csv in --outdir. PRODUCTION ARM ONLY - "
                         "never show it to a blind human screener (see RANKING_NOTES.md)")
    ap.add_argument("--okf-bundle", dest="okf_bundle", default=None,
                    help="OKF bundle dir (default: auto-detect ../okf-bundle)")
    ap.add_argument("--no-okf", dest="no_okf", action="store_true",
                    help="skip writing OKF screening-decision nodes")
    args = ap.parse_args()

    load_dotenv()

    master_path, criteria_path, prompt_path = Path(args.master), Path(args.criteria), Path(args.prompt)
    for p in (master_path, criteria_path, prompt_path):
        if not p.exists():
            print(f"ERROR: missing file: {p}", file=sys.stderr)
            return 1

    template = load_prompt_template(prompt_path)
    criteria = criteria_path.read_text(encoding="utf-8")
    df = pd.read_csv(master_path).fillna("")
    if "record_id" not in df.columns:
        print("ERROR: master CSV has no 'record_id' column - run master_records.py first.", file=sys.stderr)
        return 1
    if args.limit > 0:
        df = df.head(args.limit)

    if args.dry_run:
        print("=== DRY RUN: first assembled prompt (no API call) ===\n")
        print(build_prompt(template, criteria, df.iloc[0]))
        print(f"\n=== would screen {len(df)} record(s) with model '{args.model}' ===")
        return 0

    print(f"Screening {len(df)} record(s) with '{args.model}' ...")
    rows = [r for _, r in df.iterrows()]
    results: list[dict] = [None] * len(rows)  # type: ignore
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(screen_record, args.model, template, criteria, r): i for i, r in enumerate(rows)}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            results[futures[fut]] = fut.result()
            done += 1
            print(f"  [{done}/{len(rows)}]", end="\r", flush=True)
    print()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)

    res_df = pd.DataFrame(results)
    res_df["criteria_violated"] = res_df["criteria_violated"].apply(lambda x: "; ".join(x) if isinstance(x, list) else x)
    res_df["model"] = args.model
    res_df["prompt_file"] = prompt_path.name

    # 1) wide results
    cols = ["record_id", "title", "year", "decision", "confidence", "rationale", "criteria_violated", "model", "prompt_file"]
    res_df[cols].to_excel(outdir / f"Abstract_Screening_{ts}.xlsx", index=False)

    # 2) audit file (shared reconciliation format) - Human_Decision left blank for blind/independent entry
    audit = pd.DataFrame(
        {
            "record_id": res_df["record_id"],
            "title": res_df["title"],
            "AI_Decision": res_df["decision"],
            "Human_Decision": "",
            "Match? (Y/N)": "",
            "Error_Category": "",
            "Consensus_Decision": "",
            "AI_Rationale": res_df["rationale"],
            "AI_Confidence": res_df["confidence"],
        }
    )
    audit.to_csv(outdir / f"Abstract_Audit_{ts}.csv", index=False)

    # 2b) optional ranked reconciliation queue (--ranked-output), most-likely-relevant first
    ranked_path = None
    if args.ranked_output:
        rp = Path(args.ranked_output)
        ranked_path = rp if rp.is_absolute() else outdir / rp
        # BLIND-FIRST GATE: this file must never be shown on the blind human screening screen.
        # It is only for the production arm (post-blind reconciliation or non-validation reviews).
        build_ranked_queue(res_df).to_csv(ranked_path, index=False)

    # 3) stage counts for PRISMA - MERGE into the existing file (do not clobber fulltext_* keys)
    counts = res_df["decision"].value_counts().to_dict()
    sc_path = outdir / "stage_counts.json"
    stage_counts: dict = {}
    if sc_path.exists():
        try:
            stage_counts = json.loads(sc_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stage_counts = {}
    stage_counts.update({
        "abstract_screened": int(len(res_df)),
        "abstract_included": int(counts.get("include", 0)),
        "abstract_excluded": int(counts.get("exclude", 0)),
        "abstract_uncertain": int(counts.get("uncertain", 0)),
    })
    sc_path.write_text(json.dumps(stage_counts, indent=2), encoding="utf-8")

    # 4) log
    n_parse_fail = int((~res_df["parse_ok"]).sum())
    log = [
        f"EvidenceEngine abstract screening log - {ts}",
        f"Model: {args.model}    Prompt: {prompt_path.name}    Criteria: {criteria_path.name}",
        f"Records screened: {len(res_df)}",
        f"  include={stage_counts['abstract_included']}  exclude={stage_counts['abstract_excluded']}  uncertain={stage_counts['abstract_uncertain']}",
        f"  parse/API failures (defaulted to 'uncertain'): {n_parse_fail}",
        "",
    ]
    for _, r in res_df.iterrows():
        flag = "" if r["parse_ok"] else "  <-- PARSE/API FAILURE"
        log.append(f"{r['record_id']}: {r['decision']} ({r['confidence']}%){flag}")
    (outdir / f"Screening_Log_{ts}.txt").write_text("\n".join(log), encoding="utf-8")

    # 5) OKF nodes - one provenance-bearing screening-decision node per record (RAISE 1.8/1.9a).
    #    Non-fatal: an OKF-writing failure must never break a screening run (recall-first).
    if not args.no_okf:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import okf_writer
            bundle = okf_writer.okf_tools.find_bundle(args.okf_bundle)
            prov = okf_writer.build_provenance(args.model, prompt_path)
            n_okf = 0
            for r in results:
                if not r.get("record_id"):
                    continue
                okf_writer.write_screening_decision_node(
                    bundle, record_id=str(r["record_id"]), stage="abstract",
                    decision=str(r["decision"]), provenance=prov,
                    rationale=str(r.get("rationale", "")), confidence=r.get("confidence"),
                    criteria_violated=r.get("criteria_violated") or [],
                    title=str(r.get("title", "")))
                n_okf += 1
            if n_okf:                       # skip the whole-bundle rebuild on a no-op run
                okf_writer.write_index(bundle)
                okf_writer.append_log(bundle,
                    f"**AI abstract screening run**: {n_okf} record(s) screened via `{args.model}` "
                    f"(`{prompt_path.name}`) — include={stage_counts['abstract_included']}, "
                    f"exclude={stage_counts['abstract_excluded']}, uncertain={stage_counts['abstract_uncertain']}.")
            print(f"OKF: wrote/updated {n_okf} screening-decision node(s) (human_verified:false) in {bundle}")
        except Exception as e:  # noqa: BLE001 - OKF writing is best-effort, never fatal
            print(f"OKF: skipped node writing ({e})", file=sys.stderr)

    print(f"Done. include={stage_counts['abstract_included']} exclude={stage_counts['abstract_excluded']} "
          f"uncertain={stage_counts['abstract_uncertain']} (parse/API failures: {n_parse_fail})")
    print(f"Outputs in {outdir}/ :  Abstract_Screening_{ts}.xlsx, Abstract_Audit_{ts}.csv, "
          f"Screening_Log_{ts}.txt, stage_counts.json"
          + (f", {ranked_path.name} (production arm only - never show to a blind screener)" if ranked_path else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
