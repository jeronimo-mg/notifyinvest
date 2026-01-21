import google.generativeai as genai
import os

import os

try:
    from secrets import GEMINI_API_KEY as API_KEY
except ImportError:
    from backend.secrets import GEMINI_API_KEY as API_KEY
except:
    API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("WARNING: Gemini API Key not found. Please set GEMINI_API_KEY env var or create backend/secrets.py")


def configure_genai():
    genai.configure(api_key=API_KEY)

def analyze_news(ticker, title, summary):
    """
    Analyzes news using Gemma-3-27b-it.
    Returns analysis JSON.
    """
    try:
        model = genai.GenerativeModel('gemma-3-27b-it')
    except Exception as e:
        print(f"FATAL: Could not load 'gemma-3-27b-it'. {e}")
        raise e
    
    prompt = f"""
    You are a financial analyst specializing in the Brazilian Stock Market (B3).
    Analyze the following news item related to the company {ticker}.
    
    News Title: {title}
    News Summary: {summary}
    
    Task:
    1. Determine the sentiment of the news regarding {ticker} (POSITIVE, NEGATIVE, NEUTRAL).
    2. Suggest a trading signal (BUY, SELL, HOLD). Be conservative; only suggest BUY/SELL if the news is significant and has clear price impact potential.
    3. Provide a very short reason (max 1 sentence) in Portuguese.
    
    Output format (JSON only):
    {{
        "signal": "BUY/SELL/HOLD",
        "sentiment": "POSITIVE/NEGATIVE/NEUTRAL",
        "reason": "Resumo do motivo em pt-br"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        result = eval(text) 
        return result
    except Exception as e:
        print(f"Error analyzing with Gemma: {e}")
        return {"signal": "HOLD", "sentiment": "NEUTRAL", "reason": "Erro na análise AI"}

if __name__ == "__main__":
    print("Testing Brain (Gemma-3-27b)...")
    configure_genai()
    try:
        res = analyze_news("PETR4", "Petrobras descobre novo poço", "Descoberta relevante no pré-sal.")
        print(f"Analysis Result: {res}")
    except Exception as e:
        print(f"Test Failed: {e}")
