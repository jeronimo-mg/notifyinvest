from google import genai
from google.genai import types
import json
import os


try:
    from secrets import GEMINI_API_KEY as API_KEY
except Exception:
    try:
        from backend.secrets import GEMINI_API_KEY as API_KEY
    except Exception:
        API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("WARNING: Gemini API Key not found. Please set GEMINI_API_KEY env var or create backend/secrets.py")

_client = None

def configure_matcher_ai():
    global _client
    if _client is None:
        _client = genai.Client(api_key=API_KEY)
    return _client

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
    
    try:
        response = client.models.generate_content(
            model='gemma-4-26b-a4b-it',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        content = response.text.replace("```json", "").replace("```", "").strip()
        tickers = json.loads(content)
        
        valid_tickers = []
        if isinstance(tickers, list):
            for t in tickers:
                t = str(t).upper().strip()
                # Basic Validation: Length 5-6 (XXXX3, XXXX11)
                if len(t) >= 4 and any(char.isdigit() for char in t):
                    valid_tickers.append(t)
                
        return valid_tickers
    except Exception as e:
        print(f"Matcher AI Error: {e}")
        return []

if __name__ == "__main__":
    print("Testing Matcher (Gemma-4-26b-a4b-it)...")
    try:
        tickers = find_matches("Vale anucia dividendos bilionários e ações sobem", "A mineradora Vale (VALE3) surpreendeu o mercado com anúncio.")
        print(f"Found tickers: {tickers}")
    except Exception as e:
        print(f"Test Failed: {e}")
