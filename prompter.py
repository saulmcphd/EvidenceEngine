import os
import re
import json
import argparse
import pandas as pd
import pdfplumber
import concurrent.futures
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Gemini is the default fast-path (context caching cuts input cost ~90% on the shared system prompt - see
# get_ai_response). Any other provider routes through LiteLLM instead (imported lazily in get_ai_response so
# a Gemini-only run never needs it installed) - this LOSES the caching saving, documented in PLAN.md.
from google import genai
from google.genai import types

# 1. SETUP ENVIRONMENT
load_dotenv()
BASE_DIR = Path(os.getcwd())
PDF_DIR = BASE_DIR / "PDFs"
OUTPUT_DIR = BASE_DIR / "Outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

def flatten_record(d, parent="", sep=" · "):
    """Flatten the nested extraction JSON (Core_Condition, Outcomes, Adverse_Effects, RoB_Assessment) so EACH
    leaf statistic / RoB domain becomes its own typed field (Cochrane Ch.5 §5.5: never collect an
    outcome as a free-text blob; one field per statistic so it copy-pastes into the analysis grid and
    can be dual-extracted/reconciled). RoB_Assessment's children keep their own RoB2_*/ROBINSI_* names
    (already unique); '_instruction' helper keys are dropped.

    LISTS are indexed 1-based so a REPEATABLE block (Outcomes: [ {..}, {..} ], Adverse_Effects.Events)
    expands into per-item fields — 'Outcomes · 1 · Instrument', 'Outcomes · 2 · Effect_SE',
    'Adverse_Effects · Events · 1 · Name' — instead of collapsing into one opaque cell. Cochrane §5.3.5
    needs multiple outcomes per study at their time points, so the form MUST carry a variable-length list."""
    out = {}
    for k, v in d.items():
        if str(k).startswith("_"):
            continue
        key = k if (not parent or parent == "RoB_Assessment") else f"{parent}{sep}{k}"
        if isinstance(v, dict):
            out.update(flatten_record(v, parent=key, sep=sep))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                idx_key = f"{key}{sep}{i + 1}"          # 1-based so a referee reads 'outcome 1', not 'outcome 0'
                if isinstance(item, dict):
                    out.update(flatten_record(item, parent=idx_key, sep=sep))
                else:
                    out[idx_key] = item
        else:
            out[key] = v
    return out


AUDIT_COLS = ['FileName', 'Variable_Name', 'AI_Extracted_Value', 'Manual_Value',
              'Match? (Y/N)', 'Error_Category', 'Consensus_Value', 'Audit_Notes']
_QUOTE_PREFIX = "Source_Quotes · "
# Run-level / non-field columns that must NEVER become a reconcilable audit row (else they inflate the field
# count and block the OKF node's all-fields-reconciled flip). Confidence_Score is the AI's OWN self-rating,
# not something a human can independently re-derive from the paper — reconciling it against a "Manual_Value"
# makes no sense, so it's excluded the same way the web UI already special-cases it (Extract.jsx), but here
# in the shared CSV every consumer reads, not just that one screen.
_AUDIT_META = {'FileName', 'Status', 'Cost_USD', 'Savings_USD', 'ProcessingTime', 'Error', 'prompt_version',
               'Confidence_Score'}


def build_audit_records(results):
    """Build the audit-ready VERTICAL rows PER STUDY (one dict per field row), not by a wide-union melt.

    Why per-study: the Outcomes / Adverse_Effects blocks are VARIABLE-length lists, so a wide melt across all
    studies would union every study's columns and emit phantom EMPTY rows for an outcome that only ANOTHER study
    reported. Every audit row must be reconciled for a study's OKF node to flip human_verified, so a phantom
    blank row would block that flip forever. Building each study's rows from its OWN fields guarantees a study
    only gets rows for the fields it actually reported.

    Source_Quotes (the per-value locus / hallucination guard) is keyed by top-level BLOCK name; a leaf
    ("Outcomes · 2 · Effect_SE") falls back to its nearest quoted ancestor ("Outcomes") and lands in Audit_Notes.
    RoB rows carry their quote inline and are untouched.

    ONLY human-RECONCILABLE cells become rows. A cell the AI left blank (JSON null / missing), or one it marked
    structurally "Not applicable" (a log value for a difference measure, the OFF-tool RoB block, an inapplicable
    field), is NOT something a human re-extracts — emitting it would force a meaningless Consensus and, since a
    study's OKF node flips human_verified ONLY when every audit row is reconciled, would block that flip forever.
    So blank and "Not applicable" cells are skipped. "Not reported" is KEPT: that is a substantive claim (the
    paper did not report X) a human should verify. A stray list/dict leaf (malformed AI JSON) is JSON-stringified
    so it never lands as a raw Python object (an un-matchable repr) in a CSV cell."""
    def _blank(v):
        return v is None or (isinstance(v, float) and pd.isna(v))

    def _cell(v):
        if isinstance(v, (list, dict)):
            try:
                return json.dumps(v, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(v)
        return "" if _blank(v) else str(v)

    rows = []
    for r in results:
        fn = str(r.get('FileName', ''))
        if r.get('Status') != 'SUCCESS':
            # A failed extraction (bad scan, garbled AI reply, API error) must never just vanish from the
            # reconcilable artefact - that is exactly the silent-narrowing failure mode the playbook forbids.
            # One flagged row makes the study visible to a human instead of only surviving as a Status='FAIL'
            # row in the wide Research_Data_*.xlsx that nobody scrolls through looking for it.
            rows.append({'FileName': fn, 'Variable_Name': 'EXTRACTION_STATUS',
                         'AI_Extracted_Value': f"FAILED: {r.get('Error', '(no error message)')}",
                         'Manual_Value': "", 'Match? (Y/N)': "", 'Error_Category': 'needs_manual_extraction',
                         'Consensus_Value': "", 'Audit_Notes': "AI extraction failed - extract this study by hand"})
            continue
        quotes, data = {}, {}
        for k, v in r.items():
            if k in _AUDIT_META:
                continue
            ks = str(k)
            if ks.startswith(_QUOTE_PREFIX):
                quotes[ks[len(_QUOTE_PREFIX):]] = ("" if _blank(v) else str(v))
            else:
                data[ks] = v

        def _locus_for(vn, _quotes=quotes):
            vn = str(vn)
            while vn:
                if vn in _quotes:
                    return _quotes[vn]
                if " · " not in vn:
                    break
                vn = vn.rsplit(" · ", 1)[0]   # strip the leaf, try the parent block
            return ""

        for vn, v in data.items():
            cell = _cell(v)
            if not cell.strip() or cell.strip().lower() == "not applicable":
                continue                         # not human-reconcilable — see docstring
            rows.append({'FileName': fn, 'Variable_Name': vn, 'AI_Extracted_Value': cell,
                         'Manual_Value': "", 'Match? (Y/N)': "", 'Error_Category': "",
                         'Consensus_Value': "", 'Audit_Notes': _locus_for(vn)})
    return rows


_MIN_TEXT_CHARS = 200   # below this for a real PDF, it's almost certainly a scan with no text layer


def extract_text_advanced(pdf_path):
    """Accurately extracts text for complex research tables. A PDF that opens fine but yields (near-)no
    text - a scanned/image-only page with no OCR layer - is flagged as an error here too, not just a hard
    pdfplumber exception: otherwise it silently reaches the AI as an almost-blank document, which tends to
    come back as a confident-looking record full of 'Not reported' that reads as a real (if data-poor)
    extraction rather than the technical failure it actually is (playbook-data-extraction Step 1: a study
    with no extractable text must be flagged for manual extraction / OCR, never silently sent through)."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if page_text:
                    text += page_text + "\n"
        if len(text.strip()) < _MIN_TEXT_CHARS:
            return (f"ERROR_NO_EXTRACTABLE_TEXT: only {len(text.strip())} character(s) of text found - this "
                    f"looks like a scanned/image-only PDF with no text layer. Run it through OCR (the `pdf` "
                    f"skill) or extract it by hand.")
        return text
    except Exception as e:
        return f"ERROR_TEXT_EXTRACTION: {str(e)}"

def calculate_gemini_savings(usage):
    """Calculates savings based on 2026 Gemini 2.5 Flash pricing."""
    PRICE_IN = 0.30
    PRICE_CACHE_READ = 0.03 # 90% discount
    PRICE_OUT = 2.50
    
    cached_tokens = usage.cached_content_token_count or 0
    total_in = usage.prompt_token_count
    standard_in = total_in - cached_tokens
    output_tokens = usage.candidates_token_count
    
    actual_cost = (
        (standard_in / 1_000_000 * PRICE_IN) + 
        (cached_tokens / 1_000_000 * PRICE_CACHE_READ) + 
        (output_tokens / 1_000_000 * PRICE_OUT)
    )
    no_cache_cost = (total_in / 1_000_000 * PRICE_IN) + (output_tokens / 1_000_000 * PRICE_OUT)
    
    return round(actual_cost, 5), round(no_cache_cost - actual_cost, 5)

def get_ai_response(provider, model_name, prompt_content, cache_name=None, system_prompt=None):
    """Routes the request. 'gemini' uses the fast-path WITH explicit context caching (the ~90% input saving);
    any other provider routes through LiteLLM (provider-agnostic, but no equivalent to Gemini's cached-content
    API, so the system prompt is re-sent in full on every call - the documented cost trade-off for provider
    choice). `system_prompt` is only used on the LiteLLM path (Gemini gets it via `cache_name`)."""
    try:
        if provider == "gemini":
            client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                temperature=0
            ) if cache_name else types.GenerateContentConfig(temperature=0)

            resp = client.models.generate_content(
                model=model_name,
                contents=prompt_content,
                config=config
            )
            cost, saved = calculate_gemini_savings(resp.usage_metadata)
            return resp.text, cost, saved

        import litellm
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + \
                   [{"role": "user", "content": prompt_content}]
        resp = litellm.completion(model=model_name, messages=messages, temperature=0)
        try:
            cost = round(float(litellm.completion_cost(completion_response=resp) or 0), 5)
        except Exception:
            cost = 0.0   # a provider/model litellm can't price - report 0 rather than guess
        return resp["choices"][0]["message"]["content"], cost, 0.0   # no caching saving on this path
    except Exception as e:
        raise Exception(f"API Error ({provider}): {str(e)}")

def _first_json_object(text: str) -> str | None:
    """Slice out the first balanced {...} block, ignoring anything before/after it."""
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
                return text[start:i + 1]
    return None


def parse_extraction_json(raw_result: str) -> dict:
    """Defensively parse the model's JSON. One stray token (a bare ``` fence, a leading sentence, no fence
    at all) used to throw the whole study away as a FAIL with no attempt to recover it - the same robust-parse
    idiom already used by screener_abstract.py/screener_fulltext.py, applied here too (still-open PROGRESS.md
    TODO: 'robust JSON parser added'). Raises ValueError with the LAST error if nothing works, so the caller's
    existing FAIL handling is unchanged."""
    candidate = raw_result.strip()
    attempts = [candidate]
    if "```" in candidate:
        m = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
        if m:
            attempts.append(m.group(1).strip())
    elif "```json" in candidate:   # pre-existing simple case, kept for identical behaviour when it applies
        attempts.append(candidate.split("```json")[1].split("```")[0].strip())
    stripped = _first_json_object(candidate)
    if stripped:
        attempts.append(stripped)

    last_err = None
    for attempt in attempts:
        if not attempt:
            continue
        try:
            return json.loads(attempt)
        except json.JSONDecodeError as e:
            last_err = e
    raise ValueError(f"could not parse a JSON object from the model's response ({last_err})")


def process_file(pdf_file, provider, model_name, cache_name=None, system_prompt=None):
    """Processes a single PDF and returns structured data."""
    start_time = datetime.now()
    text = extract_text_advanced(pdf_file)
    if text.startswith("ERROR"):
        return {'FileName': pdf_file.name, 'Status': 'FAIL', 'Error': text}

    try:
        raw_result, cost, saved = get_ai_response(provider, model_name, text, cache_name, system_prompt)
        extracted_data = flatten_record(parse_extraction_json(raw_result))   # one field per statistic / RoB domain
        extracted_data.update({
            'FileName': pdf_file.name,
            'Status': 'SUCCESS',
            'Cost_USD': cost,
            'Savings_USD': saved,
            'ProcessingTime': round((datetime.now() - start_time).total_seconds(), 2)
        })
        return extracted_data
    except Exception as e:
        return {'FileName': pdf_file.name, 'Status': 'FAIL', 'Error': str(e)}

def _review_context_block(criteria_path: Path) -> str:
    """Build the [REVIEW_CONTEXT] block promptfile.txt's <Context> expects: the review's PRE-SPECIFIED
    RoB framing (effect of interest, target trial, a-priori confounder list) read from criteria.txt, so the
    AI rates bias against the review's own committed choices instead of its background knowledge of
    RoB2/ROBINS-I (playbook-risk-of-bias.md step 3: 'fix the two framing decisions before scoring'; pull the
    confounder/co-intervention list from criteria.txt/the protocol, never off the included study itself).
    Missing fields degrade to an honest 'not specified' rather than silently omitting the section."""
    fields = {}
    if criteria_path.exists():
        for raw in criteria_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Z][A-Z0-9_/]+):\s*(.*)$", line)
            if m:
                fields[m.group(1)] = re.sub(r"\s+#.*$", "", m.group(2)).strip()

    def _v(key, label, default="not specified — apply Cochrane Handbook Ch.8 default guidance"):
        val = fields.get(key, "").strip()
        return f"- {label}: {val or default}"

    lines = [
        _v("REVIEW_TOPIC", "Review topic", default="not specified"),
        _v("ROB_EFFECT_OF_INTEREST", "Effect of interest for RoB 2 Domain 2",
           default="not specified — default to ASSIGNMENT (intention-to-treat), the usual policy question"),
        _v("ROB_TARGET_TRIAL", "Target trial being emulated (ROBINS-I only)",
           default="not specified — infer the implied pragmatic RCT from the study's own stated aim"),
        _v("ROB_CONFOUNDERS", "A-priori confounder / co-intervention list (ROBINS-I Domain 1 only)",
           default="not specified — judge confounding against the standard confounders for this topic per "
                   "Cochrane Ch.8, and flag in your rationale that no review-specific list was supplied"),
    ]
    return "\n".join(lines)


def _form_version(prompt_text: str) -> str:
    """The extraction form's human-readable version (Cochrane §5.4.3 Step 4: a version number + date so a
    referee sees which piloted, revised form produced the data). Read from the '<!-- FORM_VERSION: ... -->'
    header line of promptfile.txt; falls back to a content hash (via build_provenance) when absent, so a node
    is never 'unversioned'."""
    m = re.search(r"FORM_VERSION:\s*(\S+)", prompt_text)
    d = re.search(r"FORM_VERSION_DATE:\s*(\S+)", prompt_text)
    if not m:
        return ""
    return f"{m.group(1)} ({d.group(1)})" if d else m.group(1)


def main():
    # Pilot mode (Cochrane C43 pilot-and-revise loop): --limit N runs the AI extractor over only the first N
    # included PDFs so a reviewer can trial the form, check the values against source, revise, and re-run — the
    # mandatory pilot the screener already offers. 0 = the full run. Mirrors screener_*.py's --limit.
    ap = argparse.ArgumentParser(description="EvidenceEngine AI extractor.")
    ap.add_argument("--limit", type=int, default=0, help="pilot on the first N PDFs only (0 = all)")
    ap.add_argument("--provider", default="gemini",
                     help="'gemini' (default) uses the fast-path WITH context caching (~90% input saving). "
                          "Any other value (e.g. 'anthropic', 'openai', 'ollama') routes through LiteLLM "
                          "instead - provider choice, but no caching, so it costs more per PDF.")
    ap.add_argument("--model", default="gemini-2.5-flash",
                     help="model name; for --provider gemini a bare model id, for any other provider a "
                          "LiteLLM model string (e.g. 'claude-opus-4-8', 'gpt-4o', 'ollama/llama3')")
    args, _unknown = ap.parse_known_args()
    CHOSEN_PROVIDER = args.provider
    CHOSEN_MODEL = args.model

    with open(BASE_DIR / 'promptfile.txt', 'r', encoding='utf-8') as f:
        research_prompt = f.read().strip()
    PROMPT_VERSION = _form_version(research_prompt)

    # Review-level RoB framing (effect of interest / target trial / a-priori confounders) is the SAME for
    # every PDF in this run, so it goes into the cached system instruction once here, not re-sent per call.
    review_context = _review_context_block(BASE_DIR / 'criteria.txt')
    if "[REVIEW_CONTEXT]" in research_prompt:
        research_prompt = research_prompt.replace("[REVIEW_CONTEXT]", review_context)
    print("Review context injected into the RoB/extraction prompt:\n" + review_context)
    if PROMPT_VERSION:
        print(f"Extraction form version: {PROMPT_VERSION}")

    pdfs = sorted(PDF_DIR.glob('*.pdf'))           # deterministic order so 'first N' is stable across pilot/full runs
    if args.limit and args.limit > 0:
        pdfs = pdfs[:args.limit]
        print(f"PILOT: extracting the first {len(pdfs)} PDF(s) only (C43 pilot-and-revise).")
    results = []
    cache_id = None

    if CHOSEN_PROVIDER == "gemini":
        client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
        cache = client.caches.create(
            model=CHOSEN_MODEL,
            config=types.CreateCachedContentConfig(
                display_name="systematic_review_extraction",
                system_instruction=research_prompt,
                ttl="3600s"
            )
        )
        cache_id = cache.name
        print(f"Cache active: {cache_id}")
    else:
        print(f"Provider '{CHOSEN_PROVIDER}' routes through LiteLLM (model '{CHOSEN_MODEL}') - no context "
              f"caching on this path, so the full system prompt is resent on every PDF.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_file, pdf, CHOSEN_PROVIDER, CHOSEN_MODEL, cache_id,
                                    None if CHOSEN_PROVIDER == "gemini" else research_prompt): pdf
                   for pdf in pdfs}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # 1. SAVE MAIN DATASET (wide: one row per study). Stamp the form version onto the human-facing dataset
    #    so it itself records which piloted, revised form produced it (Cochrane §5.4.3 Step 4 / C43).
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    df = pd.DataFrame(results)
    if PROMPT_VERSION:
        df['prompt_version'] = PROMPT_VERSION
    main_output = OUTPUT_DIR / f"Research_Data_{timestamp}.xlsx"
    df.to_excel(main_output, index=False)

    # 2. GENERATE THE AUDIT-READY VERTICAL FILE — built PER STUDY (build_audit_records), not by a wide-union
    #    melt, so a variable-length Outcomes/Adverse_Effects list never emits phantom rows that would block a
    #    study's OKF node flip. See build_audit_records for the full rationale.
    try:
        df_audit = pd.DataFrame(build_audit_records(results), columns=AUDIT_COLS)
        audit_output = OUTPUT_DIR / f"Audit_Ready_Research_Data_{timestamp}.csv"
        df_audit.to_csv(audit_output, index=False)
        print(f"Audit file generated: {audit_output.name} ({len(df_audit)} field rows)")
    except Exception as e:
        print(f"Audit generation failed: {str(e)}")

    # 3. OKF NODES - one provenance-bearing data-extraction node per successful study (RAISE 1.8/1.9a).
    #    Non-fatal: never let an OKF-writing failure break an extraction run. This engine has no
    #    record_id, so key on a REC_NNNN embedded in the filename, else the PDF file stem. Opt out
    #    with EVIDENCEENGINE_NO_OKF=1 (parity with the screeners' --no-okf).
    if os.environ.get('EVIDENCEENGINE_NO_OKF', '').strip().lower() not in ('1', 'true', 'yes'):
        try:
            import sys, re as _re, hashlib as _hl
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import okf_writer
            bundle = okf_writer.okf_tools.find_bundle(None)
            # prompt_version = the legible form version ('extraction-v2 (2026-07-03)') so the referee sees which
            # piloted, revised form produced this node; falls back to the content hash when the header is absent.
            prov = okf_writer.build_provenance(CHOSEN_MODEL, BASE_DIR / 'promptfile.txt',
                                               prompt_version=(PROMPT_VERSION or None))
            meta_cols = {'FileName', 'Status', 'Cost_USD', 'Savings_USD', 'ProcessingTime', 'Error', 'prompt_version'}
            n_okf = 0
            used = {}                       # node-slug -> FileName, to catch silent overwrites
            for r in results:
                fname = str(r.get('FileName', ''))
                match = _re.search(r'REC_\d{3,}', fname)
                rid = match.group(0) if match else Path(fname).stem
                # Dedup on the RESOLVED node slug (slugify collapses '.', '-', spaces), not the raw
                # rid, so two differently-punctuated filenames cannot silently overwrite one node.
                slug = okf_writer.slugify(f"extraction-{rid}")
                if used.get(slug, fname) != fname:
                    rid = f"{rid}-{_hl.sha1(fname.encode('utf-8')).hexdigest()[:6]}"
                    slug = okf_writer.slugify(f"extraction-{rid}")
                    print(f"OKF: extraction-node collision; disambiguated '{fname}' -> {rid}")
                used[slug] = fname
                if r.get('Status') != 'SUCCESS':
                    # A stub node so a failed study is still IN the bundle (never just absent) - a referee
                    # or the compliance lint can see it failed and needs manual extraction, instead of the
                    # study quietly having no extraction node at all with nothing to explain why.
                    okf_writer.write_extraction_node(
                        bundle, record_id=rid, provenance=prov,
                        fields={"Extraction_Status": "FAILED - needs manual extraction",
                                "Error": str(r.get('Error', '(no error message)'))},
                        source_file=fname)
                    n_okf += 1
                    continue
                # Exclude the parallel Source_Quotes · <field> loci: they live in the audit CSV's
                # Audit_Notes (the human-facing check), not as their own extraction fields in the node.
                fields = {k: v for k, v in r.items()
                          if k not in meta_cols and not str(k).startswith("Source_Quotes · ")}
                okf_writer.write_extraction_node(bundle, record_id=rid, provenance=prov,
                                                 fields=fields, source_file=fname)
                n_okf += 1
            if n_okf:                       # skip the whole-bundle rebuild on a no-op run
                okf_writer.write_index(bundle)
                n_success = sum(1 for r in results if r.get('Status') == 'SUCCESS')
                n_fail = len(results) - n_success
                okf_writer.append_log(bundle,
                    f"**AI extraction/RoB run**: {n_success} PDF(s) extracted via `{CHOSEN_PROVIDER}` "
                    f"(`{CHOSEN_MODEL}`, form `{PROMPT_VERSION or 'unversioned'}`)"
                    + (f"; {n_fail} failed and need manual extraction" if n_fail else "") + ".")
            print(f"OKF: wrote/updated {n_okf} data-extraction node(s) (human_verified:false) in {bundle}")
        except Exception as e:
            print(f"OKF: skipped node writing ({e})")

    if cache_id:
        client.caches.delete(name=cache_id)

if __name__ == "__main__":
    main()