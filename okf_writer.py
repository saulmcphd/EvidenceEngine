"""
okf_writer.py - OKF node writer + RAISE artifact generators (EvidenceEngine Phase 2)
====================================================================================
The *write* layer of the OKF bundle. `okf_tools.py` reads/heals/visualises the bundle;
`okf_writer.py` CREATES nodes (with mandatory RAISE provenance), generates the two run-level
RAISE artifacts, ingests a source into many concept nodes, flips `human_verified` on
reconciliation, and (re)builds the index/graph by delegating to `okf_tools`.

Non-negotiables enforced here (see CLAUDE.md):
  * Every AI-generated node carries provenance: ai_model, ai_provider, prompt_file,
    prompt_version, human_verified. `write_okf_node` REJECTS an AI node missing any of the
    four string fields (RAISE Part 1 rec 1.8 "declare AI use" + 1.9a "name/version/date").
  * `human_verified` starts False (blind-first); it flips True only when a HUMAN reconciliation
    file is re-imported (`flip_human_verified`). The reconciled human decision, not the AI
    draft, is the review's reference (Cochrane MECIR C39; RAISE Part 1 rec 1.4 accountability).
  * RAISE citation discipline: numbered recs come ONLY from Part 1 (1.x synthesist /
    2.x methodologist / 3.x tool-developer). Part 2 (§4 reporting checklist) and Part 3
    (Responsible Handover Framework) have NO numbered recs - cited by section/page only.

Commands
--------
  python okf_writer.py init                      # create/repair the 5 folders + index/log + 2 RAISE stubs
  python okf_writer.py disclosure                # (re)generate raise-disclosure.md  (RAISE 2 §4, pp.22-24)
  python okf_writer.py handover                  # (re)generate responsible-handover.md (RAISE 3 framework)
  python okf_writer.py flip <reconciliation.csv> # set human_verified:true for reconciled records
  python okf_writer.py index                     # align -> index -> graph (delegates okf_tools)
  python okf_writer.py lint                      # delegate okf_tools.lint
  python okf_writer.py selftest                  # exercise the provenance gate + artifacts in a temp bundle

Pure stdlib (no PyYAML) - mirrors okf_tools.py so both read/write the same frontmatter subset.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

# okf_tools lives next to this file; make it importable regardless of CWD.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import okf_tools  # noqa: E402  (align / generate_index / export_graph / lint / parsers)

# --------------------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------------------
PROVENANCE_STRING_FIELDS = ["ai_model", "ai_provider", "prompt_file", "prompt_version"]
PROVENANCE_FIELDS = PROVENANCE_STRING_FIELDS + ["human_verified"]

CANONICAL_TYPES = {"concept", "entity", "playbook", "reference", "system"}
FOLDER_BY_TYPE = {"concept": "concepts", "entity": "entities", "playbook": "playbooks",
                  "reference": "references", "system": "systems"}
PREFIX_BY_TYPE = {"concept": "concept-", "entity": "entity-", "playbook": "playbook-",
                  "reference": "ref-", "system": "system-"}

# Root run-level artifacts (NOT graph nodes inside a type folder) - flat provenance keys, per the
# existing stub convention so okf_tools lint stays green.
DISCLOSURE_FILE = "raise-disclosure.md"
HANDOVER_FILE = "responsible-handover.md"

RAISE_DOI = "https://doi.org/10.17605/OSF.IO/FWAUD"
RAISE_DRAFT = "RAISE 2026 is a DRAFT for consultation (v3, 13 March 2026); wording/numbering may change."


def _today() -> str:
    return datetime.date.today().isoformat()


# --------------------------------------------------------------------------------------------------
# Provenance helpers
# --------------------------------------------------------------------------------------------------
def provider_from_model(model: str) -> str:
    """Map a LiteLLM/SDK model string to an ai_provider. For litellm 'host/model' strings the MODEL
    family decides the vendor (bedrock/anthropic.claude -> anthropic, azure/gpt-4o -> openai,
    vertex_ai/claude -> anthropic) rather than the routing host. ollama (a local runtime) is the
    provider for its own models. Never returns '' (returns 'unknown' when undeterminable)."""
    m = (model or "").strip().lower()
    if not m:
        return "unknown"
    if m.startswith("ollama"):                 # local runtime: the host IS the provider
        return "ollama"
    seg = m.rsplit("/", 1)[-1]                 # the model segment after any 'host/' prefix
    for s in (seg, m):                         # identify the model family
        if "claude" in s or s.startswith("anthropic"):
            return "anthropic"
        if "gemini" in s or s.startswith("google"):
            return "google"
        if s.startswith("gpt") or "gpt-" in s or re.match(r"^o[1-9]", s):
            return "openai"
        if "command" in s or s.startswith("cohere"):
            return "cohere"
        if "mistral" in s or "mixtral" in s:
            return "mistral"
    first = m.split("/", 1)[0].strip()         # explicit single-vendor host/prefix or bare id
    if first in ("gemini", "google", "vertex", "vertex_ai"):
        return "google"
    if first in ("claude", "anthropic"):
        return "anthropic"
    if first in ("gpt", "openai", "azure"):
        return "openai"
    if "/" in m:                               # a litellm host we don't recognise — use it, never ''
        return first or "unknown"
    return "unknown"


def prompt_version_for(prompt_path, explicit: str | None = None) -> str:
    """Use an explicit version if the producer has one (e.g. screener_fulltext PROMPT_VERSION);
    otherwise derive a stable content hash of the prompt file so the version is reproducible."""
    if explicit:
        return explicit
    try:
        data = Path(prompt_path).read_bytes()
        return "sha1-" + hashlib.sha1(data).hexdigest()[:12]
    except (OSError, TypeError):
        return "unversioned"


def build_provenance(ai_model: str, prompt_file, *, ai_provider: str | None = None,
                     prompt_version: str | None = None, human_verified: bool = False) -> dict:
    """Assemble a provenance dict the way the producers should: provider derived from the model,
    prompt_version hashed from the prompt file unless the producer supplies one."""
    return {
        "ai_model": (ai_model or "").strip(),
        "ai_provider": (ai_provider or provider_from_model(ai_model)).strip(),
        "prompt_file": Path(prompt_file).name if prompt_file else "",
        "prompt_version": prompt_version_for(prompt_file, prompt_version),
        "human_verified": bool(human_verified),
    }


def validate_provenance(prov: dict) -> None:
    """RAISE 1.8/1.9a gate. Raises ValueError on any missing/empty provenance field, an
    indeterminate provider ('unknown'), or a node born already human_verified (blind-first)."""
    if not isinstance(prov, dict):
        raise ValueError("provenance must be a dict with " + ", ".join(PROVENANCE_FIELDS))
    missing = [f for f in PROVENANCE_STRING_FIELDS if not str(prov.get(f, "")).strip()]
    if "human_verified" not in prov:
        missing.append("human_verified")
    if missing:
        raise ValueError(
            "okf_writer: refusing to write an AI-generated node missing required provenance "
            f"fields {missing} (RAISE Part 1 rec 1.8/1.9a). Provide them via build_provenance().")
    if str(prov.get("ai_provider", "")).strip().lower() == "unknown":
        raise ValueError(
            "okf_writer: ai_provider could not be determined from the model id (got 'unknown'). "
            "Pass ai_provider explicitly to build_provenance() (RAISE 1.9a requires the vendor).")
    if prov.get("human_verified") is True:
        raise ValueError(
            "okf_writer: a newly written node cannot be born human_verified:true (blind-first); "
            "human_verified only flips via flip_human_verified after human reconciliation.")


# --------------------------------------------------------------------------------------------------
# Frontmatter rendering (byte-compatible with okf_tools' stdlib parser)
# --------------------------------------------------------------------------------------------------
_BARE_KEYS = {"timestamp", "year", "stage_number", "bytes", "confidence", "order_index",
              "screener_order_index"}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return re.sub(r"-{2,}", "-", s) or "node"


def _sanitize(value: str) -> str:
    # okf_tools.parse_scalar strips one layer of surrounding quotes and does NOT handle escapes.
    # Collapse newlines, swap inner double-quotes for apostrophes (as okf_tools.align does), then
    # strip boundary quotes/apostrophes so a value wrapped in "..." round-trips through parse_scalar
    # unchanged (otherwise a leading/trailing quote is silently eaten and characters are lost).
    s = str(value).replace("\n", " ").replace('"', "'").strip()
    return s.strip("'\"").strip()


# Tokens okf_tools harvests as graph edges from a node BODY: a markdown link `](x.md)` and an
# Obsidian `[[id]]` wikilink. AI free-text (rationale, quotes, extracted values) must never inject
# these or a valid decision node would fail the 0-orphan lint. A zero-width space breaks the token
# while leaving the visible text intact (important for verbatim exclusion quotes).
def _safe_text(value) -> str:
    z = "​"  # zero-width space
    s = str(value)
    return s.replace("](", "]" + z + "(").replace("[[", "[" + z + "[").replace("]]", "]" + z + "]")


def _fm_line(key: str, value) -> str:
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{key}: {value}"
    if isinstance(value, (list, tuple)):
        items = ", ".join(_sanitize(v) for v in value)
        return f"{key}: [{items}]"
    if key in _BARE_KEYS:
        return f"{key}: {_sanitize(value)}"
    return f'{key}: "{_sanitize(value)}"'


def _render_provenance(prov: dict) -> str:
    lines = ["provenance:"]
    for f in PROVENANCE_FIELDS:
        v = prov.get(f, False if f == "human_verified" else "")
        if isinstance(v, bool):
            lines.append(f"  {f}: {'true' if v else 'false'}")
        else:
            lines.append(f"  {f}: {str(v).strip()}")   # bare, matches existing nodes
    return "\n".join(lines)


def _render_node(frontmatter_pairs: list[tuple], provenance: dict | None, body: str) -> str:
    """frontmatter_pairs: ordered (key, value); provenance rendered last as a nested block."""
    fm_lines = [_fm_line(k, v) for k, v in frontmatter_pairs if v is not None and v != ""]
    if provenance is not None:
        fm_lines.append(_render_provenance(provenance))
    body = body.rstrip() + "\n"
    return "---\n" + "\n".join(fm_lines) + "\n---\n\n" + body


def _write_if_changed(path: Path, content: str) -> bool:
    """Idempotent write: skip if the on-disk content is byte-identical. Returns True if written."""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


# --------------------------------------------------------------------------------------------------
# write_okf_node - the provenance-enforcing node writer
# --------------------------------------------------------------------------------------------------
def write_okf_node(bundle: Path, *, type: str, slug: str, title: str, description: str,
                   body: str, tags, provenance: dict, resource: str | None = None,
                   extra_frontmatter: list[tuple] | None = None, timestamp: str | None = None,
                   ai_generated: bool = True) -> Path:
    """Write one OKF node with full RAISE provenance. Rejects an AI node missing provenance.

    type        - one of concept/entity/playbook/reference/system (drives folder + prefix).
    slug        - node id stem (with or without the type prefix); kebab-cased.
    tags        - list[str] (>=1; required by okf_tools lint).
    provenance  - dict with ai_model/ai_provider/prompt_file/prompt_version/human_verified.
    extra_frontmatter - ordered (key,value) pairs inserted between timestamp and provenance
                  (e.g. kind/stage/record_id/decision for run-data entity nodes; id/authors/doi
                  for references). 'resource' is handled separately to keep the canonical order.
    """
    bundle = Path(bundle)
    if type not in CANONICAL_TYPES:
        raise ValueError(f"okf_writer: type {type!r} is not one of {sorted(CANONICAL_TYPES)}")
    if not str(title).strip() or not str(description).strip():
        raise ValueError("okf_writer: title and description are required (okf_tools lint).")
    tags = list(tags) if tags else []
    if not tags:
        raise ValueError("okf_writer: at least one tag is required (okf_tools lint).")
    prov = dict(provenance) if isinstance(provenance, dict) else {}
    # Blind-first: a freshly written node is NEVER pre-verified. Force False at creation; it only
    # flips via flip_human_verified after a human reconciliation file is imported.
    prov["human_verified"] = False
    if ai_generated:
        validate_provenance(prov)
    # Render the provenance block only when it is complete (AI nodes always are, post-validate); a
    # genuinely non-AI node with no/partial provenance gets none, never a half-written block.
    render_prov = prov if all(str(prov.get(f, "")).strip() for f in PROVENANCE_STRING_FIELDS) else None

    prefix = PREFIX_BY_TYPE[type]
    stem = slugify(slug)
    if not stem.startswith(prefix):
        stem = prefix + stem
    folder = bundle / FOLDER_BY_TYPE[type]
    path = folder / f"{stem}.md"

    pairs: list[tuple] = [("type", type), ("title", title), ("description", description)]
    if resource:
        pairs.append(("resource", resource))
    pairs.append(("tags", tags))
    pairs.append(("timestamp", timestamp or _today()))
    if extra_frontmatter:
        pairs.extend(extra_frontmatter)

    content = _render_node(pairs, render_prov, body)
    _write_if_changed(path, content)
    return path


# --------------------------------------------------------------------------------------------------
# Producer-facing wrappers: screening decisions + extraction (run-data ENTITY nodes)
# --------------------------------------------------------------------------------------------------
# Run-data judgements are typed `entity` (NOT `concept`) so the <250-word "thin concept" lint never
# fires on hundreds of short decisions; `kind`/`stage`/`record_id` preserve the PLAN's semantic type.
_STAGE_PLAYBOOK = {
    "abstract": ("playbook-title-abstract-screening", "Stage 5a - title/abstract screening"),
    "fulltext": ("playbook-full-text-screening", "Stage 5b - full-text screening"),
    "extraction": ("playbook-data-extraction", "Stage 7 - data extraction"),
}


def write_screening_decision_node(bundle: Path, *, record_id: str, stage: str, decision: str,
                                  provenance: dict, rationale: str = "", confidence=None,
                                  criteria_violated=None, exclusion_reason: str = "",
                                  supporting_quote: str = "", title: str = "") -> Path:
    """Emit one screening-decision node (stage='abstract'|'fulltext'). AI second-screener draft;
    human_verified stays False until reconciliation (recall-first; a human reconciles every call)."""
    if stage not in ("abstract", "fulltext"):
        raise ValueError("stage must be 'abstract' or 'fulltext'")
    pb_id, pb_label = _STAGE_PLAYBOOK[stage]
    rec_title = title or f"Screening decision ({stage}) - {record_id}"
    desc = (f"AI {stage} screening decision for {record_id}: {decision}. "
            "Second-screener draft; a human reconciles it (human_verified flips on import).")
    extra = [("kind", f"screening-decision-{stage}"), ("stage", f"{stage}-screening"),
             ("record_id", record_id), ("decision", decision)]
    if confidence is not None and confidence != "":
        try:
            extra.append(("confidence", int(float(confidence))))
        except (TypeError, ValueError):
            pass
    if criteria_violated:
        extra.append(("criteria_violated", list(criteria_violated)))
    if exclusion_reason:
        extra.append(("exclusion_reason", exclusion_reason))

    lines = [f"# Decision: {decision}", "",
             f"AI {stage}-stage eligibility decision for record **{record_id}** "
             f"({pb_label}). This is a *second-screener draft*: the reconciled human decision is "
             "the review's reference (Cochrane MECIR C39).", ""]
    if rationale:
        lines += ["# Rationale", "", _safe_text(rationale), ""]
    if criteria_violated:
        lines += ["# Criteria cited", "", *[f"* {_safe_text(c)}" for c in criteria_violated], ""]
    if stage == "fulltext" and (exclusion_reason or supporting_quote):
        lines += ["# Exclusion", "",
                  f"**Primary reason:** {_safe_text(exclusion_reason) or '(n/a - included)'}", ""]
        if supporting_quote:
            lines += [f"> {_safe_text(supporting_quote)}", ""]
    lines += ["# Provenance & reconciliation", "",
              "AI-generated; `human_verified: false` until a human reconciliation file is imported "
              "(`okf_writer.flip_human_verified`). Recall-first: a technical failure fails SAFE to "
              "*include*, never a silent exclude.", "",
              "# Related", "",
              f"* [{pb_label}](/playbooks/{pb_id}.md) - the procedure that produced this decision",
              "* [Recall-first screening](/concepts/concept-recall-first-screening.md) - why uncertainty favours inclusion",
              "* [AI provenance](/concepts/concept-ai-provenance.md) - why this node carries model+prompt provenance",
              "* [Dual screening](/concepts/concept-dual-screening.md) - the AI is a second screener, a human reconciles"]
    return write_okf_node(bundle, type="entity", slug=f"screen-{stage}-{record_id}",
                          title=rec_title, description=desc, body="\n".join(lines),
                          tags=["screening-decision", stage, "run-data", "raise"],
                          provenance=provenance, extra_frontmatter=extra)


def write_extraction_node(bundle: Path, *, record_id: str, provenance: dict, fields: dict,
                          source_file: str = "", rob_tool: str = "", title: str = "") -> Path:
    """Emit one data-extraction node (one per included study). `fields` = {variable: value}."""
    pb_id, pb_label = _STAGE_PLAYBOOK["extraction"]
    rec_title = title or f"Data extraction - {record_id}"
    desc = (f"AI first-pass extraction for {record_id} ({len(fields)} fields). Second-extractor "
            "draft; a human reconciles every value (hallucination/confabulation tracked).")
    extra = [("kind", "data-extraction"), ("stage", "data-extraction"), ("record_id", record_id)]
    if source_file:
        extra.append(("source_file", source_file))
    if rob_tool:
        extra.append(("rob_tool", rob_tool))
    rows = "\n".join(
        f"| {_safe_text(_sanitize(k)).replace(chr(124), '/')} "
        f"| {_safe_text(_sanitize(str(v))).replace(chr(124), '/')} |"
        for k, v in fields.items())
    body = (f"# Extracted data ({record_id})\n\n"
            "AI first-pass extraction. Every value is a draft a human reconciles against the source "
            "PDF (Cochrane Ch.5: automation cannot yet replace a human extractor; C45/C46 need two "
            "people). Recall-first does not apply to extraction - accuracy does.\n\n"
            "| Variable | AI value |\n| --- | --- |\n" + rows + "\n\n"
            "# Provenance & reconciliation\n\n"
            "AI-generated; `human_verified: false` until the audit CSV "
            "(`AI_Extracted_Value | Manual_Value | Match? | Error_Category | Consensus_Value`) is "
            "reconciled and re-imported.\n\n"
            "# Related\n\n"
            f"* [{pb_label}](/playbooks/{pb_id}.md) - the extraction procedure\n"
            "* [AI provenance](/concepts/concept-ai-provenance.md) - provenance requirement\n"
            "* [Dual data extraction](/concepts/concept-dual-data-extraction.md) - two independent extractors")
    return write_okf_node(bundle, type="entity", slug=f"extraction-{record_id}",
                          title=rec_title, description=desc, body=body,
                          tags=["data-extraction", "run-data", "raise"],
                          provenance=provenance, extra_frontmatter=extra)


def write_ai_draft_node(bundle: Path, *, slug: str, kind: str, stage: str, title: str,
                        description: str, provenance: dict, ai_text: str,
                        section_label: str = "", related: list | None = None) -> Path:
    """Emit one AI-DRAFTED NARRATIVE node (e.g. a synthesis section, a protocol background). The AI is
    a second drafter only: `human_verified` stays False until a human accepts/reconciles the draft in
    the app (Cochrane synthesis: the AI is a second extractor/drafter, never the sole synthesist; RAISE
    Part 1 rec 1.8). The reconciled human text — not this draft — is the review's content."""
    extra = [("kind", kind), ("stage", stage)]
    if section_label:
        extra.append(("section", section_label))
    rel = related or [
        "* [AI provenance](/concepts/concept-ai-provenance.md) - why this draft carries model+prompt provenance",
        "* [Dual screening / reconciliation](/concepts/concept-dual-screening.md) - the AI drafts, a human reconciles",
    ]
    body = (f"# AI draft{(' - ' + section_label) if section_label else ''}\n\n"
            "AI-generated **draft** (a second-opinion / first-pass suggestion). It is NOT the review's "
            "content until a human reviews and accepts/edits it; `human_verified: false` until then "
            "(RAISE Part 1 rec 1.8; the AI is a second extractor/drafter, never the sole synthesist).\n\n"
            "# Draft text\n\n"
            f"{_safe_text(ai_text)}\n\n"
            "# Provenance & reconciliation\n\n"
            "AI-generated; `human_verified: false` until a human accepts/reconciles this section in the "
            "app (then it flips true via `okf_writer.set_node_verified`). The reconciled human text - not "
            "this draft - is the review's content.\n\n"
            "# Related\n\n" + "\n".join(rel))
    return write_okf_node(bundle, type="entity", slug=slug, title=title, description=description,
                          body=body, tags=[kind, "ai-draft", "run-data", "raise"],
                          provenance=provenance, extra_frontmatter=extra)


def set_node_verified(bundle: Path, *, type: str, slug: str, value: bool = True,
                      consensus: str | None = None, note: str | None = None) -> bool:
    """Flip `human_verified` on a single node identified by type+slug. Used when a human accepts /
    reconciles an AI-drafted NARRATIVE node (synthesis section / protocol background) that has no
    reconciliation CSV, so the CSV-driven `flip_human_verified` does not apply. Returns True if the
    file changed (False if the node does not exist yet - the flip is best-effort/non-fatal)."""
    if type not in CANONICAL_TYPES:
        raise ValueError(f"okf_writer: type {type!r} is not one of {sorted(CANONICAL_TYPES)}")
    stem = slugify(slug)
    prefix = PREFIX_BY_TYPE[type]
    if not stem.startswith(prefix):
        stem = prefix + stem
    path = Path(bundle) / FOLDER_BY_TYPE[type] / f"{stem}.md"
    if not path.exists():
        return False
    return _set_human_verified(path, value, consensus=consensus, note=note)


# --------------------------------------------------------------------------------------------------
# human_verified flip - reconciliation re-import (blind-first -> human-verified)
# --------------------------------------------------------------------------------------------------
def _set_human_verified(path: Path, value: bool = True, consensus: str | None = None,
                        note: str | None = None) -> bool:
    """Rewrite a node's provenance.human_verified in place. Returns True if the file changed.
    `consensus` writes the standard reconciliation note; `note` overrides it verbatim (used when
    reverting a withdrawn consensus so the note cannot contradict human_verified:false)."""
    text = path.read_text(encoding="utf-8")
    fm, body = okf_tools.split_frontmatter(text)
    if "provenance:" not in fm:
        return False
    new_fm, n = re.subn(r"(\n\s+human_verified:\s*)(?:true|false)",
                        lambda m: m.group(1) + ("true" if value else "false"), fm, count=1)
    if n == 0:
        return False
    if consensus or note:
        marker = "\n\n# Human reconciliation\n"
        # Note ends WITHOUT a trailing newline; both branches then terminate the body with exactly
        # one "\n", so re-importing an already-reconciled CSV is a fixed point (no whitespace drift,
        # no spurious "flip"). The append branch adds the note; the re.sub branch replaces it.
        if note:
            note_block = f"{marker}\n{note}"
        else:
            note_block = (f"{marker}\nReconciled by a human reviewer; consensus decision: **{consensus}**. "
                          "This human-verified value is the review's reference, not the AI draft.")
        if marker not in body:
            body = body.rstrip() + note_block + "\n"
        else:
            body = re.sub(r"\n\n# Human reconciliation\n.*$", note_block + "\n", body, flags=re.DOTALL)
    new = f"---\n{new_fm}\n---\n\n{body.lstrip(chr(10))}"
    if new == text:                      # idempotent: no semantic change -> no rewrite, no count
        return False
    path.write_text(new, encoding="utf-8")
    return True


def _node_for_record(bundle: Path, record_id: str, stage: str | None) -> list[Path]:
    """Find run-data node(s) for a record_id, optionally narrowed to a stage."""
    ents = (Path(bundle) / "entities")
    if not ents.exists():
        return []
    hits = []
    for p in ents.glob("entity-*.md"):
        fm, _ = okf_tools.split_frontmatter(p.read_text(encoding="utf-8"))
        if okf_tools.parse_scalar(fm, "record_id") != record_id:
            continue
        if stage:
            kind = okf_tools.parse_scalar(fm, "kind") or ""
            if stage not in kind and stage not in (okf_tools.parse_scalar(fm, "stage") or ""):
                continue
        hits.append(p)
    return hits


# A row counts as reconciled only when a HUMAN has adjudicated it. If the CSV has a consensus
# column, that column is what must be filled (a hand-typed Manual_Value alone is the human's raw
# read, NOT the reconciled decision - blind-first). Only when there is NO consensus column at all do
# we fall back to a human_decision column (e.g. human_decisions.csv from screening_import.py).
_CONSENSUS_COLS = ("consensus_decision", "consensus_value")
_FALLBACK_VERDICT_COLS = ("human_decision",)


def _row_verdict(row: dict, cols: dict) -> str:
    """The human-adjudicated value in a reconciliation row (empty if not yet reconciled)."""
    if any(k in cols for k in _CONSENSUS_COLS):
        for k in _CONSENSUS_COLS:
            if k in cols:
                v = (row.get(cols[k]) or "").strip()
                if v:
                    return v
        return ""                        # consensus column(s) present but empty -> not reconciled
    for k in _FALLBACK_VERDICT_COLS:     # no consensus column at all -> a human_decision counts
        if k in cols:
            v = (row.get(cols[k]) or "").strip()
            if v:
                return v
    return ""


_EXTRACTION_NONRECONCILABLE_VARS = {"rob_tool", "rob_assessment", "confidence_score"}
# rob2_/robinsi_ = RoB domains (reconciled on the §6 screen). notable_concern_coi = the SEPARATE conflict-of-
# interest JUDGEMENT (Cochrane §7.8.6), also reconciled on the §6 RoB screen (its melted children are
# "notable_concern_coi · judgment/rationale/who/trial_stage") — excluded here so it does NOT gate the
# extraction node's all-fields flip. The funding/COI FACTS (funding_source / author_conflicts_of_interest /
# funder_role) are NOT excluded — they stay reconciled on the extraction screen.
_EXTRACTION_NONRECONCILABLE_PREFIXES = ("rob2_", "robinsi_", "notable_concern_coi")


def is_reconcilable_extraction_var(var) -> bool:
    """A study's extraction OKF node flips when its EXTRACTION DATA fields are reconciled. Rows the human never
    reconciles on the extraction screen must NOT count toward that all-fields gate, or the node could never flip:
    the RoB domains (a separate Stage-6 screen/artefact), the RoB_Tool / RoB_Assessment metadata, and the AI's own
    Confidence_Score self-report have no reconcile input on the extraction screen. (The audit already drops blank
    and "Not applicable" cells at build time; this excludes the remaining structurally-non-reconcilable rows.)

    CASE-INSENSITIVE by design so the flip gate and the app's sidebar/agreement/report gates agree even when a
    human upload carries off-cased RoB column headers (app.py reuses THIS predicate — one canonical rule)."""
    v = str(var or "").strip().lower()
    if v in _EXTRACTION_NONRECONCILABLE_VARS:
        return False
    return not v.startswith(_EXTRACTION_NONRECONCILABLE_PREFIXES)


def flip_human_verified(bundle: Path, reconciliation_csv, stage: str | None = None) -> int:
    """Read a reconciliation/audit CSV and flip human_verified:true on the matching node(s).

    Two modes, chosen by the CSV's shape (blind-first: a row only flips once a HUMAN has reconciled
    it - see _row_verdict):
      * Extraction mode - triggered by a `Variable_Name` column (the field-level extraction audit)
        OR a `FileName` column with no `record_id`. Grouped by FileName; a study's single extraction
        node flips ONLY when EVERY one of its field rows is reconciled (a partially-checked
        extraction is never marked verified, even if the CSV also carries a record_id column).
        record_id is recovered from a REC_NNNN in the filename, else the file stem.
      * Screening mode - a `record_id` CSV with no extraction signature. Flips per row, narrowed to a
        stage (inferred from the columns when not given) and NEVER touching data-extraction nodes."""
    bundle = Path(bundle)
    csv_path = Path(reconciliation_csv)
    flipped = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print(f"flip_human_verified: {csv_path.name} has no rows")
        return 0
    cols = {c.lower().strip(): c for c in rows[0].keys()}
    rid_col = cols.get("record_id")
    fname_col = cols.get("filename")
    is_extraction = bool(cols.get("variable_name")) or (fname_col and not rid_col)

    if is_extraction:                            # per-study, all-fields-reconciled
        if not fname_col:
            print(f"flip_human_verified: {csv_path.name} looks like an extraction audit but has no "
                  "FileName column")
            return 0
        by_file: dict[str, list[dict]] = {}
        for row in rows:
            fn = (row.get(fname_col) or "").strip()
            if fn:
                by_file.setdefault(fn, []).append(row)
        var_col = cols.get("variable_name")
        for fn, frows in by_file.items():
            recon = [r for r in frows
                     if is_reconcilable_extraction_var(r.get(var_col) if var_col else "")]
            # flip only when there ARE extraction data rows AND every one is reconciled (RoB/meta rows excluded)
            if not recon or not all(_row_verdict(r, cols) for r in recon):
                continue
            m = re.search(r"REC_\d{3,}", fn)
            rid = m.group(0) if m else Path(fn).stem
            nodes = _node_for_record(bundle, rid, "extraction")
            if not nodes:
                print(f"flip_human_verified: no extraction node for FileName={fn!r} "
                      f"(recovered rid={rid!r}); not flipped")
                continue
            for node in nodes:
                if _set_human_verified(node, True, consensus="all extracted fields reconciled"):
                    flipped += 1
    elif rid_col:                                # screening mode (row-wise, stage-scoped)
        eff_stage = stage or ("fulltext" if (cols.get("exclusion_reason")
                                             or cols.get("supporting_quote")) else "abstract")
        for row in rows:
            record_id = (row.get(rid_col) or "").strip()
            verdict = _row_verdict(row, cols)
            if not record_id or not verdict:
                continue
            for node in _node_for_record(bundle, record_id, eff_stage):  # never matches extraction
                if _set_human_verified(node, True, consensus=verdict):
                    flipped += 1
    else:
        print(f"flip_human_verified: {csv_path.name} has neither a record_id nor a FileName column")
        return 0
    print(f"flip_human_verified: set human_verified:true on {flipped} node(s) from {csv_path.name}")
    return flipped


def unflip_human_verified(bundle: Path, record_id: str, stage: str | None = None,
                          reason: str | None = None) -> int:
    """Revert human_verified:true -> false for a record's run-data node(s). Used when a saved
    consensus is withdrawn (e.g. the record is routed to a third reviewer): the node must not keep
    claiming a human-verified decision that no longer stands. Only nodes currently marked true are
    touched (idempotent); the reconciliation note is replaced with `reason`. Returns count reverted."""
    bundle = Path(bundle)
    note = reason or ("Consensus withdrawn and the record routed to a third reviewer; no "
                      "human-verified decision stands for this record — awaiting arbitration.")
    reverted = 0
    for node in _node_for_record(bundle, record_id, stage):
        text = node.read_text(encoding="utf-8")
        if re.search(r"\n\s+human_verified:\s*true", text) and _set_human_verified(node, False, note=note):
            reverted += 1
    print(f"unflip_human_verified: reverted human_verified:false on {reverted} node(s) for {record_id}")
    return reverted


# --------------------------------------------------------------------------------------------------
# ingest_source - one source -> 1 reference node + MANY concept nodes (Marie-Haynes granularity)
# --------------------------------------------------------------------------------------------------
def sha256_of(path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def ingest_source(bundle: Path, source_meta: dict, extracted: list[dict],
                  provenance: dict) -> list[Path]:
    """Karpathy/OKF 'ingest': write ONE reference node (pointer + sha256) and MANY single-concept
    nodes (one atomic unit of knowledge each), each linking back to the reference.

    source_meta : {ref_id, title, authors, year, doi, url, source_path(optional for sha256), tags}
    extracted   : [{slug, title, description, body, tags, resource(optional)}, ...]
    """
    bundle = Path(bundle)
    paths: list[Path] = []
    ref_id = source_meta.get("ref_id") or ("ref-" + slugify(source_meta.get("title", "source")))
    ref_id = ref_id if ref_id.startswith("ref-") else "ref-" + ref_id
    extra = [("id", ref_id), ("authors", source_meta.get("authors", [])),
             ("year", source_meta.get("year")), ("doi", source_meta.get("doi", "")),
             ("url", source_meta.get("url", "")), ("role", source_meta.get("role", "guideline"))]
    if source_meta.get("source_path"):
        try:
            extra += [("sha256", sha256_of(source_meta["source_path"])),
                      ("bytes", Path(source_meta["source_path"]).stat().st_size)]
        except OSError:
            pass
    ref_body = (f"# {source_meta.get('title', ref_id)}\n\n"
                f"Source document. {len(extracted)} concept node(s) extracted from it; each cites "
                "this reference. See `# Related` for the derived concepts.\n\n# Related\n\n"
                + "\n".join(f"* [{e['title']}](/concepts/{_concept_stem(e['slug'])}.md)"
                            for e in extracted))
    ref_path = write_okf_node(
        bundle, type="reference", slug=ref_id,
        title=source_meta.get("title", ref_id),
        description=source_meta.get("description", f"Source: {source_meta.get('title', ref_id)}"),
        body=ref_body, tags=source_meta.get("tags", ["source"]),
        resource=source_meta.get("doi") or source_meta.get("url"),
        extra_frontmatter=extra, provenance=provenance)
    paths.append(ref_path)

    for e in extracted:
        body = e["body"].rstrip()
        if "# Related" not in body:
            body += (f"\n\n# Related\n\n* [{source_meta.get('title', ref_id)}]"
                     f"(/references/{ref_id}.md) - source")
        if "# Citations" not in body:
            body += (f"\n\n# Citations\n\n[1] {_citation(source_meta)}")
        paths.append(write_okf_node(
            bundle, type="concept", slug=e["slug"], title=e["title"],
            description=e["description"], body=body, tags=e.get("tags", ["concept"]),
            resource=e.get("resource") or source_meta.get("doi") or source_meta.get("url"),
            provenance=provenance))
    print(f"ingest_source: wrote 1 reference + {len(extracted)} concept(s) from {ref_id}")
    return paths


def _concept_stem(slug: str) -> str:
    s = slugify(slug)
    return s if s.startswith("concept-") else "concept-" + s


def _citation(meta: dict) -> str:
    authors = meta.get("authors", [])
    a = ", ".join(authors) if isinstance(authors, (list, tuple)) else str(authors)
    parts = [p for p in [a, meta.get("title", ""), str(meta.get("year", "") or ""),
                         meta.get("doi", "") or meta.get("url", "")] if p]
    return ". ".join(parts)


# ==================================================================================================
# RAISE artifact generators
# ==================================================================================================
def _val(meta: dict, key: str, blank: str = "______ (to complete)") -> str:
    v = meta.get(key)
    if v is None or v == "":
        return blank
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v)


# RAISE Part 2 §4 reporting checklist (pp.22-24), grouped exactly as the source. Verbatim guidance
# preserved so the generated disclosure tells the author what each item requires. NO numbered recs.
DISCLOSURE_SECTIONS = [
    ("Introduction", [
        ("Existing tools and knowledge (optional)",
         "Overview of the current state-of-the-art and how this tool contributes new knowledge or capabilities."),
        ("AI tool",
         "AI tool name and version; developer name and country; how to access it + user guides/support; how it "
         "works and how it achieves its goal(s); which stage(s) of evidence synthesis are affected; whether it "
         "replaces or runs in parallel with existing methods (and which); and how human oversight/control is set up."),
        ("Objective",
         "The objective(s) / research question(s) the evaluation addresses."),
    ]),
    ("Methods", [
        ("Study design", "Prospective or retrospective; the nature of the comparisons made (if any)."),
        ("Setting", "The domain the tool was developed in (e.g. public or environmental health)."),
        ("Data sources",
         "Where the data came from and its structure; whether it reflects the variability of the setting; a "
         "specific statement that distinct datasets were used for training, testing and validation (if applicable)."),
        ("Data selection",
         "Inclusion/exclusion criteria for the sample and how applied; how the dataset was sized and made broad enough."),
        ("Data preprocessing", "How data were transformed; how missing data and outliers were identified and addressed."),
        ("Labelling of input / validation data",
         "How the 'gold standard' data were created; how its accuracy was measured and assured."),
        ("Type of AI tool / model",
         "Algorithm type and foundation models (e.g. OpenAI's ChatGPT, Anthropic's Claude); deployment/integration."),
        ("Tool development",
         "How the tool/model/prompts were developed; iteratively-designed prompts described in detail; the "
         "processes used to ensure train/test data were not contaminated and that the process is replicable and robust."),
        ("Performance accuracy",
         "Which outcomes are measured, metrics used, comparators defined; accuracy and variability/range/confidence "
         "(especially for generative AI with variable responses)."),
        ("Validation methods",
         "Statistical and/or qualitative analysis approaches, performance comparisons and baselines; internal/external validity."),
        ("Performance errors", "How errors were identified and what error analysis was conducted."),
        ("Interpretation", "Interpretation of the results."),
    ]),
    ("Discussion", [
        ("Strengths and limitations",
         "Breadth of training/testing/validation data and generalisability (scope, sources, geography, language, "
         "methods, publication types); which syntheses it suits / is inappropriate for; interpretation pitfalls."),
        ("Bias",
         "Which biases or equity issues might affect use; what users must be mindful of; mitigation strategies "
         "(e.g. published-only or open-access-only data)."),
        ("Practical value of the tool",
         "Whether it augments current workflows and how; how it should be used in production; cost to implement/integrate/use."),
        ("Implications for use",
         "How to interpret the validation for use; whether use/misuse could invalidate findings or make conclusions "
         "unreliable, and under what circumstances; reporting/visualisation requirements."),
    ]),
    ("Other information", [
        ("Ethical statement", "Ethics approvals (where relevant) and the provider's ethical stance on LLMs."),
        ("Availability of protocol", "Whether a protocol was public prior to the evaluation and where to find it."),
        ("Sources of support", "Financial/non-financial support and the role of funders/sponsors."),
        ("Declarations of interest",
         "Financial/non-financial interests of the evaluation authors, INCLUDING whether the authors are "
         "independent of the AI tool developers; whether a commercial organisation can gain financially from use."),
        ("Availability of data, code and other materials",
         "Which are public / available on request: training dataset; testing dataset; prompt development; "
         "evaluation dataset; performance-analyses data; analytic code; other materials."),
        ("Replicability", "How 3rd parties can replicate the results (or a clear statement that they cannot)."),
        ("Environmental impacts", "Energy, water use, emissions related to computational power/efficiency."),
    ]),
]


def write_raise_disclosure(bundle: Path, run_metadata: dict | None = None) -> Path:
    """Generate raise-disclosure.md structured to the RAISE Part 2 §4 reporting checklist (pp.22-24).

    Implements RAISE Part 1 rec 1.8 (declare AI use) + 1.9 (1.9a name/version/date; 1.9b purpose +
    justification; 1.9b.i methodologically sound; 1.9b.ii validated/piloted; 1.9c interests/funding;
    1.9d limitations). FAIR/FAIR4RS data+code sharing = rec 3.6. Null-result + full-method reporting
    = rec 2.6 (methodologist) / 3.5 (tool-developer). Part 2 has NO numbered recs - cited by section.
    A run fills `run_metadata`; absent keys render as '______ (to complete)' placeholders.
    """
    bundle = Path(bundle)
    m = run_metadata or {}
    # The frontmatter names the MODEL OF RECORD: the screening model if the run screened, else the extraction
    # model if the run only extracted (both are gated upstream by have_ai / _ai_extraction_ran, so this can
    # never over-claim a model that did not run). A blank run leaves it "" — honest, and the Report gate keys
    # its green light off this field == the expected model of record.
    _fm_model = m.get("screening_model") or m.get("extraction_model") or ""
    _fm_provider = (m.get("screening_provider")
                    or (provider_from_model(m.get("extraction_model", "")) if m.get("extraction_model") else ""))
    out = [
        "---",
        "type: raise-disclosure",
        'title: "AI-use disclosure - EvidenceEngine run"',
        'description: "Auto-generated by okf_writer.write_raise_disclosure; structured to the RAISE Part 2 §4 reporting checklist (pp.22-24)."',
        f'topic: "{_sanitize(m.get("topic", ""))}"',
        "source: pipeline",
        f"timestamp: {m.get('timestamp', _today())}",
        "tags: [raise, disclosure, reporting]",
        f'ai_model: "{_sanitize(_fm_model)}"',
        f'ai_provider: "{_sanitize(_fm_provider)}"',
        f'prompt_file: "{_sanitize(m.get("prompt_file", ""))}"',
        f'prompt_version: "{_sanitize(m.get("prompt_version", ""))}"',
        "human_verified: false",
        "---",
        "",
        "# AI-use disclosure (RAISE Part 2 §4)",
        "",
        "Paste this into the host review's AI-use disclosure. It is structured to the **RAISE Part 2 §4 "
        "reporting checklist (pp.22-24)** and implements **RAISE Part 1** recs **1.8** (declare AI use for "
        "each judgement) and **1.9** (1.9a name/version/date; 1.9b purpose + justification; 1.9b.i evidence "
        "the tool is methodologically sound; 1.9b.ii how it was validated/piloted; 1.9c interests + funding; "
        "1.9d limitations). Data/code sharing follows **rec 3.6** (FAIR data + FAIR4RS research software). "
        "Full-method + null-result reporting follows **rec 2.6** (methodologist) / **rec 3.5** (tool-developer).",
        "",
        f"> {RAISE_DRAFT} RAISE Part 2 §4 carries **no numbered recommendations** - it is cited by section/page.",
        "",
        "## Tool name, version & human oversight (rec 1.9a; §4 Introduction)",
        f"- **Tool / version:** {_val(m, 'tool_name', 'EvidenceEngine')} {_val(m, 'tool_version', 'v__')}",
        f"- **Developer (name, country):** {_val(m, 'developer')}",
        "- **How it works + human oversight (rec 3.20):** the AI proposes screening / RoB / extraction "
        "judgements; a human reconciles **every** decision (the AI is a *second* reviewer, never the sole "
        "reviewer; Cochrane MECIR C39). AI is not credited as an author (rec 1.4) and is not anthropomorphised "
        "(rec 3.29).",
        "",
    ]
    for group, items in DISCLOSURE_SECTIONS:
        out.append(f"## {group} (RAISE 2 §4)")
        for label, guidance in items:
            out.append(f"- **{label}.** {guidance}")
            out.append(f"  - *Response:* {_val(m, _meta_key(label))}")
        out.append("")
    # Run-specific model/prompt lines fall through to the honest "______ (to complete)" sentinel on a blank
    # run (no literal default like "gemini-2.5-flash" that a reader could mistake for what THIS run used — the
    # methods.docx builder pastes this body verbatim). The "Gemini fast-path" descriptor is asserted only when
    # an extraction model actually ran.
    extraction_line = (f"- **Extraction:** {_val(m, 'extraction_model')} (Gemini fast-path + context caching); "
                       "prompt `promptfile.txt`." if m.get("extraction_model")
                       else "- **Extraction:** ______ (to complete) — no AI data extraction was run for this review.")
    out += [
        "## Models & prompts used (rec 1.8, 1.9a)",
        f"- **Screening:** {_val(m, 'screening_model')} (exact version/date) via LiteLLM; "
        f"prompt `{_val(m, 'prompt_file')}` v`{_val(m, 'prompt_version')}`.",
        extraction_line,
        "- Full prompt text + versions are archived (repo path + content hash); every OKF node carries its own "
        "model/provider/prompt/prompt_version provenance.",
        "",
        "## Performance (rec 1.9b.i; RAISE 2 §4 Performance accuracy, Appendix 1)",
        f"- **Recall + 95% CI (headline):** {_val(m, 'recall')}  ·  F-beta(β=3): {_val(m, 'fbeta')}  ·  "
        f"sensitivity/specificity: {_val(m, 'sens_spec')}  ·  AUC: {_val(m, 'auc')}  ·  WSS@95%: {_val(m, 'wss')}",
        f"- **Secondary:** F1: {_val(m, 'f1')}  ·  κ (+95% CI, prevalence-sensitive): {_val(m, 'kappa')}",
        # Threshold independence line — THREE-WAY, mirroring app._methods_md's thr_clause and driven by the
        # SAME single source of truth (m['threshold_independent'] / m['independence_suppressed'] are set by
        # _disclosure_run_metadata). It must NEVER assert "INDEPENDENTLY of the developer" when a COI was
        # declared or the bar was slid after results (RAISE Part 1 rec 2.8) — the desync the review caught.
        (f"- **Acceptance threshold (set a priori, INDEPENDENTLY of the developer - RAISE 2 §1/Box 2, p.9):** "
         f"{_val(m, 'threshold')}" if m.get("threshold_independent")
         else f"- **Acceptance threshold (applied to the one-sided 95% lower bound; NOT reported as independent - "
              f"{m['independence_suppressed']} - RAISE 2 §1/Box 2, p.9):** {_val(m, 'threshold')}"
         if m.get("independence_suppressed")
         else f"- **Acceptance threshold (tool DEFAULT recall target — independence of the threshold-setter is not "
              f"recorded, so NOT reported as a priori/independent; RAISE 2 §1/Box 2, p.9):** {_val(m, 'threshold')}"),
        "- *RAISE 2 (p.5, p.34): recall must not be sacrificed for precision; F1 is usually wrong for screening - "
        "prefer F-beta with recall emphasised.*",
        "",
        "## Data handling & contamination (RAISE 2 §2 evaluation methods - data contamination, pp.16-18; §4 items Data sources / Tool development, p.23)",
        f"- **Train/test/validation separation:** {_val(m, 'data_separation')} (prompt-development records "
        "excluded from the evaluation set - 'prompt development is equivalent to training a model').",
        # When THIS run supplies a real contamination statement (a published-review benchmark with a probe on
        # record) show it alone — it already names the probe file. Otherwise show the blank placeholder followed by
        # GUIDANCE on how to complete it — never a bare positive assertion ("validated on a new review so it cannot
        # be in the training data"), which would read as an established FACT sitting next to a "to complete"
        # placeholder (the incoherence the adversarial review caught).
        (f"- **Contamination control:** {_val(m, 'contamination')}" if m.get("contamination")
         else f"- **Contamination control:** {_val(m, 'contamination')} — state the contamination control here: if "
         "the evaluation used a fresh / in-progress review, note that it cannot be in the model's training data; if "
         "a published review was reused, report the memorization-probe result (`reliability/memorization-probe.md`)."),
        f"- **Reference standard (gold standard) + its limits:** {_val(m, 'reference_standard', 'blind, independent human decisions')} "
        "(performance can only be as good as the reference standard - RAISE 2 Appendix 1, p.32).",
        "",
        "## Availability, replicability & environmental impact (rec 3.6 FAIR/FAIR4RS; §4 Other information)",
        f"- **Datasets / prompt-development / analysis code / performance data:** {_val(m, 'availability')} "
        "(links + checksums; FAIR for data, FAIR4RS for software - rec 3.6).",
        f"- **Licence:** {_val(m, 'licence', 'MIT')}  ·  **Zenodo DOI:** {_val(m, 'zenodo_doi')}",
        f"- **Replicability:** {_val(m, 'replicability', 'temperature=0 screening; pinned model versions; archived prompts + seeds where supported')}",
        f"- **Environmental impact:** {_val(m, 'environmental')}",
        "",
        "## Declarations of interest & evaluator independence (RAISE 2 §4, p.24; rec 1.9c)",
        f"- **Are the evaluators independent of the tool developer?** {_val(m, 'evaluators_independent')}.",
        "- EvidenceEngine is **author-built and (currently) author-evaluated** - a real conflict. Mitigation: "
        "recruit an independent methodologist to audit the evaluation design / verify no leakage, OR disclose the "
        "lack of independence prominently (RAISE 2 §2, p.14; §4, p.24).",
        f"- **Commercial interest:** {_val(m, 'commercial_interest', 'none - open-source, MIT; no commercial gain from use')}.",
        f"- **Funding / sources of support:** {_val(m, 'funding')}.",
        "",
        "## Limitations of using AI (rec 1.9d)",
        f"- {_val(m, 'limitations', 'single-topic pilot; small-n recall CI is wide; language/domain generalisability untested; LLM outputs vary run-to-run')}.",
        "",
        "# Citations",
        "",
        "[1] Thomas J, Hair K, Noel-Storr A, et al. RAISE 2026 - Recommendations for practice (Part 1). "
        f"DRAFT v3. {RAISE_DOI}",
        "[2] Thomas J, Hair K, Noel-Storr A, et al. RAISE 2026 - Building and evaluating AI evidence synthesis "
        f"tools (Part 2), §4. DRAFT v3. {RAISE_DOI}",
    ]
    content = "\n".join(out).rstrip() + "\n"
    path = bundle / DISCLOSURE_FILE
    changed = _write_if_changed(path, content)
    print(f"write_raise_disclosure: {'wrote' if changed else 'unchanged'} {path.name} "
          f"({len(DISCLOSURE_SECTIONS)} section-4 groups)")
    return path


def _meta_key(label: str) -> str:
    """Map a §4 item label to a run_metadata key, e.g. 'Study design' -> 'study_design'."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


# RAISE Part 3 - Responsible Handover Framework: five assessment domains (verbatim key questions),
# seven stopping signals (a-g), and the three-way go/no-go gate. NO numbered recs (cited by section).
HANDOVER_DOMAINS = [
    ("1. Purpose", "What is the AI tool for, and does it fit your task/context?", [
        "Is the intended use case clearly defined, and does it match your specific task and context?",
        "Is the level of human oversight appropriate (do humans keep control of operations and outputs)?",
        "For LLMs, are the model version and prompt recorded?",
        "Replace an existing task or run in parallel - and if parallel, which method does it complement?",
        "Is the tool clearly better than the alternatives (other AI tools or the manual process)?",
    ]),
    ("2. Training, testing & validation data", "Where did the tool's data come from, and does it fit?", [
        "Are training/testing data sources disclosed and accessible?",
        "Do they match your evidence-synthesis domain/context (scope, geography, language, methods, dates)?",
        "Is there SEPARATION between training, testing and validation data (any contamination risk)?",
        "Is the corpus large enough, broad enough, and current enough (power, comprehensiveness, coverage)?",
    ]),
    ("3. Validation & performance", "Is it validated and performing well enough for your use?", [
        "Has performance been validated, and reported in enough detail to be transparent and replicable?",
        "Are the metrics appropriate, and does performance meet YOUR acceptable threshold?",
        "Is the validation published and/or peer-reviewed? Can performance change over time?",
        "Was validation done by the developers or by INDEPENDENT methodologists (who lack a COI in performance)?",
        "Is there an appropriate comparator (current best practice / human gold standard / a prior-evaluated AI)?",
        "Is it at least as accurate as current processes, or accurate enough against benchmarks?",
    ]),
    ("4. Usability & user capability", "Can your team use it reliably, and at what cost?", [
        "Does your team have the skills to use it reliably (and if not, is that remediable)?",
        "Is training/documentation available and user-friendly? Is user support available?",
        "What are the costs (financial, time, infrastructure)? Does it fit current methods/platforms?",
        "What are the likely negative outcomes if used, and how will identified risks be mitigated?",
        "Will user data be used to train/fine-tune the tool?",
    ]),
    ("5. Transparency, licences, availability & documentation", "Are the terms, licence and COI acceptable?", [
        "Are the terms of use clear and acceptable? Does it meet your legal/ethical requirements?",
        "Will uploaded content be used for training - and can you opt out? Can it run locally?",
        "Is there a conflict-of-interest disclosure AND a statement of funding sources?",
        "Is the code accessible, what licence applies, and is it likely to remain maintained?",
        "Are you confident this is a responsible handover, and what conditions/mitigations apply (and when to reassess)?",
    ]),
]

HANDOVER_STOPPING_SIGNALS = [
    "a. No published validation in a relevant context",
    "b. Concerns about the replicability of the validation",
    "c. Performance claims based ONLY on the developer's own validation, and/or methodological limitations",
    "d. Lack of legal or policy compliance (organisational, national or international)",
    "e. Terms allow use of your content for model training without opt-out",
    "f. Inappropriate level of human oversight (no way to monitor, audit or override outputs)",
    "g. The AI tool developer is unresponsive to questions",
]


def write_responsible_handover(bundle: Path, assessment: dict | None = None) -> Path:
    """Generate responsible-handover.md from the RAISE Part 3 Responsible Handover Framework:
    the five assessment domains, the stopping-signals check, the developer-independence/COI
    statement, and the Proceed / Proceed-with-mitigations / Do-not-proceed gate. Part 3 has NO
    numbered recs - the framework is cited by section. `assessment` fills the gate/decision fields."""
    bundle = Path(bundle)
    a = assessment or {}
    out = [
        "---",
        "type: responsible-handover",
        'title: "Responsible Handover assessment - EvidenceEngine"',
        'description: "Structured to RAISE Part 3 (the Responsible Handover Framework): 5 domains + stopping signals + go/no-go gate."',
        f'topic: "{_sanitize(a.get("topic", ""))}"',
        "source: pipeline",
        f"timestamp: {a.get('timestamp', _today())}",
        "tags: [raise, governance, go-no-go]",
        'ai_model: ""',
        'ai_provider: ""',
        'prompt_file: ""',
        'prompt_version: ""',
        "human_verified: false",
        "---",
        "",
        "# Responsible Handover assessment (RAISE Part 3)",
        "",
        "The go/no-go artefact for adopting EvidenceEngine on a given review, structured to the **RAISE Part 3 "
        "Responsible Handover Framework** (based on Sense About Science's framework; Part 3 has **no numbered "
        "recommendations** - cited by section). Complete the five domains, the stopping-signals check, the "
        "independence statement, and the decision gate.",
        "",
        f"> {RAISE_DRAFT} Each embedded AI system needs its own assessment; revisit whenever the tool, model, "
        "prompt set or deployment context changes (record a reassessment date). Record any unanswerable question "
        "as 'Unknown / Not disclosed' and treat it as a risk signal.",
        "",
        "**Agreed decision criteria (set BEFORE assessing):** "
        f"{_val(a, 'decision_criteria', 'what level of evidence/transparency is required before adoption, and what triggers a decision not to proceed')}.",
        "",
    ]
    for name, gist, questions in HANDOVER_DOMAINS:
        out.append(f"## Domain {name}")
        out.append(f"*{gist}*")
        out.append("")
        for q in questions:
            out.append(f"- [ ] {q}")
        out.append(f"  - *Assessment:* {_val(a, 'domain_' + name.split('.')[0].strip())}")
        out.append("")
    out += [
        "## Stopping signals (pause and reconsider if ANY are true - RAISE Part 3)",
        "",
        *[f"- [ ] {s}" for s in HANDOVER_STOPPING_SIGNALS],
        "",
        "> For EvidenceEngine, signal **c** applies by default (author-evaluated) - mitigate with an independent "
        "audit or a prominent disclosure before proceeding.",
        "",
        "## Conflict of interest / developer independence (RAISE Part 3; RAISE 2 §4, p.24)",
        "",
        "EvidenceEngine is author-built and (currently) author-evaluated - a real conflict. Ultimate "
        "responsibility for the synthesis lies with the evidence synthesist regardless of who completed this "
        "questionnaire (verify outputs, document AI use, ensure conclusions remain supported by the evidence).",
        f"- **Independent methodologist engaged?** {_val(a, 'independent_auditor')}",
        f"- **Funding / commercial interest:** {_val(a, 'funding', 'none - open-source, MIT; no commercial gain from use')}",
        f"- **Will your content be used to train the tool?** {_val(a, 'training_optout', 'no - runs locally; data never leaves the machine')}",
        "",
        "## Decision gate (RAISE Part 3, §3 'How to decide on AI tool use after this assessment', p.22)",
        "",
        "- [ ] **Proceed** - validation evidence is strong, transparency is high, risks are well-understood and reasonably manageable.",
        "- [ ] **Proceed with mitigations** - shows promise but has evidence gaps / needs monitoring / moderate risks that can be actively managed. List mitigations:",
        f"      {_val(a, 'mitigations', 'retain human dual-screening; hold out a second review; recruit an independent evaluator')}",
        "- [ ] **Do not proceed** - validation absent/weak, transparency insufficient, or risks cannot be mitigated.",
        "",
        f"**Decision:** {_val(a, 'decision')}   **By:** {_val(a, 'decided_by')}   **Date:** {_val(a, 'decided_at')}   "
        f"**Reassess on:** {_val(a, 'reassess_on')}",
        "",
        "# Citations",
        "",
        f"[1] Thomas J, Hair K, Noel-Storr A, et al. RAISE 2026 - Selecting and using AI evidence synthesis tools "
        f"(Part 3): the Responsible Handover Framework. DRAFT v3. {RAISE_DOI}",
    ]
    content = "\n".join(out).rstrip() + "\n"
    path = bundle / HANDOVER_FILE
    changed = _write_if_changed(path, content)
    print(f"write_responsible_handover: {'wrote' if changed else 'unchanged'} {path.name} "
          f"({len(HANDOVER_DOMAINS)} domains, {len(HANDOVER_STOPPING_SIGNALS)} stopping signals)")
    return path


# --------------------------------------------------------------------------------------------------
# init_bundle / write_index / lint - structure + delegation to okf_tools
# --------------------------------------------------------------------------------------------------
def init_bundle(bundle: Path) -> None:
    """Create the five canonical folders + index/log + the two RAISE artifact stubs (idempotent)."""
    bundle = Path(bundle)
    for folder in FOLDER_BY_TYPE.values():
        (bundle / folder).mkdir(parents=True, exist_ok=True)
    log = bundle / "log.md"
    if not log.exists():
        log.write_text("# Directory Update Log\n\nReserved OKF v0.1 file: chronological history "
                       "(newest first).\n", encoding="utf-8")
    if not (bundle / DISCLOSURE_FILE).exists():
        write_raise_disclosure(bundle, {})
    if not (bundle / HANDOVER_FILE).exists():
        write_responsible_handover(bundle, {})
    write_index(bundle)
    print(f"init_bundle: ensured structure at {bundle}")


def write_index(bundle: Path) -> None:
    """Align queryable fields, regenerate index.md + per-folder indexes, rebuild the graph."""
    bundle = Path(bundle)
    okf_tools.align(bundle)
    okf_tools.generate_index(bundle)
    okf_tools.export_graph(bundle)


def lint(bundle: Path) -> int:
    return okf_tools.lint(Path(bundle))


# --------------------------------------------------------------------------------------------------
# selftest - exercise the provenance gate + artifacts in a throwaway bundle
# --------------------------------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        b = Path(tmp) / "okf-bundle"
        init_bundle(b)

        # Closed-world: create the cross-link targets the decision node references (these exist in
        # the real 271-node bundle). Concepts need >=250 words or okf_tools flags them "thin".
        prov_stub = build_provenance("claude-opus-4-8", "selftest", ai_provider="anthropic",
                                     prompt_version="selftest-v1")
        filler = ("# Definition\n\n" + "Stub concept node for the okf_writer selftest closed world. "
                  * 50)
        for cslug, ctitle in [("concept-recall-first-screening", "Recall-first screening"),
                              ("concept-ai-provenance", "AI provenance"),
                              ("concept-dual-screening", "Dual screening"),
                              ("concept-dual-data-extraction", "Dual data extraction")]:
            write_okf_node(b, type="concept", slug=cslug, title=ctitle,
                           description=f"{ctitle} (selftest stub).", body=filler,
                           tags=["selftest"], provenance=prov_stub)
        for pslug, ptitle in [("playbook-title-abstract-screening", "Stage 5a - title/abstract screening"),
                              ("playbook-full-text-screening", "Stage 5b - full-text screening"),
                              ("playbook-data-extraction", "Stage 7 - data extraction")]:
            write_okf_node(b, type="playbook", slug=pslug, title=ptitle,
                           description="Selftest stub.", body="# Goal\n\nSelftest stub playbook.",
                           tags=["selftest"], provenance=prov_stub)

        good = build_provenance("gemini/gemini-2.5-flash", "screening_abstract.txt")
        if good["ai_provider"] != "google":
            failures.append(f"provider_from_model: expected google, got {good['ai_provider']}")
        if not good["prompt_version"].startswith(("sha1-", "unversioned")):
            failures.append(f"prompt_version not derived: {good['prompt_version']}")

        # 1) the gate REJECTS a node missing provenance fields
        try:
            write_okf_node(b, type="entity", slug="bad", title="Bad", description="No provenance",
                           body="x", tags=["t"], provenance={"ai_model": "x"})
            failures.append("provenance gate did NOT reject an incomplete-provenance node")
        except ValueError:
            pass

        # 2) a valid screening-decision node writes
        p = write_screening_decision_node(b, record_id="REC_0007", stage="abstract",
                                          decision="include", provenance=good,
                                          rationale="Mentions attachment + social support.",
                                          confidence=82)
        if not p.exists():
            failures.append("screening-decision node was not written")
        fm, _ = okf_tools.split_frontmatter(p.read_text(encoding="utf-8"))
        if "human_verified: false" not in fm:
            failures.append("new node is not human_verified:false")

        # 3) idempotent re-write
        before = p.read_text(encoding="utf-8")
        write_screening_decision_node(b, record_id="REC_0007", stage="abstract",
                                      decision="include", provenance=good,
                                      rationale="Mentions attachment + social support.",
                                      confidence=82)
        if p.read_text(encoding="utf-8") != before:
            failures.append("re-write was not idempotent")

        # 4) the flip sets human_verified:true from a reconciliation CSV (record_id mode)
        recon = Path(tmp) / "Abstract_Audit.csv"
        recon.write_text("record_id,AI_Decision,Human_Decision,Match?,Consensus_Decision\n"
                         "REC_0007,include,include,Y,include\n", encoding="utf-8")
        n = flip_human_verified(b, recon, stage="abstract")
        fm, _ = okf_tools.split_frontmatter(p.read_text(encoding="utf-8"))
        if n != 1 or "human_verified: true" not in fm:
            failures.append(f"human_verified flip failed (flipped={n})")

        # 4b) full-text decision node + extraction node write (the other two producer wrappers)
        ft = write_screening_decision_node(b, record_id="REC_0008", stage="fulltext",
                                          decision="exclude", provenance=good,
                                          rationale="Wrong population.", confidence=88,
                                          exclusion_reason="No attachment measure",
                                          supporting_quote="participants were screened only for depression")
        ex = write_extraction_node(b, record_id="REC_0009", provenance=good,
                                   fields={"Sample_Size": "204", "Design": "cross-sectional"},
                                   source_file="REC_0009_smith2019.pdf", rob_tool="ROBINS-I")
        if not ft.exists() or not ex.exists():
            failures.append("full-text or extraction node was not written")

        # 4c) extraction-mode flip: a study flips ONLY when every field row is reconciled
        ex_recon = Path(tmp) / "Audit_Ready_Research_Data.csv"
        ex_recon.write_text(
            "FileName,Variable_Name,AI_Extracted_Value,Manual_Value,Consensus_Value\n"
            "REC_0009_smith2019.pdf,Sample_Size,204,204,204\n"
            "REC_0009_smith2019.pdf,Design,cross-sectional,cross-sectional,cross-sectional\n",
            encoding="utf-8")
        ne = flip_human_verified(b, ex_recon)
        fm, _ = okf_tools.split_frontmatter(ex.read_text(encoding="utf-8"))
        if ne != 1 or "human_verified: true" not in fm:
            failures.append(f"extraction-mode flip failed (flipped={ne})")
        # a PARTIALLY-reconciled study must NOT flip
        ex2 = write_extraction_node(b, record_id="REC_0010", provenance=good,
                                    fields={"Sample_Size": "99", "Design": "RCT"},
                                    source_file="REC_0010_jones2020.pdf")
        partial = Path(tmp) / "Audit_Ready_partial.csv"
        partial.write_text(
            "FileName,Variable_Name,AI_Extracted_Value,Manual_Value,Consensus_Value\n"
            "REC_0010_jones2020.pdf,Sample_Size,99,99,99\n"
            "REC_0010_jones2020.pdf,Design,RCT,,\n", encoding="utf-8")
        flip_human_verified(b, partial)
        fm2, _ = okf_tools.split_frontmatter(ex2.read_text(encoding="utf-8"))
        if "human_verified: false" not in fm2:
            failures.append("partially-reconciled extraction was wrongly flipped to verified")

        # 4d) provider mapping for litellm host/model strings (vendor by model family, not host)
        for mdl, exp in {"azure/gpt-4o": "openai", "bedrock/anthropic.claude-v2": "anthropic",
                         "vertex_ai/claude-3-5-sonnet": "anthropic", "azure/o1-mini": "openai",
                         "ollama/llama3": "ollama", "gemini/gemini-2.5-flash": "google",
                         "claude-opus-4-8": "anthropic", "/foo": "unknown"}.items():
            got = provider_from_model(mdl)
            if got != exp:
                failures.append(f"provider_from_model({mdl!r}) -> {got!r}, expected {exp!r}")

        # 4e) the gate rejects an indeterminate provider and a node born human_verified:true
        try:
            validate_provenance(build_provenance("some-unmapped-model", "x"))
            failures.append("gate did not reject an 'unknown' ai_provider")
        except ValueError:
            pass
        try:
            validate_provenance(build_provenance("claude-opus-4-8", "x", ai_provider="anthropic",
                                                 human_verified=True))
            failures.append("gate did not reject a node born human_verified:true")
        except ValueError:
            pass

        # 4f) re-importing an already-reconciled CSV is idempotent (no second flip)
        n2 = flip_human_verified(b, recon, stage="abstract")
        if n2 != 0:
            failures.append(f"re-import was not idempotent (re-flipped {n2})")

        # 4g) extraction must NOT flip on a Manual_Value alone when a Consensus column is present
        exm = write_extraction_node(b, record_id="REC_0011", provenance=good,
                                    fields={"Sample_Size": "50"}, source_file="REC_0011_x.pdf")
        man_only = Path(tmp) / "Audit_manualonly.csv"
        man_only.write_text("FileName,Variable_Name,AI_Extracted_Value,Manual_Value,Consensus_Value\n"
                            "REC_0011_x.pdf,Sample_Size,50,51,\n", encoding="utf-8")
        flip_human_verified(b, man_only)
        fmm, _ = okf_tools.split_frontmatter(exm.read_text(encoding="utf-8"))
        if "human_verified: false" not in fmm:
            failures.append("extraction flipped on Manual_Value alone (no consensus)")

        # 4h) extraction signature wins even when the CSV also carries a record_id (all-fields guard)
        exr = write_extraction_node(b, record_id="REC_0012", provenance=good,
                                    fields={"N": "10", "D": "RCT"}, source_file="REC_0012.pdf")
        mixed = Path(tmp) / "Audit_mixed.csv"
        mixed.write_text("record_id,FileName,Variable_Name,Consensus_Value\n"
                         "REC_0012,REC_0012.pdf,N,10\nREC_0012,REC_0012.pdf,D,\n", encoding="utf-8")
        flip_human_verified(b, mixed)
        fmr, _ = okf_tools.split_frontmatter(exr.read_text(encoding="utf-8"))
        if "human_verified: false" not in fmr:
            failures.append("record_id+Variable_Name CSV bypassed the all-fields extraction guard")

        # 4i) a screening flip with stage=None touches ONLY the inferred stage, never the other
        #     stage or the extraction node for the same record_id
        for st in ("abstract", "fulltext"):
            write_screening_decision_node(b, record_id="REC_0013", stage=st, decision="include",
                                          provenance=good, rationale="x", confidence=70)
        write_extraction_node(b, record_id="REC_0013", provenance=good, fields={"N": "5"},
                              source_file="REC_0013.pdf")
        abs_csv = Path(tmp) / "Abstract_only.csv"
        abs_csv.write_text("record_id,Consensus_Decision\nREC_0013,include\n", encoding="utf-8")
        nstage = flip_human_verified(b, abs_csv)
        if nstage != 1:
            failures.append(f"stage=None abstract flip touched {nstage} node(s) (expected exactly 1)")
        for nm, label in [("entity-screen-fulltext-rec-0013.md", "fulltext"),
                          ("entity-extraction-rec-0013.md", "extraction")]:
            fmx, _ = okf_tools.split_frontmatter((b / "entities" / nm).read_text(encoding="utf-8"))
            if "human_verified: false" not in fmx:
                failures.append(f"stage=None abstract flip wrongly verified the {label} node")

        # 4j) AI free-text with markdown-link / wikilink syntax must NOT inject orphan edges
        write_screening_decision_node(
            b, record_id="REC_0014", stage="fulltext", decision="exclude", provenance=good,
            rationale="cf [[concept-ghost]] and [see](/concepts/concept-phantom.md)",
            exclusion_reason="violates [crit](/concepts/concept-madeup.md)",
            supporting_quote="quote with [[concept-bogus]] and ](/references/ref-nope.md)",
            confidence=40)

        # 5) artifacts regenerate with real content + a populated run
        d = write_raise_disclosure(b, {"tool_name": "EvidenceEngine", "recall": "0.97 (0.91-0.99)",
                                       "evaluators_independent": False})
        h = write_responsible_handover(b, {"decision": "Proceed with mitigations"})
        dt = d.read_text(encoding="utf-8")
        if "RAISE Part 2 §4" not in dt or "rec 3.6" not in dt or "0.97 (0.91-0.99)" not in dt:
            failures.append("disclosure missing §4 structure / rec 3.6 / filled recall")
        if "Responsible Handover Framework" not in h.read_text(encoding="utf-8"):
            failures.append("handover missing framework heading")

        # 6) the whole bundle lints clean (0 orphans / 0 thin / 0 missing)
        write_index(b)
        problems = lint(b)
        if problems:
            failures.append(f"lint reported {problems} problem(s) in the selftest bundle")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print("  - " + f)
        return 1
    print("SELFTEST PASSED: provenance gate, idempotency, flip, artifacts, and lint all OK.")
    return 0


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="OKF node writer + RAISE artifact generators")
    ap.add_argument("cmd", choices=["init", "disclosure", "handover", "flip", "index", "lint", "selftest"])
    ap.add_argument("arg", nargs="?", help="reconciliation CSV (for 'flip')")
    ap.add_argument("--bundle", default=None)
    ap.add_argument("--stage", default=None, help="abstract|fulltext (narrows 'flip')")
    ap.add_argument("--metadata", default=None, help="JSON file of run_metadata/assessment")
    args = ap.parse_args()

    if args.cmd == "selftest":
        return _selftest()

    bundle = okf_tools.find_bundle(args.bundle)
    print(f"bundle: {bundle}")
    meta = {}
    if args.metadata:
        meta = json.loads(Path(args.metadata).read_text(encoding="utf-8"))

    if args.cmd == "init":
        init_bundle(bundle)
    elif args.cmd == "disclosure":
        write_raise_disclosure(bundle, meta)
    elif args.cmd == "handover":
        write_responsible_handover(bundle, meta)
    elif args.cmd == "flip":
        if not args.arg:
            ap.error("flip requires a reconciliation CSV path")
        flip_human_verified(bundle, args.arg, stage=args.stage)
    elif args.cmd == "index":
        write_index(bundle)
    elif args.cmd == "lint":
        return 0 if lint(bundle) == 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
