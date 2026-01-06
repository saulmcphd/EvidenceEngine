import os
import json
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
        
        extracted_data = json.loads(clean_json)
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

def main():
    CHOSEN_PROVIDER = "gemini" 
    CHOSEN_MODEL = "gemini-2.5-flash" 

    with open(BASE_DIR / 'promptfile.txt', 'r', encoding='utf-8') as f:
        research_prompt = f.read().strip()

    pdfs = list(PDF_DIR.glob('*.pdf'))
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

    # 1. SAVE MAIN DATASET
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    df = pd.DataFrame(results)
    main_output = OUTPUT_DIR / f"Research_Data_{timestamp}.xlsx"
    df.to_excel(main_output, index=False)

    # 2. GENERATE AUDIT-READY VERTICAL FILE (MELT)
    try:
        # Successful extractions only
        df_success = df[df['Status'] == 'SUCCESS'].copy()
        # Define metadata columns to exclude from audit
        meta_cols = ['FileName', 'Status', 'Cost_USD', 'Savings_USD', 'ProcessingTime', 'Error']
        # Identify columns to transform
        value_vars = [c for c in df_success.columns if c not in meta_cols]
        
        # Transform from Wide to Long
        df_audit = df_success.melt(
            id_vars=['FileName'], 
            value_vars=value_vars, 
            var_name='Variable_Name', 
            value_name='AI_Extracted_Value'
        )
        
        # Add Reconciliation Columns
        df_audit['Manual_Value'] = ""
        df_audit['Match? (Y/N)'] = ""
        df_audit['Error_Category'] = ""
        df_audit['Consensus_Value'] = ""
        df_audit['Audit_Notes'] = ""
        
        # Save Audit File
        audit_output = OUTPUT_DIR / f"Audit_Ready_Research_Data_{timestamp}.csv"
        df_audit.to_csv(audit_output, index=False)
        print(f"Audit file generated: {audit_output.name}")
    except Exception as e:
        print(f"Audit generation failed: {str(e)}")

    if cache_id:
        client.caches.delete(name=cache_id)

if __name__ == "__main__":
    main()