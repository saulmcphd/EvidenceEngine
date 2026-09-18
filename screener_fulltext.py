"""
screener_fulltext.py - EvidenceEngine Phase 1 (Step 5b)
=======================================================
AI full-text screener. For each PDF in PDFs/FullText_Candidates/ it extracts the full text,
matches the file to a master record_id, applies criteria.txt + screening_fulltext.txt, and returns
an auditable include/exclude decision. This is the FINAL eligibility stage, so it is stricter than
the title/abstract screener:

  * Decision is "include" or "exclude" only - NO "uncertain" at full text.
  * Every "exclude" must carry ONE primary exclusion_reason AND a VERBATIM supporting_quote from
    the paper (so a human can check the exclusion against the source in seconds).

Design choices (mirrors screener_abstract.py):
  * Provider-agnostic via LiteLLM - switch model with --model, no code change, temperature=0.
  * Recall-first / fail-safe: a PDF that cannot be extracted, or a response that cannot be parsed,
    defaults to "include" (flagged for human review) - the AI never silently EXCLUDES a study on a
    technical failure. The AI is a SECOND screener; a human reconciles every decision.
  * Robust JSON parsing - an unparseable response becomes a safe default, never a crash.
  * Audit CSV leaves Human_Decision BLANK so the human can decide blind (before seeing the AI).

PDF -> record_id matching (in order, first hit wins):
  1. REC_NNNN in the filename (e.g. REC_0007.pdf)            -> exact id
  2. a DOI from master_records.csv found in the filename     -> doi
  3. Author_Year in the filename (e.g. Feeney_2009.pdf)      -> author+year against master
  4. the filename matched against record titles             -> title
Unmatched PDFs are still screened (record_id = the file stem, flagged) so no candidate is silently
dropped, and they are listed prominently in the log for the human to fix the mapping.

Outputs (in --outdir, default ./Outputs):
  FullText_Screening_<ts>.xlsx   wide results table
  FullText_Audit_<ts>.csv        shared reconciliation format + Exclusion_Reason + Supporting_Quote
  Screening_Log_<ts>.txt         per-PDF success / failure / unmatched log
  stage_counts.json              MERGED with existing counts: adds fulltext_assessed/included/
                                 excluded + an exclusion_reasons {reason: count} dict (for PRISMA)

Usage
-----
    # sanity-check prompt assembly WITHOUT calling any API (free):
    python screener_fulltext.py --dry-run --limit 1

    # real run (needs an API key in .env for the chosen provider):
    python screener_fulltext.py --model gemini/gemini-2.5-flash --limit 3
    python screener_fulltext.py --model claude-opus-4-8
    python screener_fulltext.py --model gpt-4o --max-chars 350000   # cap text for small-context models

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

VALID_DECISIONS = {"include", "exclude"}  # no "uncertain" at full text
PROMPT_VERSION = "fulltext_v1"


# --------------------------------------------------------------------------------------------------
# PDF text extraction (kept in sync with prompter.py::extract_text_advanced)
# --------------------------------------------------------------------------------------------------
def extract_text_advanced(pdf_path: Path) -> str:
    """Accurately extracts text, tolerant of complex research tables. Returns 'ERROR...' on failure."""
    import pdfplumber

    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        return f"ERROR_TEXT_EXTRACTION: {e}"


# --------------------------------------------------------------------------------------------------
# Record matching helpers (kept in sync with master_records.py)
# --------------------------------------------------------------------------------------------------
def first_author(authors: str) -> str:
    """Best-effort first-author surname from a free-text author string."""
    authors = str(authors)
    if not authors.strip():
        return ""
    for sep in (";", " and ", "&", ","):
        if sep in authors:
            head = authors.split(sep)[0].strip()
            if "," in head:
                return head.split(",")[0].strip()
            parts = head.split()
            return parts[-1] if parts else authors.strip()
    parts = authors.split()
    return parts[-1] if parts else authors.strip()


def _norm(text: str) -> str:
    """Lower-case and strip everything except a-z0-9 (for fuzzy filename<->title/doi comparison)."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def match_pdf_to_record(stem: str, master: pd.DataFrame) -> dict:
    """Map a PDF filename stem to a master record. Returns dict with record_id/title/year/method/matched."""
    ids = master["record_id"].astype(str).tolist()
    stem_norm = _norm(stem)

    # 1) explicit REC_NNNN in the filename
    m = re.search(r"rec[_\-\s]?0*(\d{1,4})", stem, re.IGNORECASE)
    if m:
        candidate = f"REC_{int(m.group(1)):04d}"
        if candidate in ids:
            return _hit(master, candidate, "rec_id")

    # 2) a DOI from master found inside the filename
    if "doi" in master.columns:
        for _, r in master.iterrows():
            doi = _norm(r.get("doi", ""))
            if doi and len(doi) >= 8 and doi in stem_norm:
                return _hit(master, str(r["record_id"]), "doi")

    # 3) Author_Year  (a 19xx/20xx year in the stem + a first-author surname token)
    ym = re.search(r"(19|20)\d{2}", stem)
    if ym:
        year = ym.group(0)
        for _, r in master.iterrows():
            surname = _norm(first_author(r.get("authors", "")))
            if surname and len(surname) >= 3 and surname in stem_norm and str(r.get("year", "")).strip() == year:
                return _hit(master, str(r["record_id"]), "author_year")

    # 4) filename matched against a record title (truncated-title filenames are common). Collect ALL
    # candidates above threshold (not just the first) so two similarly-titled studies - a trial and
    # its follow-up, say - can't have the PDF silently filed under whichever one happened to come
    # first in the master's row order; a second, equally-plausible candidate makes it ambiguous.
    stem_tokens = {t for t in re.split(r"[^a-z0-9]+", stem.lower()) if len(t) > 3}
    candidates: list[tuple[str, str]] = []   # (record_id, method), in the order found
    for _, r in master.iterrows():
        title_norm = _norm(r.get("title", ""))
        if not title_norm or len(stem_norm) < 8:
            continue
        if stem_norm in title_norm or title_norm.startswith(stem_norm[:24]):
            candidates.append((str(r["record_id"]), "title"))
            continue
        # token-overlap fallback for reordered / partial titles
        title_tokens = {t for t in re.split(r"[^a-z0-9]+", str(r.get("title", "")).lower()) if len(t) > 3}
        if stem_tokens and title_tokens:
            overlap = len(stem_tokens & title_tokens) / len(stem_tokens)
            if overlap >= 0.6:
                candidates.append((str(r["record_id"]), "title_tokens"))

    if len(candidates) == 1:
        return _hit(master, candidates[0][0], candidates[0][1])
    if len(candidates) > 1:
        ids = ", ".join(c[0] for c in candidates)
        return {"record_id": stem, "title": stem, "year": "", "match_method": "AMBIGUOUS_MATCH",
                "matched": False, "ambiguous_candidates": ids}

    # no match -> screen anyway under the file stem, flagged for the human
    return {"record_id": stem, "title": stem, "year": "", "match_method": "UNMATCHED", "matched": False}


def _hit(master: pd.DataFrame, record_id: str, method: str) -> dict:
    row = master.loc[master["record_id"].astype(str) == record_id].iloc[0]
    return {
        "record_id": record_id,
        "title": str(row.get("title", "")),
        "year": str(row.get("year", "")),
        "match_method": method,
        "matched": True,
    }


# --------------------------------------------------------------------------------------------------
# Prompt assembly + robust JSON parsing
# --------------------------------------------------------------------------------------------------
def load_prompt_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_prompt(template: str, criteria: str, rec: dict, fulltext: str) -> str:
    return (
        template.replace("[CRITERIA_CONTENT]", criteria.strip())
        .replace("[RECORD_ID]", str(rec["record_id"]))
        .replace("[TITLE]", str(rec.get("title", "")).strip())
        .replace("[YEAR]", str(rec.get("year", "")).strip())
        .replace("[FULLTEXT]", fulltext.strip() if fulltext.strip() else "(no extractable text)")
    )


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


def robust_parse(text: str, record_id: str) -> dict:
    """Parse the model's JSON defensively. Always returns a valid include/exclude decision dict.

    Fail-safe: an unparseable response defaults to 'include' (flagged) - the AI never silently
    EXCLUDES a study because of a parsing problem.
    """
    fallback = {
        "record_id": record_id,
        "decision": "include",
        "exclusion_reason": "",
        "supporting_quote": "",
        "rationale": "PARSE_FAILURE - response could not be parsed; defaulted to include and flagged for human review.",
        "confidence": 0,
        "parse_ok": False,
    }
    if not text:
        return fallback

    candidate = text.strip()
    if "```" in candidate:
        m = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
        if m:
            candidate = m.group(1).strip()

    for attempt in (candidate, _first_json_object(candidate)):
        if not attempt:
            continue
        try:
            obj = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        decision = str(obj.get("decision", "")).strip().lower()
        if decision not in VALID_DECISIONS:
            continue
        conf = obj.get("confidence", 0)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        if 0 < conf <= 1:       # some models answer on a 0-1 scale despite the 0-100 prompt instruction
            conf *= 100
        conf = max(0, min(100, int(conf)))

        exclusion_reason = str(obj.get("exclusion_reason", "")).strip()
        supporting_quote = str(obj.get("supporting_quote", "")).strip()
        rationale = str(obj.get("rationale", "")).strip()

        # Recall-first guardrail: the whole point of a full-text exclude is that a human can verify
        # it in seconds from ONE reason + a verbatim quote. A syntactically-valid exclude that omits
        # either must never pass through as a normal, unflagged exclusion (screening_fulltext.txt
        # <Task> rule 1) - downgrade it the same way every other technical failure in this file does.
        if decision == "exclude" and not (exclusion_reason and supporting_quote):
            return {
                "record_id": record_id,
                "decision": "include",
                "exclusion_reason": "",
                "supporting_quote": "",
                "rationale": ("AI excluded but did not return the required exclusion_reason + "
                              "supporting_quote - cannot be trusted without both, so defaulted to "
                              "include and flagged for human review. Model's own rationale, if any: "
                              + (rationale or "(none given)")),
                "confidence": 0,
                "parse_ok": True,
                "exclude_downgraded": True,
            }

        return {
            "record_id": record_id,
            "decision": decision,
            "exclusion_reason": exclusion_reason,
            "supporting_quote": supporting_quote,
            "rationale": rationale,
            "confidence": conf,
            "parse_ok": True,
        }

    # last resort: regex out a decision word. Recall-first: only honour an 'include' here. A detected
    # 'exclude' cannot carry the required reason + verbatim quote, so we never exclude on a broken parse.
    m = re.search(r'"?decision"?\s*[:=]\s*"?(include|exclude)', candidate, re.IGNORECASE)
    if m and m.group(1).lower() == "include":
        fallback["rationale"] = "Partial parse (regex fallback): 'include' detected; verify manually."
    elif m:
        fallback["rationale"] = (
            "Partial parse (regex fallback): the model appeared to exclude but the response could not be "
            "parsed for the required reason + verbatim quote; defaulted to include and flagged for review."
        )
    return fallback


def call_model(model: str, prompt: str) -> str:
    """Single LiteLLM call. Imported lazily so --dry-run works without litellm installed."""
    import litellm

    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp["choices"][0]["message"]["content"]


def screen_pdf(model: str, template: str, criteria: str, rec: dict, max_chars: int) -> dict:
    """Extract text from one PDF, screen it, and return a result dict. Never raises."""
    pdf_path = rec["pdf_path"]
    text = extract_text_advanced(pdf_path)
    truncated = False

    if text.startswith("ERROR") or not text.strip():
        # extraction failed or no text layer (e.g. scanned PDF) -> fail-safe include, flagged
        reason = text if text.startswith("ERROR") else "NO_EXTRACTABLE_TEXT (scanned PDF / image-only?)"
        result = {
            "record_id": str(rec["record_id"]),
            "decision": "include",
            "exclusion_reason": "",
            "supporting_quote": "",
            "rationale": f"TEXT_EXTRACTION_FAILURE: {reason}; defaulted to include and flagged for human review.",
            "confidence": 0,
            "parse_ok": False,
        }
        return _decorate(result, rec, n_chars=0, truncated=False, extract_ok=False)

    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    prompt = build_prompt(template, criteria, rec, text)
    try:
        raw = call_model(model, prompt)
        result = robust_parse(raw, str(rec["record_id"]))
    except Exception as e:  # network / auth / rate-limit -> fail-safe include, flagged
        result = {
            "record_id": str(rec["record_id"]),
            "decision": "include",
            "exclusion_reason": "",
            "supporting_quote": "",
            "rationale": f"API_ERROR: {e}; defaulted to include and flagged for human review.",
            "confidence": 0,
            "parse_ok": False,
        }
    return _decorate(result, rec, n_chars=len(text), truncated=truncated, extract_ok=True)


def _decorate(result: dict, rec: dict, n_chars: int, truncated: bool, extract_ok: bool) -> dict:
    result["title"] = str(rec.get("title", ""))
    result["year"] = str(rec.get("year", ""))
    result["pdf_file"] = rec["pdf_path"].name
    result["match_method"] = rec.get("match_method", "")
    result["matched"] = bool(rec.get("matched", False))
    result["text_chars"] = n_chars
    result["text_truncated"] = truncated
    result["extract_ok"] = extract_ok
    return result


# --------------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="EvidenceEngine AI full-text screener (Step 5b).")
    ap.add_argument("--master", default="Outputs/master_records.csv", help="master_records.csv from master_records.py")
    ap.add_argument("--criteria", default="criteria.txt", help="shared topic config")
    ap.add_argument("--prompt", default="screening_fulltext.txt", help="full-text screening prompt template")
    ap.add_argument("--model", default="gemini/gemini-2.5-flash", help="LiteLLM model string")
    ap.add_argument("--pdfdir", default="PDFs/FullText_Candidates", help="folder of candidate PDFs")
    ap.add_argument("--outdir", default="Outputs")
    ap.add_argument("--limit", type=int, default=0, help="screen only the first N PDFs (0 = all)")
    ap.add_argument("--workers", type=int, default=4, help="concurrent requests")
    ap.add_argument("--max-chars", dest="max_chars", type=int, default=0,
                    help="truncate extracted text to N chars (0 = no limit; use for small-context models)")
    ap.add_argument("--dry-run", action="store_true", help="print the first assembled prompt and exit (no API call)")
    ap.add_argument("--okf-bundle", dest="okf_bundle", default=None,
                    help="OKF bundle dir (default: auto-detect ../okf-bundle)")
    ap.add_argument("--no-okf", dest="no_okf", action="store_true",
                    help="skip writing OKF screening-decision nodes")
    args = ap.parse_args()

    load_dotenv()

    criteria_path, prompt_path = Path(args.criteria), Path(args.prompt)
    master_path = Path(args.master)
    for p in (master_path, criteria_path, prompt_path):
        if not p.exists():
            print(f"ERROR: missing file: {p}", file=sys.stderr)
            return 1

    pdfdir = Path(args.pdfdir)
    pdfdir.mkdir(parents=True, exist_ok=True)  # create FullText_Candidates if absent

    template = load_prompt_template(prompt_path)
    criteria = criteria_path.read_text(encoding="utf-8")
    master = pd.read_csv(master_path).fillna("")
    if "record_id" not in master.columns:
        print("ERROR: master CSV has no 'record_id' column - run master_records.py first.", file=sys.stderr)
        return 1
    dup_ids = master["record_id"].astype(str)
    dup_ids = dup_ids[dup_ids.duplicated()].unique().tolist()
    if dup_ids:
        print(f"WARNING: master has duplicate record_id(s): {dup_ids[:10]} - first row used for each.", file=sys.stderr)
    missing_cols = [c for c in ("title", "authors", "year", "doi") if c not in master.columns]
    if missing_cols:
        print(f"WARNING: master missing column(s) {missing_cols}; some PDF-matching methods unavailable.", file=sys.stderr)

    pdfs = sorted(pdfdir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {pdfdir}/ .")
        print(f"Put the full-text candidate PDFs there (e.g. REC_0001.pdf or Author_Year.pdf) and re-run.")
        return 0

    # match every PDF to a record up front (cheap, deterministic)
    recs: list[dict] = []
    for pdf in pdfs:
        rec = match_pdf_to_record(pdf.stem, master)
        rec["pdf_path"] = pdf
        recs.append(rec)

    unmatched = [r for r in recs if not r["matched"]]

    if args.limit > 0:
        recs = recs[: args.limit]

    if args.dry_run:
        print("=== DRY RUN: first assembled prompt (no API call) ===\n")
        first = recs[0]
        text = extract_text_advanced(first["pdf_path"])
        preview = text if len(text) <= 2000 else text[:2000] + f"\n...[truncated for preview; {len(text)} chars total]..."
        prompt = build_prompt(template, criteria, first, preview)
        print(prompt)
        print(f"\n=== PDF '{first['pdf_path'].name}' -> {first['record_id']} (match: {first['match_method']}) ===")
        print(f"=== would screen {len(recs)} PDF(s) with model '{args.model}' ===")
        if unmatched:
            print(f"=== WARNING: {len(unmatched)} unmatched PDF(s): {', '.join(r['pdf_path'].name for r in unmatched)} ===")
        return 0

    print(f"Screening {len(recs)} PDF(s) with '{args.model}' ...")
    results: list[dict] = [None] * len(recs)  # type: ignore
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(screen_pdf, args.model, template, criteria, r, args.max_chars): i
                   for i, r in enumerate(recs)}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            results[futures[fut]] = fut.result()
            done += 1
            print(f"  [{done}/{len(recs)}]", end="\r", flush=True)
    print()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)

    res_df = pd.DataFrame(results)
    res_df["model"] = args.model
    res_df["prompt_file"] = prompt_path.name
    res_df["prompt_version"] = PROMPT_VERSION

    # 1) wide results table
    cols = ["record_id", "title", "year", "decision", "confidence", "exclusion_reason",
            "supporting_quote", "rationale", "pdf_file", "match_method", "matched",
            "text_chars", "text_truncated", "model", "prompt_file", "prompt_version"]
    res_df[cols].to_excel(outdir / f"FullText_Screening_{ts}.xlsx", index=False)

    # 2) audit file - shared reconciliation format + the two full-text-specific columns appended.
    #    Human_Decision left BLANK for blind/independent entry.
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
            "Exclusion_Reason": res_df["exclusion_reason"],
            "Supporting_Quote": res_df["supporting_quote"],
            "Text_Truncated": res_df["text_truncated"],  # True only if --max-chars cut the text
        }
    )
    audit.to_csv(outdir / f"FullText_Audit_{ts}.csv", index=False)

    # 3) stage counts for PRISMA - MERGE into the existing file (do not clobber abstract_* keys)
    counts = res_df["decision"].value_counts().to_dict()
    n_incl = int(counts.get("include", 0))
    n_excl = int(counts.get("exclude", 0))
    excl_reasons: dict[str, int] = {}
    for _, r in res_df[res_df["decision"] == "exclude"].iterrows():
        reason = str(r["exclusion_reason"]).strip() or "(unspecified)"
        excl_reasons[reason] = excl_reasons.get(reason, 0) + 1

    sc_path = outdir / "stage_counts.json"
    stage_counts: dict = {}
    if sc_path.exists():
        try:
            stage_counts = json.loads(sc_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stage_counts = {}
    # full-text screening OWNS exclusion_reasons (replace, so the dict always matches fulltext_excluded
    # for the latest run). The abstract screener merges and preserves these keys, so nothing is clobbered.
    stage_counts.update(
        {
            "fulltext_assessed": int(len(res_df)),
            "fulltext_included": n_incl,
            "fulltext_excluded": n_excl,
            "exclusion_reasons": excl_reasons,
        }
    )
    sc_path.write_text(json.dumps(stage_counts, indent=2), encoding="utf-8")

    # 4) log
    n_fail = int((~res_df["parse_ok"]).sum())
    n_extract_fail = int((~res_df["extract_ok"]).sum())
    n_downgraded = int(res_df.get("exclude_downgraded", pd.Series(dtype=bool)).fillna(False).sum())
    log = [
        f"EvidenceEngine full-text screening log - {ts}",
        f"Model: {args.model}    Prompt: {prompt_path.name} ({PROMPT_VERSION})    Criteria: {criteria_path.name}",
        f"PDFs assessed: {len(res_df)}   include={n_incl}  exclude={n_excl}",
        f"  parse/API failures (defaulted to 'include', flagged): {n_fail}",
        f"  text-extraction failures (defaulted to 'include', flagged): {n_extract_fail}",
        f"  excludes missing a reason+quote, downgraded to 'include' (flagged): {n_downgraded}",
        "",
    ]
    if unmatched:
        log.append(f"UNMATCHED / AMBIGUOUS PDFs ({len(unmatched)}) - screened under the file stem; fix the filename or master mapping:")
        for r in unmatched:
            if r.get("match_method") == "AMBIGUOUS_MATCH":
                log.append(f"  - {r['pdf_path'].name}  AMBIGUOUS: matches multiple studies "
                           f"({r.get('ambiguous_candidates', '')}) - rename the file to REC_NNNN.pdf to disambiguate")
            else:
                log.append(f"  - {r['pdf_path'].name}  (screened as record_id={r['record_id']})")
        log.append("")
    log.append("Per-PDF decisions:")
    for _, r in res_df.iterrows():
        flags = []
        if not r["matched"]:
            flags.append("UNMATCHED")
        if not r["extract_ok"]:
            flags.append("EXTRACT_FAIL")
        if not r["parse_ok"]:
            flags.append("PARSE/API_FAIL")
        if bool(r.get("exclude_downgraded", False)):
            flags.append("EXCLUDE_MISSING_REASON/QUOTE->DOWNGRADED_TO_INCLUDE")
        if r["text_truncated"]:
            flags.append("TEXT_TRUNCATED")
        flag = ("  <-- " + ", ".join(flags)) if flags else ""
        line = f"{r['record_id']} [{r['pdf_file']}]: {r['decision']} ({r['confidence']}%)"
        if r["decision"] == "exclude" and str(r["exclusion_reason"]).strip():
            line += f"  reason: {r['exclusion_reason']}"
        log.append(line + flag)
    (outdir / f"Screening_Log_{ts}.txt").write_text("\n".join(log), encoding="utf-8")

    # 5) OKF nodes - one provenance-bearing full-text screening-decision node per PDF (RAISE 1.8/1.9a).
    #    Non-fatal: an OKF-writing failure must never break a screening run (recall-first).
    if not args.no_okf:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import okf_writer
            bundle = okf_writer.okf_tools.find_bundle(args.okf_bundle)
            prov = okf_writer.build_provenance(args.model, prompt_path, prompt_version=PROMPT_VERSION)
            n_okf = 0
            for r in results:
                if not r.get("record_id"):
                    continue
                okf_writer.write_screening_decision_node(
                    bundle, record_id=str(r["record_id"]), stage="fulltext",
                    decision=str(r["decision"]), provenance=prov,
                    rationale=str(r.get("rationale", "")), confidence=r.get("confidence"),
                    exclusion_reason=str(r.get("exclusion_reason", "")),
                    supporting_quote=str(r.get("supporting_quote", "")),
                    title=str(r.get("title", "")))
                n_okf += 1
            if n_okf:                       # skip the whole-bundle rebuild on a no-op run
                okf_writer.write_index(bundle)
                okf_writer.append_log(bundle,
                    f"**AI full-text screening run**: {n_okf} PDF(s) screened via `{args.model}` "
                    f"(`{prompt_path.name}`) — include={n_incl}, exclude={n_excl} "
                    f"(unmatched={len(unmatched)}, downgraded excludes={n_downgraded}).")
            print(f"OKF: wrote/updated {n_okf} full-text decision node(s) (human_verified:false) in {bundle}")
        except Exception as e:  # noqa: BLE001 - OKF writing is best-effort, never fatal
            print(f"OKF: skipped node writing ({e})", file=sys.stderr)

    print(f"Done. include={n_incl} exclude={n_excl} "
          f"(parse/API failures: {n_fail}; extraction failures: {n_extract_fail}; unmatched PDFs: {len(unmatched)})")
    print(f"Outputs in {outdir}/ :  FullText_Screening_{ts}.xlsx, FullText_Audit_{ts}.csv, "
          f"Screening_Log_{ts}.txt, stage_counts.json")
    if excl_reasons:
        print("Exclusion reasons: " + "; ".join(f"{k} ({v})" for k, v in excl_reasons.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
