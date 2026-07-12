#!/usr/bin/env python3
import os
import sys
import json
import re
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("translate_locales")

def load_env_fallback():
    """
    Manually load .env files to get credentials if python-dotenv is not installed.
    """
    env_path = Path.cwd() / '.env'
    if env_path.exists():
        logger.info(f"Loading environment variables from {env_path}")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    load_env_fallback()

# Try to import httpx
try:
    import httpx
except ImportError:
    logger.error("The 'httpx' library is required to run this script. Please install it using: pip install httpx")
    sys.exit(1)

def flatten_json(data: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, str]:
    """
    Flattens a nested dictionary into a dot-separated flat dictionary.
    """
    items = {}
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_json(v, new_key, sep=sep))
        else:
            items[new_key] = str(v) if v is not None else ""
    return items

def unflatten_json(flat_data: Dict[str, str], sep: str = ".") -> Dict[str, Any]:
    """
    Unflattens a dot-separated flat dictionary back into a nested dictionary structure.
    """
    nested = {}
    for k, v in flat_data.items():
        parts = k.split(sep)
        curr = nested
        for part in parts[:-1]:
            if part not in curr:
                curr[part] = {}
            if not isinstance(curr[part], dict):
                curr[part] = {}
            curr = curr[part]
        curr[parts[-1]] = v
    return nested

def is_english_fallback(en_val: str, tgt_val: str) -> bool:
    """
    Checks if a target value is an English fallback.
    Returns True if identical, excluding purely numeric or placeholder-only strings.
    """
    if en_val != tgt_val:
        return False
    # Strip placeholders {{...}}, citations [...], digits, and non-word characters.
    cleaned = re.sub(r'\{\{[^}]+\}\}', '', en_val)
    cleaned = re.sub(r'\[[^\]]+\]', '', cleaned)
    cleaned = re.sub(r'\d+', '', cleaned)
    cleaned = re.sub(r'[^\w\s]', '', cleaned).strip()
    return len(cleaned) > 0

def is_corrupted_kn(val: str) -> bool:
    """
    Kannada target validation: returns True if containing Devanagari characters (\u0900 to \u097F).
    """
    return any('\u0900' <= char <= '\u097F' for char in val)

def is_corrupted_hi(val: str) -> bool:
    """
    Hindi target validation: returns True if containing corrupted 'स्रा' sequence.
    """
    return "स्रा" in val

def validate_placeholders_and_citations(en_val: str, tgt_val: str) -> Tuple[bool, str]:
    """
    Validates that all placeholders and citation markers match exactly.
    """
    # 1. Placeholders
    en_placeholders = set(re.findall(r'\{\{[^}]+\}\}', en_val))
    tgt_placeholders = set(re.findall(r'\{\{[^}]+\}\}', tgt_val))
    missing_ph = en_placeholders - tgt_placeholders
    if missing_ph:
        return False, f"Missing placeholders: {missing_ph}"
        
    # 2. Citations
    en_citations = set(re.findall(r'\[[a-zA-Z0-9]+\]', en_val))
    tgt_citations = set(re.findall(r'\[[a-zA-Z0-9]+\]', tgt_val))
    missing_cit = en_citations - tgt_citations
    if missing_cit:
        return False, f"Missing citations: {missing_cit}"
        
    return True, ""

async def translate_text(
    text: str,
    target_lang: str,
    api_key: str,
    client: httpx.AsyncClient,
    dry_run: bool = False
) -> str:
    """
    Translates text to target language using Sarvam Translation API.
    Retries up to 5 times with exponential backoff on retryable status/network issues.
    """
    if not text.strip():
        return ""
        
    lang_mapping = {
        "hi": "hi-IN",
        "te": "te-IN",
        "kn": "kn-IN",
        "ta": "ta-IN",
        "mr": "mr-IN"
    }
    tgt_code = lang_mapping.get(target_lang, f"{target_lang}-IN")
    
    if dry_run or not api_key:
        return f"[MOCK_{target_lang.upper()}] {text}"
        
    url = "https://api.sarvam.ai/translate"
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": api_key
    }
    payload = {
        "input": text,
        "source_language_code": "en-IN",
        "target_language_code": tgt_code,
        "model": "mayura:v1"
    }
    
    max_retries = 5
    backoff_factors = [1.0, 2.0, 4.0, 8.0, 16.0]
    
    for attempt in range(max_retries + 1):
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("translated_text", "").strip()
            
            # Retry on rate limits (429) or server errors (5xx)
            is_retryable = (resp.status_code == 429 or 500 <= resp.status_code < 600)
            if is_retryable and attempt < max_retries:
                wait_time = backoff_factors[attempt]
                logger.warning(f"Sarvam API status {resp.status_code}. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"Sarvam translation API returned status {resp.status_code}: {resp.text}")
                return ""
        except (httpx.RequestError, asyncio.TimeoutError) as e:
            if attempt < max_retries:
                wait_time = backoff_factors[attempt]
                logger.warning(f"Network error calling Sarvam API: {e}. Retrying in {wait_time}s (Attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"Error calling Sarvam API: {e}")
                return ""
                
    return ""

async def translate_key_with_sem(
    sem: asyncio.Semaphore,
    k: str,
    en_val: str,
    lang: str,
    api_key: str,
    client: httpx.AsyncClient,
    dry_run: bool,
    tgt_flat: Dict[str, str],
    progress_tracker: Dict[str, int]
):
    """
    Translates a single key using a semaphore to limit concurrency.
    Applies a 0.5s delay immediately inside the semaphore block to rate limit requests.
    """
    async with sem:
        await asyncio.sleep(0.5)
        translated_text = await translate_text(
            text=en_val,
            target_lang=lang,
            api_key=api_key,
            client=client,
            dry_run=dry_run
        )
        
        if not translated_text:
            progress_tracker["skipped"] += 1
            return
            
        valid, err_msg = validate_placeholders_and_citations(en_val, translated_text)
        if not valid:
            logger.warning(f"Validation failed for key '{k}': {err_msg}. Original: '{en_val}', Translated: '{translated_text}'. Skipping.")
            progress_tracker["skipped"] += 1
            return
            
        tgt_flat[k] = translated_text
        progress_tracker["completed"] += 1

async def progress_logger_task(progress_tracker: Dict[str, int], total: int, interval: float = 3.0):
    """
    Background task to periodically print progress summaries.
    """
    try:
        while True:
            completed = progress_tracker["completed"]
            skipped = progress_tracker["skipped"]
            processed = completed + skipped
            if processed >= total:
                break
            logger.info(f"Progress: Processed {processed}/{total} keys (Translated: {completed}, Skipped/Failed: {skipped})...")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass

def validate_locales(locales_dir: str, langs: List[str]) -> Dict[str, List[str]]:
    """
    Scans locale files for errors (missing, superfluous, corrupted, fallback, placeholder mismatch).
    Returns a dictionary of language -> list of error messages.
    """
    locales_path = Path(locales_dir)
    en_path = locales_path / "en.json"
    if not en_path.exists():
        return {"en": [f"Baseline en.json not found at {en_path}"]}
        
    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    en_flat = flatten_json(en_data)
    
    errors = {}
    for lang in langs:
        lang_errors = []
        lang_file = locales_path / f"{lang}.json"
        if not lang_file.exists():
            continue
            
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                tgt_data = json.load(f)
        except Exception as e:
            lang_errors.append(f"Failed to parse JSON file {lang_file}: {e}")
            errors[lang] = lang_errors
            continue
            
        tgt_flat = flatten_json(tgt_data)
        
        # Check missing keys
        missing = set(en_flat.keys()) - set(tgt_flat.keys())
        if missing:
            lang_errors.append(f"{len(missing)} missing keys (e.g. {list(missing)[:5]})")
            
        # Check superfluous keys
        superfluous = set(tgt_flat.keys()) - set(en_flat.keys())
        if superfluous:
            lang_errors.append(f"{len(superfluous)} superfluous keys (e.g. {list(superfluous)[:5]})")
            
        # Check content validation
        for k, tgt_val in tgt_flat.items():
            if k not in en_flat:
                continue
            en_val = en_flat[k]
            
            # 1. Contamination check
            if lang == "kn" and is_corrupted_kn(tgt_val):
                lang_errors.append(f"Key '{k}' contains Devanagari character(s): '{tgt_val}'")
            elif lang == "hi" and is_corrupted_hi(tgt_val):
                lang_errors.append(f"Key '{k}' contains corrupted sequence 'स्रा': '{tgt_val}'")
                
            # 2. English fallback check
            if is_english_fallback(en_val, tgt_val):
                lang_errors.append(f"Key '{k}' is a direct English fallback: '{tgt_val}'")
                
            # 3. Placeholder / Citation check
            valid, err_msg = validate_placeholders_and_citations(en_val, tgt_val)
            if not valid:
                lang_errors.append(f"Key '{k}' placeholder mismatch: {err_msg} (EN: '{en_val}', TGT: '{tgt_val}')")
                
        if lang_errors:
            errors[lang] = lang_errors
            
    return errors

async def run_translation(
    locales_dir: str,
    langs: List[str],
    dry_run: bool,
    limit: int
):
    """
    Main execution loop to clean, identify keys to translate, call Sarvam API concurrently, and save.
    """
    locales_path = Path(locales_dir)
    en_path = locales_path / "en.json"
    if not en_path.exists():
        logger.error(f"Baseline en.json not found at {en_path}")
        return
        
    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    en_flat = flatten_json(en_data)
    
    api_key = os.environ.get("SARVAM_API_KEY", "")
    if not api_key and not dry_run:
        logger.warning("SARVAM_API_KEY environment variable not found. Defaulting to dry-run (simulation).")
        dry_run = True
        
    async with httpx.AsyncClient() as client:
        for lang in langs:
            lang_file = locales_path / f"{lang}.json"
            tgt_flat = {}
            if lang_file.exists():
                try:
                    with open(lang_file, "r", encoding="utf-8") as f:
                        tgt_flat = flatten_json(json.load(f))
                except Exception as e:
                    logger.error(f"Could not load or parse {lang_file}. Initializing as empty.")
            
            # Step 1: Remove superfluous keys
            superfluous = set(tgt_flat.keys()) - set(en_flat.keys())
            if superfluous:
                logger.info(f"Removing {len(superfluous)} superfluous keys from {lang}.json")
                for k in superfluous:
                    del tgt_flat[k]
                    
            # Step 2: Identify keys that need translation
            keys_to_translate = []
            for k, en_val in en_flat.items():
                if k not in tgt_flat:
                    keys_to_translate.append(k)
                elif is_english_fallback(en_val, tgt_flat[k]):
                    keys_to_translate.append(k)
                elif lang == "kn" and is_corrupted_kn(tgt_flat[k]):
                    keys_to_translate.append(k)
                elif lang == "hi" and is_corrupted_hi(tgt_flat[k]):
                    keys_to_translate.append(k)
                    
            if not keys_to_translate:
                logger.info(f"Locale {lang}.json is fully synced and clean. No translations needed.")
                continue
                
            logger.info(f"Found {len(keys_to_translate)} keys needing translation in {lang}.json")
            if limit and len(keys_to_translate) > limit:
                logger.info(f"Limiting to first {limit} keys for translation.")
                keys_to_translate = keys_to_translate[:limit]
                
            progress_tracker = {"completed": 0, "skipped": 0}
            sem = asyncio.Semaphore(2)
            total = len(keys_to_translate)
            
            # Start background progress logger
            logger_task = asyncio.create_task(progress_logger_task(progress_tracker, total, interval=3.0))
            
            # Run tasks concurrently
            tasks = [
                translate_key_with_sem(
                    sem=sem,
                    k=k,
                    en_val=en_flat[k],
                    lang=lang,
                    api_key=api_key,
                    client=client,
                    dry_run=dry_run,
                    tgt_flat=tgt_flat,
                    progress_tracker=progress_tracker
                )
                for k in keys_to_translate
            ]
            
            await asyncio.gather(*tasks)
            logger_task.cancel()
            
            # Final summary
            logger.info(f"Finished processing {lang}.json. Translated: {progress_tracker['completed']}, Skipped/Failed: {progress_tracker['skipped']}")
            
            # Reconstruct and save
            if not dry_run:
                nested_output = unflatten_json(tgt_flat)
                # Ensure the directory exists
                lang_file.parent.mkdir(parents=True, exist_ok=True)
                with open(lang_file, "w", encoding="utf-8") as f:
                    json.dump(nested_output, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved updated file: {lang_file}")
            else:
                logger.info(f"[Dry Run] Did not write updates to {lang_file}")

def main():
    parser = argparse.ArgumentParser(description="Synchronize and translate regional locale files using Sarvam Mayura Translate API.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate translation and do not write files.")
    parser.add_argument("--lang", default="hi,te,kn,ta,mr", help="Comma-separated target languages to process (e.g. hi,te).")
    parser.add_argument("--limit", type=int, default=0, help="Limit the number of translated keys per language (0 means no limit).")
    parser.add_argument("--locales-dir", default="src/locales", help="Directory containing the json locale files.")
    parser.add_argument("--validate", action="store_true", help="Perform validation scans on target files and exit.")
    
    args = parser.parse_args()
    
    langs = [l.strip() for l in args.lang.split(",") if l.strip()]
    
    if args.validate:
        logger.info(f"Starting validation scan in '{args.locales_dir}' for languages: {langs}")
        errors = validate_locales(args.locales_dir, langs)
        if not errors:
            logger.info("Validation PASS: No missing, superfluous, fallback, corrupted, or placeholder mismatch errors detected.")
            sys.exit(0)
        else:
            logger.error("Validation FAIL: Detected issues in target locales:")
            for lang, issues in errors.items():
                print(f"\n--- {lang}.json ({len(issues)} issues) ---")
                for issue in issues[:10]:  # Limit output to first 10 issues
                    print(f"  - {issue}")
                if len(issues) > 10:
                    print(f"  ... and {len(issues) - 10} more issues.")
            sys.exit(1)
            
    # Run the translation loop
    asyncio.run(run_translation(
        locales_dir=args.locales_dir,
        langs=langs,
        dry_run=args.dry_run,
        limit=args.limit
    ))

if __name__ == "__main__":
    main()
