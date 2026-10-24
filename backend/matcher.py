import importlib.util
import json
import os
import re
import sys
import time

def _load_api_key_safely():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    existing = sys.modules.get("secrets")
    if existing is None or not hasattr(existing, "token_bytes"):
        sys.modules.pop("secrets", None)
        saved_path = list(sys.path)
        try:
            sys.path = [p for p in sys.path if os.path.abspath(p or ".") != backend_dir]
            import secrets as _stdlib_secrets  # noqa: F401
        finally:
            sys.path = saved_path

    secrets_file = os.path.join(backend_dir, "secrets.py")
    if os.path.exists(secrets_file):
        try:
            spec = importlib.util.spec_from_file_location("_notifyinvest_secrets", secrets_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if getattr(mod, "GEMINI_API_KEY", None):
                return mod.GEMINI_API_KEY
        except Exception:
            pass
    return os.getenv("GEMINI_API_KEY")

API_KEY = _load_api_key_safely()

from google import genai

if not API_KEY:
    print("WARNING: Gemini API Key not found. Please set GEMINI_API_KEY env var or create backend/secrets.py")

_client = None

def configure_matcher_ai():
    global _client
    if _client is None:
        _client = genai.Client(api_key=API_KEY)
    return _client

def _parse_json_array(raw_text):
    content = raw_text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        content = match.group(0)
    return json.loads(content)

def find_matches(title, summary=""):
    """
    Uses Gemma-4-26b-a4b-it to identify B3 companies in the text.
    Returns: List of tickers (e.g. ['PETR4', 'VALE3'])
    """
    try:
        client = configure_matcher_ai()
    except Exception as e:
        print(f"Error initializing GenAI client for gemma-4-26b-a4b-it: {e}")
        raise e

    # Validation Helper
    try:
        from b3_tickers import B3_TICKERS
    except ImportError:
        from backend.b3_tickers import B3_TICKERS
    
    text = f"{title}\n{summary}"
    
    prompt = f"""
    Analyze the following news text and identify if any company listed on the Brazilian Stock Exchange (B3) is mentioned.
    
    News: "{text}"
    
    Task:
    1. Identify company names or tickers.
    2. Convert company names to their PRIMARY liquid ticker (e.g. Petrobras -> PETR4, Vale -> VALE3).
    3. Return ONLY a JSON array of these tickers.
    
    Rules:
    - If the ticker provided in the text is valid (e.g. JBSS3), use it.
    - If only the name is provided, map it to the most traded ticker.
    - Ignore ETFs or Indexes (IBOV, SPX) unless explicitly asked.
    - If no B3 company is found, return [].
    
    Example Output: ["PETR4", "WEGE3"]
    """
    
    for model_name in ('gemma-4-26b-a4b-it', 'gemma-4-31b-it'):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            tickers = _parse_json_array(response.text)
            valid_tickers = []
            if isinstance(tickers, list):
                for t in tickers:
                    t = str(t).upper().strip()
                    # Basic Validation: Length 5-6 (XXXX3, XXXX11)
                    if len(t) >= 4 and any(char.isdigit() for char in t):
                        valid_tickers.append(t)
            return valid_tickers
        except Exception as e:
            if model_name == 'gemma-4-26b-a4b-it':
                time.sleep(1)
                continue
            print(f"Matcher AI Error: {e}")
            return []

if __name__ == "__main__":
    print("Testing Matcher (Gemma-4-26b-a4b-it)...")
    try:
        tickers = find_matches("Vale anucia dividendos bilionários e ações sobem", "A mineradora Vale (VALE3) surpreendeu o mercado com anúncio.")
        print(f"Found tickers: {tickers}")
    except Exception as e:
        print(f"Test Failed: {e}")
