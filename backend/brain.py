from google import genai
from google.genai import types
import json
import os
import re

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

def _parse_json_object(raw_text):
    text = raw_text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)

def analyze_news(ticker, title, summary):
    """
    Analyzes news using Gemma-4-31b-it (with fallback to Gemma-4-26b-a4b-it).
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
        # Note: gemma-4-31b-it throws HTTP 500 INTERNAL when response_mime_type="application/json" is set
        response = client.models.generate_content(
            model='gemma-4-31b-it',
            contents=prompt
        )
        return _parse_json_object(response.text)
    except Exception as e:
        print(f"Warning: gemma-4-31b-it failed ({e}), falling back to gemma-4-26b-a4b-it...")
        try:
            response = client.models.generate_content(
                model='gemma-4-26b-a4b-it',
                contents=prompt
            )
            return _parse_json_object(response.text)
        except Exception as fallback_err:
            print(f"Error analyzing with Gemma: {fallback_err}")
            return {"signal": "HOLD", "sentiment": "NEUTRAL", "reason": "Erro na análise AI"}


def evaluate_alert_reason(
    ticker,
    original_signal,
    original_sentiment,
    original_impact,
    original_reason,
    original_title,
    price_metrics,
    subsequent_news,
):
    """
    Uses Gemma to evaluate whether the original 'sentiment' and 'reason' held true
    given the subsequent stock price behavior on B3 and follow-up news headlines.
    Returns JSON with scores (0-100) and a short verdict in Portuguese.
    """
    if not API_KEY:
        return None
    try:
        client = configure_genai()
    except Exception as e:
        print(f"Could not initialize GenAI client for evaluation: {e}")
        return None

    news_list_str = "\n".join([f"- {n.get('title', '')} ({n.get('source', '')})" for n in (subsequent_news or [])[:8]])
    if not news_list_str.strip():
        news_list_str = "Nenhuma notícia posterior relevante encontrada no período."

    prompt = f"""
    Você é um auditor quantitativo e fundamentalista da B3 (Bolsa de Valores do Brasil).
    Avalie se um alerta gerado por IA para a ação {ticker} acertou em sua tese (reason) e sentimento (sentiment).

    --- ALERTA ORIGINAL ---
    Ativo: {ticker}
    Notícia Original: {original_title or 'N/A'}
    Sinal emitido (signal): {original_signal}
    Sentimento previsto (sentiment): {original_sentiment}
    Impacto previsto (impact): {original_impact}
    Justificativa original (reason): {original_reason}

    --- COMPORTAMENTO REAL DAS AÇÕES NA B3 APÓS O ALERTA ---
    Preço inicial de referência: R$ {price_metrics.get('entry_price', 'N/A')}
    Preço mais recente/final na janela: R$ {price_metrics.get('latest_price', 'N/A')}
    Variação máxima a favor do sinal: {price_metrics.get('max_favorable_pct', 0):.2f}%
    Variação máxima contra o sinal (drawdown): {price_metrics.get('max_adverse_pct', 0):.2f}%
    Variação final/atual: {price_metrics.get('latest_change_pct', 0):.2f}%
    Status técnico de consolidação: {price_metrics.get('status_label', 'N/A')}

    --- NOTÍCIAS POSTERIORES AO ALERTA ---
    {news_list_str}

    Tarefa:
    1. Avalie de 0 a 100 o grau de acerto do SENTIMENTO (sentiment_score): o humor real do mercado e do noticiário posterior correspondeu ao sentimento {original_sentiment}?
    2. Avalie de 0 a 100 o grau de acerto da JUSTIFICATIVA (reason_score): o motivo dado ("{original_reason}") se provou relevante, correto e direcionador de preço, ou foi irrelevante/contradito/já precificado?
    3. Escreva um veredito curto e direto em português (máx 2 frases) explicando por que o alerta acertou, acertou parcialmente ou errou.

    Responda APENAS com um objeto JSON válido neste formato:
    {{
        "sentiment_score": 85,
        "reason_score": 80,
        "news_alignment": "CONFIRMED/NEUTRAL/CONTRADICTED",
        "verdict": "Explicação curta em pt-br sobre a confirmação ou falha da tese."
    }}
    """

    for model_name in ['gemma-4-31b-it', 'gemma-4-26b-a4b-it']:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            parsed = _parse_json_object(response.text)
            if isinstance(parsed, dict) and "reason_score" in parsed:
                return parsed
        except Exception as e:
            print(f"Warning: {model_name} evaluation failed ({e})")
            continue

    return None


if __name__ == "__main__":
    print("Testing Brain (Gemma-4-31b-it)...")
    configure_genai()
    try:
        res = analyze_news("PETR4", "Petrobras descobre novo poço", "Descoberta relevante no pré-sal.")
        print(f"Analysis Result: {res}")
    except Exception as e:
        print(f"Test Failed: {e}")

