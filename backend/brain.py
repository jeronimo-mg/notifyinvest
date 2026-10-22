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

def configure_genai():
    global _client
    if _client is None:
        _client = genai.Client(api_key=API_KEY)
    return _client

def analyze_news(ticker, title, summary):
    """
    Analyzes news using Gemma-4-31b-it.
    Returns analysis JSON.
    """
    try:
        client = configure_genai()
    except Exception as e:
        print(f"FATAL: Could not initialize GenAI client for 'gemma-4-31b-it'. {e}")
        raise e
    
    prompt = f"""
    You are a financial analyst specializing in the Brazilian Stock Market (B3).
    Analyze the following news item related to the company {ticker}.
    
    News Title: {title}
    News Summary: {summary}
    
    Task:
    1. Determine the sentiment of the news regarding {ticker} (POSITIVE, NEGATIVE, NEUTRAL).
    2. Suggest a trading signal (BUY, SELL, HOLD). Be conservative.
    3. Estimate the potential short-term price impact as a percentage (e.g. "+2%", "-5%", "0%").
    4. Provide a very short reason (max 1 sentence) in Portuguese.
    
    Output format (JSON only):
    {{
        "signal": "BUY/SELL/HOLD",
        "sentiment": "POSITIVE/NEGATIVE/NEUTRAL",
        "impact": "+/-X%",
        "reason": "Resumo do motivo em pt-br"
    }}
    """
    
    try:
        response = client.models.generate_content(
            model='gemma-4-31b-it',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return result
    except Exception as e:
        print(f"Error analyzing with Gemma: {e}")
        return {"signal": "HOLD", "sentiment": "NEUTRAL", "reason": "Erro na análise AI"}

if __name__ == "__main__":
    print("Testing Brain (Gemma-4-31b-it)...")
    configure_genai()
    try:
        res = analyze_news("PETR4", "Petrobras descobre novo poço", "Descoberta relevante no pré-sal.")
        print(f"Analysis Result: {res}")
    except Exception as e:
        print(f"Test Failed: {e}")
