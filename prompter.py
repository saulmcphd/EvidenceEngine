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

# API Providers
from anthropic import Anthropic
from openai import OpenAI
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
# count and block the OKF node's all-fields-reconciled flip).
_AUDIT_META = {'FileName', 'Status', 'Cost_USD', 'Savings_USD', 'ProcessingTime', 'Error', 'prompt_version'}


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
        if r.get('Status') != 'SUCCESS':
            continue
        fn = str(r.get('FileName', ''))
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


def extract_text_advanced(pdf_path):
    """Accurately extracts text for complex research tables."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if page_text:
                    text += page_text + "\n"
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

def get_ai_response(provider, model_name, prompt_content, cache_name=None):
    """Routes request with cache support for Gemini."""
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
        # Add OpenAI/Anthropic fallbacks here if needed...
        return "ERROR: Provider Not Supported", 0, 0
    except Exception as e:
        raise Exception(f"API Error ({provider}): {str(e)}")

def process_file(pdf_file, provider, model_name, cache_name=None):
    """Processes a single PDF and returns structured data."""
    start_time = datetime.now()
    text = extract_text_advanced(pdf_file)
    if text.startswith("ERROR"):
        return {'FileName': pdf_file.name, 'Status': 'FAIL', 'Error': text}

    try:
        raw_result, cost, saved = get_ai_response(provider, model_name, text, cache_name)
        clean_json = raw_result.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        
        extracted_data = flatten_record(json.loads(clean_json))   # one field per statistic / RoB domain
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
    CHOSEN_PROVIDER = "gemini"
    CHOSEN_MODEL = "gemini-2.5-flash"

    # Pilot mode (Cochrane C43 pilot-and-revise loop): --limit N runs the AI extractor over only the first N
    # included PDFs so a reviewer can trial the form, check the values against source, revise, and re-run — the
    # mandatory pilot the screener already offers. 0 = the full run. Mirrors screener_*.py's --limit.
    ap = argparse.ArgumentParser(description="EvidenceEngine AI extractor (Gemini fast-path).")
    ap.add_argument("--limit", type=int, default=0, help="pilot on the first N PDFs only (0 = all)")
    args, _unknown = ap.parse_known_args()

    with open(BASE_DIR / 'promptfile.txt', 'r', encoding='utf-8') as f:
        research_prompt = f.read().strip()
    PROMPT_VERSION = _form_version(research_prompt)
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_file, pdf, CHOSEN_PROVIDER, CHOSEN_MODEL, cache_id): pdf for pdf in pdfs}
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
                if r.get('Status') != 'SUCCESS':
                    continue
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
                # Exclude the parallel Source_Quotes · <field> loci: they live in the audit CSV's
                # Audit_Notes (the human-facing check), not as their own extraction fields in the node.
                fields = {k: v for k, v in r.items()
                          if k not in meta_cols and not str(k).startswith("Source_Quotes · ")}
                okf_writer.write_extraction_node(bundle, record_id=rid, provenance=prov,
                                                 fields=fields, source_file=fname)
                n_okf += 1
            if n_okf:                       # skip the whole-bundle rebuild on a no-op run
                okf_writer.write_index(bundle)
            print(f"OKF: wrote/updated {n_okf} data-extraction node(s) (human_verified:false) in {bundle}")
        except Exception as e:
            print(f"OKF: skipped node writing ({e})")

    if cache_id:
        client.caches.delete(name=cache_id)

if __name__ == "__main__":
    main()