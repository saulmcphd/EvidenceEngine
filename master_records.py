"""
master_records.py - EvidenceEngine Phase 1
============================================
Builds the master record set for screening.

It takes a search-results CSV exported from one or more databases, REMOVES DUPLICATE records
(same paper found in several databases) by DOI then by title+first-author+year, and produces:
  - master_records.csv         deduplicated records + stable REC_NNNN id + title_hash (fed to the AI screener)
  - master_records.ris         RIS file; REC_NNNN written to ID (and C1 as backup) so it
                               survives a reference-manager import -> export round trip
  - screening_orders.csv       one *separately randomised* presentation order per human
                               screener (for the blind, multi-screener fatigue study)

Why the randomised orders: a defensible fatigue analysis needs each human to screen in a
DIFFERENT random order, so "position in the list" is decoupled from database/alphabetical
order. The AI is later run over each screener's order for a matched comparison.

Why title_hash: reference managers sometimes overwrite the RIS `ID` field or drop custom
tags. title_hash (a stable hash of title|first-author|year) is a fallback join key if the
REC_NNNN id is lost on re-import.

This script is deterministic and needs no API key. It depends only on `pandas`
(already required by prompter.py).

Usage
-----
    python master_records.py sample_search_results.csv
    python master_records.py my_search.csv --screeners 3 --seed 42 --outdir Outputs

Input columns (case-insensitive; missing ones are tolerated and left blank):
    title, abstract, year, authors, doi, source_db
"""

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = ["title", "abstract", "year", "authors", "doi", "source_db"]


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case/strip headers and ensure every expected column exists."""
    df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df[EXPECTED_COLUMNS] = df[EXPECTED_COLUMNS].fillna("").astype(str)
    # A re-uploaded/re-exported master file already carries record_id + title_hash (e.g. a user
    # re-uploading their own downloaded master_records.csv alongside a fresh search export, or a
    # combined old+new file). Drop both here so build_master() always assigns them itself — via
    # id-matching against `previous` when given, never a blind positional re-number — instead of a
    # stray incoming record_id silently surviving into the id column, or colliding with the insert.
    df = df.drop(columns=[c for c in ("record_id", "title_hash") if c in df.columns])
    return df


def first_author(authors: str) -> str:
    """Best-effort first-author surname from a free-text author string."""
    if not authors.strip():
        return ""
    # A real ',' separates AUTHORS only in "Surname, Initial" form (comma right after one name-like
    # token, e.g. "Smith, J."). "Smith J, Jones K" instead uses the comma to separate PEOPLE, each
    # already "Surname Initial" — the surname is the FIRST token, not the last. Tell the two apart by
    # whether the text before the first ',' looks like a single name (<=2 tokens).
    if "," in authors and " and " not in authors and "&" not in authors and ";" not in authors:
        before_comma = authors.split(",")[0].strip()
        if len(before_comma.split()) <= 1:
            # "Smith, J., Jones, K." — comma directly follows the surname.
            return before_comma
        # "Smith J, Jones K" — comma separates people; each is "Surname Initial(s)".
        return before_comma.split()[0]
    # split on the common multi-author separators
    for sep in (";", " and ", "&", ","):
        if sep in authors:
            head = authors.split(sep)[0].strip()
            # "Smith, J." -> "Smith"; "John Smith" -> "Smith"
            if "," in head:
                return head.split(",")[0].strip()
            parts = head.split()
            return parts[-1] if parts else authors.strip()
    parts = authors.split()
    return parts[-1] if parts else authors.strip()


def split_authors(authors: str) -> list[str]:
    if not authors.strip():
        return []
    for sep in (";", " and ", "&"):
        if sep in authors:
            return [a.strip() for a in authors.split(sep) if a.strip()]
    return [authors.strip()]


def title_hash(title: str, authors: str, year: str) -> str:
    key = f"{title.strip().lower()}|{first_author(authors).lower()}|{str(year).strip()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def normalise_doi(doi: str) -> str:
    """Bare, comparable DOI: lower-case, no doi.org/doi: prefix, no angle brackets, no surrounding whitespace."""
    d = str(doi or "").strip().lower().strip("<>").strip()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)   # https://doi.org/10.xxxx or https://dx.doi.org/10.xxxx
    d = re.sub(r"^(dx\.)?doi\.org/", "", d)            # doi.org/10.xxxx (no scheme)
    d = re.sub(r"^doi:\s*", "", d)                     # doi:10.xxxx
    return d.strip()


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove records that are the same paper found in more than one database.

    Dedup key = the normalised DOI when present, else a title+first-author+year hash. When two
    rows share a key, keep the most complete copy (one with a DOI, then the longest abstract);
    otherwise preserve input order. Returns (deduped_df, n_removed).
    """
    df = df.copy().reset_index(drop=True)
    df["_orig"] = range(len(df))
    keys = []
    for _, r in df.iterrows():
        d = normalise_doi(r["doi"])
        if d:
            keys.append("doi:" + d)
        else:
            # No DOI: match on normalised title + year. Author is deliberately excluded because
            # databases format names differently ("Lee, K" vs "Lee K"), which would hide true
            # duplicates. A blank title can't be matched, so it stays its own record.
            t = re.sub(r"[^a-z0-9]", "", str(r["title"]).lower())
            y = str(r["year"]).strip()
            keys.append(f"ti:{t}|{y}" if t else f"uniq:{r['_orig']}")
    df["_key"] = keys
    df["_score"] = (
        (df["doi"].astype(str).str.strip() != "").astype(int) * 10_000_000
        + df["abstract"].astype(str).str.len()
    )
    keep = (
        df.sort_values("_score", ascending=False, kind="mergesort")   # stable: ties keep input order
        .drop_duplicates("_key", keep="first")["_orig"]
    )
    n_removed = len(df) - len(keep)
    out = (
        df[df["_orig"].isin(set(keep))]
        .sort_values("_orig")
        .drop(columns=["_orig", "_key", "_score"])
        .reset_index(drop=True)
    )
    return out, n_removed


def update_stage_counts(path: Path, updates: dict, defaults: dict | None = None) -> None:
    """Read-merge-write the shared stage_counts.json (so PRISMA-flow counts accumulate).

    `updates` always overwrite (counts this run computed). `defaults` are only written if the key
    is ABSENT, so a human's hand-entered value (e.g. PRISMA 'removed for other reasons') survives.
    """
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    for k, v in (defaults or {}).items():
        data.setdefault(k, v)
    data.update(updates)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_master(df: pd.DataFrame, previous: pd.DataFrame | None = None) -> pd.DataFrame:
    """Assign stable REC_NNNN ids.

    If `previous` — an existing master_records.csv from an earlier run — is given, a row that matches a
    previous row by DOI (preferred) or by title_hash keeps that SAME record_id; only a genuinely new row
    mints a new id, continuing the numbering after the highest id already in use. This is what makes a
    later currency-window rerun (re-searching every 6-12 months, MECIR C37 / playbook-search step 14) safe:
    without it, re-running on a combined old+new set silently renumbers every existing study, orphaning
    every screening/RoB/extraction record already filed under its old id.

    With no `previous`, ids are minted fresh from row position — the original (first-run) behaviour.
    """
    df = df.copy().reset_index(drop=True)
    df["title_hash"] = [
        title_hash(r["title"], r["authors"], r["year"]) for _, r in df.iterrows()
    ]

    if previous is not None and len(previous):
        prev = previous.copy()
        if "title_hash" not in prev.columns:
            prev["title_hash"] = [
                title_hash(str(r.get("title", "")), str(r.get("authors", "")), str(r.get("year", "")))
                for _, r in prev.iterrows()
            ]
        by_doi, by_hash, max_n = {}, {}, 0
        for _, r in prev.iterrows():
            rid = str(r.get("record_id", "")).strip()
            m = re.match(r"^REC_(\d+)$", rid)
            if m:
                max_n = max(max_n, int(m.group(1)))
            if not rid:
                continue
            d = normalise_doi(str(r.get("doi", "")))
            if d:
                by_doi.setdefault(d, rid)
            th = str(r.get("title_hash", "")).strip()
            if th:
                by_hash.setdefault(th, rid)

        record_ids = []
        for _, r in df.iterrows():
            d = normalise_doi(r["doi"])
            rid = by_doi.get(d) if d else None
            if not rid:
                rid = by_hash.get(r["title_hash"])
            if not rid:
                max_n += 1
                rid = f"REC_{max_n:04d}"
            record_ids.append(rid)
        df.insert(0, "record_id", record_ids)
    else:
        df.insert(0, "record_id", [f"REC_{i + 1:04d}" for i in range(len(df))])

    return df


def load_previous_master(path: Path) -> pd.DataFrame | None:
    """Load an existing master_records.csv for id carry-over, or None if it doesn't exist / can't be read."""
    if not path.exists():
        return None
    try:
        prev = pd.read_csv(path).fillna("")
        if "record_id" not in prev.columns:
            return None
        return prev
    except Exception:
        return None


def write_ris(df: pd.DataFrame, path: Path) -> None:
    """Minimal, widely-compatible RIS writer. REC_NNNN goes in ID and C1. Tolerant of a master that lacks the
    derived `title_hash` column (e.g. a benchmark dataset or a set imported from elsewhere) — the hash is
    recomputed on the fly so the N1 join-fallback note is always present and the writer never KeyErrors. All
    optional fields use defensive access so a non-canonical master can never crash the report export."""
    lines: list[str] = []

    def _cell(row, key: str) -> str:
        # NaN-safe: a PRESENT-but-NaN cell (float nan is TRUTHY, so `nan or ""` keeps nan and str(nan)=="nan")
        # must read as empty, not the literal "nan" — else a blank title_hash/doi would emit "title_hash=nan".
        v = row.get(key, "")
        return "" if pd.isna(v) else str(v)

    for _, r in df.iterrows():
        title = _cell(r, "title")
        authors = _cell(r, "authors")
        year = _cell(r, "year").strip()
        th = _cell(r, "title_hash").strip() or title_hash(title, authors, year)
        lines.append("TY  - JOUR")
        if title:
            lines.append(f"TI  - {title}")
        if _cell(r, "abstract").strip():
            lines.append(f"AB  - {_cell(r, 'abstract')}")
        if year:
            lines.append(f"PY  - {year}")
        for au in split_authors(authors):
            lines.append(f"AU  - {au}")
        if _cell(r, "doi").strip():
            lines.append(f"DO  - {_cell(r, 'doi')}")
        # Record id carried in two fields for round-trip robustness:
        lines.append(f"ID  - {r['record_id']}")
        lines.append(f"C1  - {r['record_id']}")
        # And a human-readable backup in a note, in case ID/C1 are stripped:
        lines.append(f"N1  - EvidenceEngine record_id={r['record_id']}; title_hash={th}")
        lines.append("ER  - ")
        lines.append("")  # blank line between records
    path.write_text("\n".join(lines), encoding="utf-8")


def write_screening_orders(record_ids: list[str], n_screeners: int, seed: int, path: Path) -> None:
    """One separately-randomised presentation order per screener (column = screener)."""
    orders = {"position": list(range(1, len(record_ids) + 1))}
    for idx in range(n_screeners):
        label = f"screener_{chr(ord('A') + idx)}" if idx < 26 else f"screener_{idx + 1}"
        shuffled = record_ids[:]  # copy
        random.Random(seed + idx).shuffle(shuffled)  # distinct, reproducible per screener
        orders[label] = shuffled
    pd.DataFrame(orders).to_csv(path, index=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the EvidenceEngine master record set.")
    ap.add_argument("input_csv", help="Deduplicated search-results CSV")
    ap.add_argument("--screeners", type=int, default=5,
                     help="Number of human screeners (default 5 — the reliability layer's mixed-effects "
                          "fatigue model needs >=5; 3-4 falls back to a fixed-effects model; <3 is descriptive only)")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for reproducible orders")
    ap.add_argument("--outdir", default="Outputs", help="Output directory (default ./Outputs)")
    ap.add_argument("--previous", default=None,
                     help="Path to a prior master_records.csv to carry record_ids over from "
                          "(default: auto-detect <outdir>/master_records.csv if present)")
    ap.add_argument("--fresh", action="store_true",
                     help="Ignore any previous master_records.csv and renumber from REC_0001 "
                          "(rarely what you want — breaks every existing screening/RoB/extraction record's link)")
    args = ap.parse_args()

    in_path = Path(args.input_csv)
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        return 1

    df = normalise_columns(pd.read_csv(in_path))
    if len(df) == 0:
        print("ERROR: input CSV has no rows.", file=sys.stderr)
        return 1

    n_identified = len(df)
    by_source = df["source_db"].replace("", "unspecified").value_counts().to_dict()
    df, n_dups = deduplicate(df)

    outdir = Path(args.outdir)
    outdir.mkdir(exist_ok=True)

    previous = None
    if not args.fresh:
        prev_path = Path(args.previous) if args.previous else (outdir / "master_records.csv")
        previous = load_previous_master(prev_path)

    try:
        master = build_master(df, previous=previous)
    except ValueError as e:
        print(f"ERROR: could not assign record ids ({e}). If you're re-uploading an existing "
              f"master_records.csv, pass --fresh to force a clean renumber instead.", file=sys.stderr)
        return 1

    if previous is not None:
        carried = int(master["record_id"].isin(set(previous["record_id"].astype(str))).sum())
        print(f"  carried over {carried} existing id(s) from {prev_path}; minted {len(master) - carried} new one(s)")

    master.to_csv(outdir / "master_records.csv", index=False)
    write_ris(master, outdir / "master_records.ris")
    write_screening_orders(
        master["record_id"].tolist(), args.screeners, args.seed, outdir / "screening_orders.csv"
    )
    update_stage_counts(
        outdir / "stage_counts.json",
        {
            # PRISMA "Identification" — counts this run computed (always overwrite).
            "records_identified": n_identified,
            "duplicates_removed": n_dups,            # PRISMA "Duplicate records removed" (auto: dedup)
            "records_after_dedup": len(master),
            "records_by_source": by_source,
        },
        defaults={
            # The other two "Records removed before screening" boxes. EvidenceEngine does NOT
            # auto-exclude records before screening (the AI is a SECOND SCREENER at the screening
            # stage, not a pre-screening filter — recall-first), so automation_ineligible defaults
            # to 0. removed_other_reasons is a MANUAL count (retracted / non-research / etc.); a
            # human overwrites it in stage_counts.json. Written as defaults so a manual value survives.
            "automation_ineligible": 0,
            "removed_other_reasons": 0,
        },
    )

    print(f"Master records built: {len(master)} unique records -> {outdir}/")
    print(f"  identified {n_identified} -> removed {n_dups} duplicate(s) -> {len(master)} unique records")
    print(f"  master_records.csv          ({len(master)} rows, ids {master['record_id'].iloc[0]}..{master['record_id'].iloc[-1]})")
    print(f"  master_records.ris          (ID + C1 + N1 backup)")
    print(f"  screening_orders.csv        ({args.screeners} randomised order(s), seed={args.seed})")
    print(f"  stage_counts.json           (identified / duplicates_removed / after-dedup for the PRISMA diagram)")
    print("\nNext: import master_records.ris into Zotero/Mendeley/EndNote, export it again,")
    print("and confirm the REC_NNNN ids survived (they should appear in ID, C1, or the note).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
