"""
screening_import.py - EvidenceEngine Phase 1
============================================
Bring the HUMAN screening decisions back into the pipeline so reliability.py (future) can compare the
AI's decisions against the human's BLIND decisions on the SAME records (joined on record_id).

This is the human side of the blind-first validation design: the human records include/exclude BEFORE
seeing any AI output; this script just parses whatever the human's tool exported.

Inputs (one of, chosen with --kind):
  ris      a RIS file exported after screening (Zotero / EndNote / Mendeley / Rayyan).
           record_id recovered from ID / C1 / the "record_id=REC_NNNN" note (N1); decision from an
           inclusion marker if the export carries one (e.g. Rayyan's RAYYAN-INCLUSION note).
  rayyan   a Rayyan CSV export. record_id from the `key` column; decision from the RAYYAN-INCLUSION
           note; screener = the Rayyan username.
  csv      a generic CSV - typically the dashboard's instrumented capture, which is the ONLY source
           that carries a per-decision timestamp (decided_at) and per-screener order_index needed
           for the fatigue model. Columns are matched flexibly (aliases below).

record_id recovery order: an explicit REC_NNNN id -> DOI match against master -> title_hash match ->
normalised-title match. Unmatched rows are written with a blank record_id and listed in the summary.

Both screening stages are supported (--stage, default abstract) — the two entry points of the product
thesis exist at 5a AND 5b (playbook-full-text-screening step 7; concept-dual-screening):

Output (in --outdir, default Outputs):
  Re-importing MERGES with an existing output file at BOTH stages (this upload wins per record/reviewer;
  all other previously-imported rows are kept) — Rayyan exports Included and Excluded articles as SEPARATE
  files, so per-batch uploads must never clobber each other. --replace restores plain overwrite (used by
  the webapp's compile-my-decisions, which rebuilds the in-app arm from scratch).

  --stage abstract   human_decisions.csv     columns: record_id, human_decision, decided_at, screener,
                                             order_index (reliability.py joins this to the AI audit)
  --stage fulltext   fulltext_human_decisions.csv
                     columns: record_id, ft_decision, reason, supporting_quote, decided_at, screener,
                     order_index, flag — the same shape as the app's in-app fulltext_decisions.csv, so
                     the webapp reads both as ONE human arm. Exclusion reasons are captured where the
                     export carries them (Rayyan exclusion-reason labels; a reason/quote CSV column);
                     an imported EXCLUDE missing its reason/quote is KEPT but flagged, never dropped —
                     the reconciliation screen's MECIR-C41 gate demands the reason + verbatim quote
                     before any FINAL exclude is saved (recall-first: rejecting rows would silently
                     discard human work). 'awaiting' (couldn't get/read the paper) survives a round trip.
                     Multi-reviewer exports keep EVERY reviewer's vote (one row each) so human-vs-human
                     conflicts surface at reconciliation. Re-importing MERGES with the existing file
                     (this upload wins per record/reviewer; other rows kept) — Rayyan exports Included
                     and Excluded articles as separate files, so per-batch uploads must never clobber
                     each other.

Usage
-----
    python screening_import.py --input Outputs/master_records.ris --kind ris
    python screening_import.py --input rayyan_export.csv         --kind rayyan
    python screening_import.py --input dashboard_decisions.csv   --kind csv
    python screening_import.py --input rayyan_fulltext.csv       --kind rayyan --stage fulltext
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

REC_ID_RE = re.compile(r"REC[_\-\s]?0*(\d{1,4})", re.IGNORECASE)
RECORD_ID_TAG_RE = re.compile(r"record_id\s*=\s*(REC[_\-\s]?\d{1,4})", re.IGNORECASE)

# tags in a RIS record that may carry a human include/exclude marker
RIS_DECISION_TAGS = ["N1", "N2", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "KW", "LB"]

# flexible column aliases for the generic instrumented-UI CSV
CSV_ALIASES = {
    "record_id": ["record_id", "recordid", "rec_id", "id", "key"],
    "human_decision": ["human_decision", "ft_decision", "decision", "human", "screening_decision", "label", "vote"],
    "decided_at": ["decided_at", "timestamp", "time", "datetime", "decision_time", "decided"],
    "screener": ["screener", "reviewer", "user", "rater", "name", "screener_id"],
    "order_index": ["order_index", "order", "position", "idx", "sequence", "seq", "pos"],
    "doi": ["doi"],
    "title": ["title", "ti"],
    "authors": ["authors", "author", "au"],
    "year": ["year", "py"],
    # full-text stage only: the primary failed criterion + the verbatim quote backing an exclude (MECIR C41)
    "reason": ["reason", "exclusion_reason", "exclusion reason", "exclusion reasons", "exclude_reason",
               "primary_reason", "reason_for_exclusion", "ft_reason"],
    "supporting_quote": ["supporting_quote", "supporting quote", "quote", "verbatim_quote", "evidence_quote"],
}

OUT_COLUMNS = ["record_id", "human_decision", "decided_at", "screener", "order_index"]
# --stage fulltext writes the SAME shape as the webapp's in-app fulltext_decisions.csv (its FT_COLS),
# so the app can read the two files as one human arm without translation.
FT_OUT_COLUMNS = ["record_id", "ft_decision", "reason", "supporting_quote", "decided_at", "screener",
                  "order_index", "flag"]

# Rayyan writes full-text exclusion reasons into the notes blob as e.g.
#   ... | RAYYAN-EXCLUSION-REASONS: wrong population,background article | ...
RAYYAN_EXCL_RE = re.compile(r"RAYYAN-EXCLUSION-REASONS:\s*([^|]+)", re.IGNORECASE)


def ft_import_flag(reason: str, quote: str) -> str:
    """Honest per-row flag for an imported full-text EXCLUDE, naming exactly WHAT is missing — never claim
    the reason is absent when it was captured (Rayyan carries reasons but never verbatim quotes, so a
    both-or-nothing flag would mislabel every conscientious Rayyan exclude)."""
    reason, quote = str(reason).strip(), str(quote).strip()
    if reason and quote:
        return ""
    missing = ("the verbatim quote (reason captured)" if reason
               else "its failed-criterion reason (quote captured)" if quote
               else "its failed-criterion reason and verbatim quote")
    return f"imported — exclude is missing {missing}; complete it at Reconciliation"


def read_decisions_csv(path: Path) -> pd.DataFrame:
    """Read an exported decisions CSV leniently: Excel on Windows often saves cp1252 (smart quotes in a
    pasted verbatim quote), which the default utf-8 read rejects — a hard crash the user would see as
    'check the file format'. Try utf-8 first (correct for Rayyan/most tools), fall back to cp1252."""
    try:
        return pd.read_csv(path, encoding="utf-8-sig").fillna("").astype(str)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp1252").fillna("").astype(str)


# --------------------------------------------------------------------------------------------------
# Shared helpers (kept in sync with master_records.py)
# --------------------------------------------------------------------------------------------------
def first_author(authors: str) -> str:
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


def title_hash(title: str, authors: str, year: str) -> str:
    key = f"{str(title).strip().lower()}|{first_author(authors).lower()}|{str(year).strip()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def normalize_decision(value: str, stage: str = "abstract") -> str:
    """Map any human label to include / exclude / uncertain / '' (blank = no decision recorded).
    At the FULL-TEXT stage, 'awaiting' labels (couldn't obtain / couldn't read the paper) are preserved as
    'awaiting' so a re-import never turns a parked paper into a silent drop — awaiting is a PRISMA status,
    not an exclusion (concept-full-text-retrieval-workflow). An imported full-text 'maybe' is kept as
    'uncertain' and surfaced at Reconciliation for the definite call the stage requires — never dropped."""
    v = str(value).strip().lower()
    if not v:
        return ""
    if stage == "fulltext" and ("awaiting" in v or v in {"not retrieved", "not_retrieved", "unobtainable"}):
        return "awaiting"
    if v in {"include", "included", "yes", "y", "1", "true", "in"}:
        return "include"
    if v in {"exclude", "excluded", "no", "n", "0", "false", "out"}:
        return "exclude"
    if v in {"maybe", "unsure", "uncertain", "conflict", "conflicted", "?"}:
        return "uncertain"
    # substring fallback (handles "Included by reviewer", "EXCLUDE - off topic")
    if "exclud" in v:
        return "exclude"
    if "includ" in v:
        return "include"
    if "maybe" in v or "uncertain" in v or "unsure" in v:
        return "uncertain"
    return ""


def detect_exclusion_reason(blob: str) -> str:
    """Pull Rayyan's full-text exclusion-reason labels out of a notes blob ('' if none)."""
    m = RAYYAN_EXCL_RE.search(str(blob))
    return m.group(1).strip().strip(",") if m else ""


# --------------------------------------------------------------------------------------------------
# record_id recovery against master_records.csv
# --------------------------------------------------------------------------------------------------
def load_master(master_path: Path) -> pd.DataFrame | None:
    if not master_path.exists():
        return None
    df = pd.read_csv(master_path).fillna("").astype(str)
    if "title_hash" not in df.columns and {"title", "authors", "year"} <= set(df.columns):
        df["title_hash"] = [title_hash(r["title"], r["authors"], r["year"]) for _, r in df.iterrows()]
    return df


def recover_record_id(explicit_id: str, doi: str, title: str, authors: str, year: str,
                      master: pd.DataFrame | None) -> tuple[str, str]:
    """Return (record_id, method). Tries explicit REC id, then DOI / title_hash / title against master."""
    # 1) explicit REC_NNNN already present
    m = REC_ID_RE.search(str(explicit_id))
    if m:
        return f"REC_{int(m.group(1)):04d}", "explicit_id"

    if master is None:
        return "", "no_master"

    ids = master["record_id"].astype(str)

    # 2) DOI match
    doi_n = _norm(doi)
    if doi_n and len(doi_n) >= 8 and "doi" in master.columns:
        hits = master.loc[master["doi"].map(_norm) == doi_n, "record_id"]
        if len(hits):
            return str(hits.iloc[0]), "doi"

    # 3) title_hash match
    if title and "title_hash" in master.columns:
        th = title_hash(title, authors, year)
        hits = master.loc[master["title_hash"].astype(str) == th, "record_id"]
        if len(hits):
            return str(hits.iloc[0]), "title_hash"

    # 4) normalised-title match
    if title and "title" in master.columns:
        tn = _norm(title)
        if tn:
            hits = master.loc[master["title"].map(_norm) == tn, "record_id"]
            if len(hits):
                return str(hits.iloc[0]), "title"

    return "", "unmatched"


# --------------------------------------------------------------------------------------------------
# RIS
# --------------------------------------------------------------------------------------------------
def parse_ris_records(text: str) -> list[dict]:
    """Split a RIS file into records, each a dict tag -> list[str]."""
    records: list[dict] = []
    current: dict[str, list[str]] = {}
    last_tag: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        m = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", line)
        if m:
            tag, val = m.group(1), m.group(2)
            current.setdefault(tag, []).append(val)
            last_tag = tag
            if tag == "ER":
                records.append(current)
                current, last_tag = {}, None
        elif line.strip() and last_tag:
            # continuation line of the previous tag
            current[last_tag][-1] = (current[last_tag][-1] + " " + line.strip()).strip()
    if current:  # tolerate a missing final ER
        records.append(current)
    return records


def _ris_note_blob(rec: dict) -> str:
    blob_parts: list[str] = []
    for tag in RIS_DECISION_TAGS:
        blob_parts.extend(rec.get(tag, []))
    return " | ".join(blob_parts)


def detect_ris_decisions(rec: dict, stage: str = "abstract") -> list[tuple[str, str]]:
    """ALL (human_decision, screener) pairs from RIS note/label fields — one per reviewer for a Rayyan
    multi-reviewer export. Keeping only the first pair would silently destroy a genuine human-vs-human
    conflict, which is exactly what reconciliation (with the AI as extra arbiter) exists to settle.
    Generic markers yield a single anonymous pair."""
    blob = _ris_note_blob(rec)

    # Rayyan: RAYYAN-INCLUSION: {"alice"=>"Included", "bob"=>"Excluded"} — keep EVERY reviewer's vote
    rm = re.search(r"RAYYAN-INCLUSION:\s*\{(.*?)\}", blob)
    if rm:
        pairs = re.findall(r'"([^"]+)"\s*=>\s*"(Included|Excluded|Maybe)"', rm.group(1))
        if pairs:
            return [(normalize_decision(dec, stage), scr) for scr, dec in pairs]

    # generic markers — explicit include/exclude/maybe wins over the loose 'awaiting' heuristic below,
    # so a note like 'PDF obtained after awaiting author response | INCLUDED' imports as the include it is
    low = blob.lower()
    if re.search(r"\bexclud", low):
        return [("exclude", "")]
    if re.search(r"\binclud", low):
        return [("include", "")]
    if re.search(r"\bmaybe\b|\buncertain\b|\bunsure\b", low):
        return [("uncertain", "")]
    if stage == "fulltext" and "awaiting" in low:
        return [("awaiting", "")]
    return [("", "")]


def import_ris(path: Path, master: pd.DataFrame | None, stage: str = "abstract") -> tuple[list[dict], list[str]]:
    records = parse_ris_records(path.read_text(encoding="utf-8", errors="replace"))
    rows, methods = [], []
    for rec in records:
        explicit = ""
        for tag in ("ID", "C1"):
            if rec.get(tag):
                explicit = rec[tag][0]
                break
        if not explicit:  # look for record_id=REC_NNNN inside any note
            for tag in ("N1", "N2"):
                for v in rec.get(tag, []):
                    rm = RECORD_ID_TAG_RE.search(v)
                    if rm:
                        explicit = rm.group(1)
                        break
                if explicit:
                    break

        doi = rec.get("DO", [""])[0]
        title = rec.get("TI", rec.get("T1", [""]))[0]
        authors = "; ".join(rec.get("AU", []))
        year = rec.get("PY", rec.get("Y1", [""]))[0]
        decided_at = rec.get("DA", [""])[0]

        record_id, method = recover_record_id(explicit, doi, title, authors, year, master)
        reason = detect_exclusion_reason(_ris_note_blob(rec))          # Rayyan exclusion labels, if present
        for decision, screener in detect_ris_decisions(rec, stage):   # one row per reviewer's vote
            rows.append({
                "record_id": record_id,
                "human_decision": decision,
                "decided_at": decided_at,
                "screener": screener,
                "order_index": "",
                "reason": reason,
                "supporting_quote": "",                                # RIS exports don't carry quotes
            })
            methods.append(method)
    return rows, methods


# --------------------------------------------------------------------------------------------------
# Rayyan CSV
# --------------------------------------------------------------------------------------------------
def import_rayyan(path: Path, master: pd.DataFrame | None, stage: str = "abstract") -> tuple[list[dict], list[str]]:
    df = read_decisions_csv(path)
    cols = {c.lower(): c for c in df.columns}
    # the SAME flexible aliases as the generic importer — a post-processed spreadsheet (or one routed here
    # by the upload sniffer because of a 'rayyan' filename / 'key' column) must not lose its reviewer,
    # decision, reason or quote columns just because this is the Rayyan path
    col = {field: _pick(cols, aliases) for field, aliases in CSV_ALIASES.items()}
    rows, methods = [], []
    for _, r in df.iterrows():
        explicit = r.get(cols.get("key", ""), "")
        notes = r.get(cols.get("notes", ""), "")
        if not REC_ID_RE.search(str(explicit)):
            rm = RECORD_ID_TAG_RE.search(str(notes))
            if rm:
                explicit = rm.group(1)
        doi = r.get(cols.get("doi", ""), "")
        title = r.get(cols.get("title", ""), "")
        authors = r.get(cols.get("authors", ""), "")
        year = r.get(cols.get("year", ""), "")

        record_id, method = recover_record_id(explicit, doi, title, authors, year, master)

        # ALL reviewers' votes — one imported row per reviewer. Keeping only the first vote would silently
        # destroy a human-vs-human conflict that reconciliation exists to arbitrate.
        decisions: list[tuple[str, str]] = []
        rm = re.search(r"RAYYAN-INCLUSION:\s*\{(.*?)\}", str(notes))
        if rm:
            pairs = re.findall(r'"([^"]+)"\s*=>\s*"(Included|Excluded|Maybe)"', rm.group(1))
            decisions = [(normalize_decision(dec, stage), scr) for scr, dec in pairs]
        # a reviewer-column name (any alias: screener/reviewer/user/rater/...) tags the fallback votes,
        # so two reviewers' rows never collapse onto one (record, '') key and silently lose a vote
        scr_generic = str(r.get(col["screener"], "")).strip() if col["screener"] else ""
        if not decisions and cols.get("inclusion"):  # some exports add an 'inclusion' column
            decisions = [(normalize_decision(r.get(cols["inclusion"], ""), stage), scr_generic)]
        if not decisions or all(not d for d, _ in decisions):
            # No Rayyan decision marker on this row — fall back to the generic decision aliases rather
            # than silently importing a blank decision.
            if col["human_decision"]:
                d = normalize_decision(r.get(col["human_decision"], ""), stage)
                if d:
                    decisions = [(d, scr_generic)]
        if not decisions:
            decisions = [("", "")]

        # exclusion reason: a dedicated column if the export has one (any alias), else Rayyan's notes labels
        reason = str(r.get(col["reason"], "")).strip() if col["reason"] else ""
        if not reason:
            reason = detect_exclusion_reason(notes)
        # a verbatim-quote column is honoured too (Rayyan itself never exports quotes, but a routed
        # spreadsheet may carry one — the upload card promises it is kept)
        quote = str(r.get(col["supporting_quote"], "")).strip() if col["supporting_quote"] else ""

        for decision, screener in decisions:
            rows.append({
                "record_id": record_id,
                "human_decision": decision,
                "decided_at": "",
                "screener": screener,
                "order_index": "",
                "reason": reason,
                "supporting_quote": quote,
            })
            methods.append(method)
    return rows, methods


# --------------------------------------------------------------------------------------------------
# Generic / instrumented-UI CSV
# --------------------------------------------------------------------------------------------------
def _pick(cols: dict, names: list[str]) -> str | None:
    for n in names:
        if n in cols:
            return cols[n]
    return None


def import_csv(path: Path, master: pd.DataFrame | None, stage: str = "abstract") -> tuple[list[dict], list[str]]:
    df = read_decisions_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    col = {field: _pick(cols, aliases) for field, aliases in CSV_ALIASES.items()}

    # transparency: surface the chosen column mapping and warn on missing key columns
    print(f"  CSV column mapping: { {f: c for f, c in col.items() if c} }")
    if not col["record_id"]:
        print(f"  WARNING: no record_id-like column (looked for {CSV_ALIASES['record_id']}); "
              "relying on DOI/title fallback.", file=sys.stderr)
    if not col["human_decision"]:
        print(f"  WARNING: no decision column (looked for {CSV_ALIASES['human_decision']}); "
              "human_decision will be blank.", file=sys.stderr)

    rows, methods = [], []
    for _, r in df.iterrows():
        explicit = r.get(col["record_id"], "") if col["record_id"] else ""
        doi = r.get(col["doi"], "") if col["doi"] else ""
        title = r.get(col["title"], "") if col["title"] else ""
        authors = r.get(col["authors"], "") if col["authors"] else ""
        year = r.get(col["year"], "") if col["year"] else ""

        record_id, method = recover_record_id(explicit, doi, title, authors, year, master)
        rows.append({
            "record_id": record_id,
            "human_decision": normalize_decision(r.get(col["human_decision"], ""), stage) if col["human_decision"] else "",
            "decided_at": r.get(col["decided_at"], "") if col["decided_at"] else "",
            "screener": r.get(col["screener"], "") if col["screener"] else "",
            "order_index": r.get(col["order_index"], "") if col["order_index"] else "",
            "reason": r.get(col["reason"], "").strip() if col["reason"] else "",
            "supporting_quote": r.get(col["supporting_quote"], "").strip() if col["supporting_quote"] else "",
        })
        methods.append(method)
    return rows, methods


# --------------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Import human screening decisions -> human_decisions.csv "
                                             "(--stage fulltext -> fulltext_human_decisions.csv)")
    ap.add_argument("--input", required=True, help="the exported human-decision file")
    ap.add_argument("--kind", required=True, choices=["ris", "rayyan", "csv"], help="input format")
    ap.add_argument("--stage", default="abstract", choices=["abstract", "fulltext"],
                    help="which screening stage these decisions belong to (default: abstract)")
    ap.add_argument("--replace", action="store_true",
                    help="overwrite the output file instead of merging with it (used by the webapp's "
                         "'Compile my decisions', which REBUILDS the in-app arm from blind_decisions.csv)")
    ap.add_argument("--master", default="Outputs/master_records.csv", help="for DOI/title-hash id recovery")
    ap.add_argument("--outdir", default="Outputs")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        return 1

    master = load_master(Path(args.master))
    if master is None:
        print(f"NOTE: master not found at {args.master} - record_id recovery limited to explicit REC ids.")

    if args.kind == "ris":
        rows, methods = import_ris(in_path, master, args.stage)
    elif args.kind == "rayyan":
        rows, methods = import_rayyan(in_path, master, args.stage)
    else:
        rows, methods = import_csv(in_path, master, args.stage)

    if not rows:
        print("ERROR: no records parsed from the input.", file=sys.stderr)
        return 1

    if args.stage == "fulltext":
        # Same shape as the app's in-app fulltext_decisions.csv so both files read as ONE human arm.
        # An exclude missing its reason/quote is KEPT and flagged (recall-first — never drop human work);
        # the reconciliation C41 gate still requires both before a FINAL exclude is saved.
        for r in rows:
            r["ft_decision"] = r.pop("human_decision")
            r["flag"] = (ft_import_flag(r.get("reason", ""), r.get("supporting_quote", ""))
                         if r["ft_decision"] == "exclude" else "")
        cols, out_name, dec_col = FT_OUT_COLUMNS, "fulltext_human_decisions.csv", "ft_decision"
    else:
        cols, out_name, dec_col = OUT_COLUMNS, "human_decisions.csv", "human_decision"
    new_df = pd.DataFrame(rows)[cols]
    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)
    out_path = outdir / out_name
    out_df, prior_kept, merge_skipped = new_df, 0, False
    if not args.replace and out_path.exists():
        # A second upload must never silently DELETE the first — Rayyan exports Included and Excluded
        # articles as SEPARATE files (at BOTH stages), so per-batch uploads are the normal workflow.
        # Merge: this upload wins per (record_id, reviewer); every other previously-imported row is kept.
        # (--replace, used by the webapp's compile-my-decisions rebuild, restores plain overwrite.)
        try:
            prior = pd.read_csv(out_path, encoding="utf-8-sig").fillna("").astype(str)
        except Exception:
            prior = None
        if prior is not None and set(cols) <= set(prior.columns) and len(prior):
            new_keys = set(zip(new_df["record_id"].astype(str), new_df["screener"].astype(str)))
            keep_mask = [(str(r["record_id"]), str(r["screener"])) not in new_keys for _, r in prior.iterrows()]
            kept = prior[keep_mask]
            prior_kept = len(kept)
            if prior_kept:
                out_df = pd.concat([new_df, kept[cols]], ignore_index=True)
        else:
            merge_skipped = True
    out_df.to_csv(out_path, index=False)

    # summary — computed on THIS upload's rows (new_df), never on the merged file, so the counts always
    # describe what the user just uploaded (a merge would otherwise produce nonsense like negative
    # unmatched counts and a false no-record-id warning)
    n = len(new_df)
    n_recovered = int((new_df["record_id"].astype(str).str.len() > 0).sum())
    n_unmatched = n - n_recovered
    method_counts: dict[str, int] = {}
    for mth in methods:
        method_counts[mth] = method_counts.get(mth, 0) + 1
    dec_counts = new_df[dec_col].replace("", "(none)").value_counts().to_dict()

    print(f"Parsed {n} decision row(s) from {in_path.name} ({args.kind}, stage={args.stage}).")
    print(f"  record_id recovered: {n_recovered}/{n}   unmatched: {n_unmatched}")
    print(f"  recovery methods: " + ", ".join(f"{k}={v}" for k, v in method_counts.items()))
    print(f"  human decisions:  " + ", ".join(f"{k}={v}" for k, v in dec_counts.items()))
    multi = out_df[out_df["record_id"].astype(str).str.len() > 0].groupby("record_id")["screener"].nunique()
    n_multi = int((multi > 1).sum()) if len(multi) else 0
    if n_multi:
        print(f"  NOTE: {n_multi} record(s) carry decisions from more than one reviewer — every vote is "
              "kept, and reviewer-vs-reviewer disagreements will surface at Reconciliation.")
    if prior_kept:
        print(f"  NOTE: merged with the existing {out_path.name} — kept {prior_kept} previously imported "
              f"decision(s); this upload wins per record/reviewer. The file now holds {len(out_df)} rows.")
    if merge_skipped:
        print(f"  WARNING: the existing {out_path.name} could not be merged (unreadable, empty, or its "
              "columns were changed) — it was REPLACED by this upload.", file=sys.stderr)
    if args.stage == "fulltext":
        n_flag = int((new_df["flag"].astype(str).str.len() > 0).sum())
        if n_flag:
            print(f"  NOTE: {n_flag} exclude(s) are missing the reason and/or verbatim quote a final "
                  "exclude needs — kept and flagged for completion at Reconciliation (never dropped).")
    if n_unmatched:
        print(f"  WARNING: {n_unmatched} row(s) had no recoverable record_id (left blank in the output).")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
