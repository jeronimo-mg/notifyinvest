import google.generativeai as genai
import json
import os


try:
    from secrets import GEMINI_API_KEY as API_KEY
except ImportError:
    from backend.secrets import GEMINI_API_KEY as API_KEY
except:
    API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("WARNING: Gemini API Key not found. Please set GEMINI_API_KEY env var or create backend/secrets.py")


def configure_matcher_ai():
    genai.configure(api_key=API_KEY)

def find_matches(title, summary=""):
    """
    Uses Gemma-3-12b-it to identify B3 companies in the text.
    Returns: List of tickers (e.g. ['PETR4', 'VALE3'])
    """
    configure_matcher_ai()
    
    try:
        # User requested Gemma-3-12b. 
        model = genai.GenerativeModel('gemma-3-12b-it')
    except Exception as e:
        print(f"Error loading Gemma-3-12b-it: {e}")
        raise e

    text = f"{title}\n{summary}"
    
    prompt = f"""
    Analyze the following news text and identify if any company listed on the Brazilian Stock Exchange (B3) is mentioned.
    
    News: "{text}"
    
    Return ONLY a JSON array of the official B3 tickers of the companies found. 
    If the company is mentioned by name (e.g., "Vale"), return the ticker (e.g., "VALE3").
    If no B3 company is mentioned, return [].
    
    Example Output: ["PETR4", "MGLU3"]
    """
    
    try:
        response = model.generate_content(prompt)
        content = response.text.replace("```json", "").replace("```", "").strip()
        tickers = json.loads(content)
        if isinstance(tickers, list):
            return tickers
        return []
    except Exception as e:
        print(f"Matcher AI Error: {e}")
        return []

if __name__ == "__main__":
    print("Testing Matcher (Gemma-3-12b)...")
    try:
        tickers = find_matches("Vale anucia dividendos bilionários e ações sobem", "A mineradora Vale (VALE3) surpreendeu o mercado com anúncio.")
        print(f"Found tickers: {tickers}")
    except Exception as e:
        print(f"Test Failed: {e}")
