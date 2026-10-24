import asyncio
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
_live_client = None

def configure_genai():
    global _client
    if _client is None:
        _client = genai.Client(api_key=API_KEY)
    return _client

def configure_live_genai():
    global _live_client
    if _live_client is None:
        _live_client = genai.Client(
            api_key=API_KEY,
            http_options={"api_version": "v1beta"}
        )
    return _live_client

def _parse_json_object(raw_text):
    text = raw_text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


async def _analyze_with_gemini_3_8_live(ticker, title, summary):
    """
    Stage 1: Connects to 'gemini-3.8-live-extended-thinking' via the Live API,
    sends the B3 news item, and monitors 'interaction_status' (IN_PROGRESS vs IDLE)
    while background extended thinking and audio transcription stream in.
    """
    live_client = configure_live_genai()

    system_instruction = (
        "Você é um analista financeiro sênior especialista na Bolsa de Valores do Brasil (B3). "
        "Para toda notícia enviada pelo usuário, responda sempre de forma direta e analítica em português, "
        "avaliando o impacto para a ação indicada. Informe claramente: "
        "1) O sentimento da notícia para o ativo (POSITIVE, NEGATIVE ou NEUTRAL); "
        "2) O sinal recomendado (BUY, SELL ou HOLD, sendo conservador); "
        "3) A estimativa percentual de impacto no curto prazo (ex: +2%, -4%, 0%); "
        "4) Uma justificativa concisa de 1 frase em português."
    )

    # Note: On gemini-3.8-live-extended-thinking:
    # - response_modalities must be ["AUDIO"]
    # - output_audio_transcription={} enables real-time text transcript of the audio response
    # - thinking_config supports thinking_level="low"|"medium"|"high" (not "minimal") and include_thoughts=True
    # - proactive_audio is permanently enabled by default (do not set proactive_audio=False)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        output_audio_transcription={},
        thinking_config=types.ThinkingConfig(
            thinking_level="high",
            include_thoughts=True,
        ),
        system_instruction=types.Content(
            parts=[types.Part(text=system_instruction)]
        ),
    )

    user_prompt = (
        f"Analise esta notícia para a ação {ticker} na B3:\n"
        f"Título: {title}\n"
        f"Resumo: {summary}\n\n"
        f"Qual é o sentimento (POSITIVE/NEGATIVE/NEUTRAL), o sinal (BUY/SELL/HOLD), "
        f"a estimativa de impacto percentual (+/-X%) e o motivo em 1 frase?"
    )

    thoughts_chunks = []
    transcript_chunks = []
    text_chunks = []

    async with live_client.aio.live.connect(
        model="gemini-3.8-live-extended-thinking",
        config=config
    ) as session:
        await session.send_client_content(
            turns={"role": "user", "parts": [{"text": user_prompt}]},
            turn_complete=True,
        )

        # Asynchronous reasoning loop monitoring interaction_status (IN_PROGRESS vs IDLE).
        # With Extended Thinking, turn_complete=True does NOT mean the session is idle if
        # interaction_status is still IN_PROGRESS.
        is_idle = False
        while not is_idle:
            received_any = False
            async for response in session.receive():
                received_any = True
                sc = response.server_content
                if not sc:
                    continue

                # 1. Capture thought summaries and text parts from model_turn
                if sc.model_turn and sc.model_turn.parts:
                    for part in sc.model_turn.parts:
                        if getattr(part, "thought", False) and getattr(part, "text", None):
                            thoughts_chunks.append(part.text)
                        elif getattr(part, "text", None):
                            text_chunks.append(part.text)

                # 2. Capture real-time output audio transcription
                if sc.output_transcription and getattr(sc.output_transcription, "text", None):
                    transcript_chunks.append(sc.output_transcription.text)

                # 3. Check interaction_status (IN_PROGRESS vs IDLE)
                raw_status = getattr(sc, "interaction_status", None)
                status_str = str(raw_status or "").upper()

                if "IDLE" in status_str:
                    is_idle = True
                    break
                elif "IN_PROGRESS" in status_str:
                    # Background reasoning is still active; keep listening even if turn_complete is True
                    continue
                elif sc.turn_complete and not status_str:
                    # Fallback if server frame omits interaction_status
                    is_idle = True
                    break

            if not received_any:
                break

    combined_sections = []
    if transcript_chunks:
        combined_sections.append("Parecer falado (Transcrição Gemini 3.8 Live): " + "".join(transcript_chunks).strip())
    if text_chunks:
        combined_sections.append("Texto gerado (Gemini 3.8 Live): " + "".join(text_chunks).strip())
    if thoughts_chunks:
        combined_sections.append("Raciocínio estendido (Extended Thinking): " + "\n".join(thoughts_chunks).strip())

    return "\n\n".join(combined_sections).strip()


def analyze_news(ticker, title, summary):
    """
    Two-stage news analysis pipeline:
    1. Stage 1 (Deep Financial Reasoning): Uses 'gemini-3.8-live-extended-thinking' via Live API
       monitoring asynchronous interaction_status (IN_PROGRESS -> IDLE).
    2. Stage 2 (Structured JSON Formatting): Sends the Gemini 3.8 analysis to Gemma 4
       ('gemma-4-31b-it' with fallback to 'gemma-4-26b-a4b-it') to produce the strict JSON output.
    """
    try:
        client = configure_genai()
    except Exception as e:
        print(f"FATAL: Could not initialize GenAI client. {e}")
        raise e

    # Stage 1: Gemini 3.8 Live Extended Thinking
    live_analysis_text = ""
    try:
        print(f"[{ticker}] Stage 1: Analyzing with gemini-3.8-live-extended-thinking (Live API)...")
        live_analysis_text = asyncio.run(
            asyncio.wait_for(
                _analyze_with_gemini_3_8_live(ticker, title, summary),
                timeout=60.0
            )
        )
        if live_analysis_text:
            print(f"[{ticker}] Gemini 3.8 Extended Thinking output captured ({len(live_analysis_text)} chars).")
        else:
            print(f"[{ticker}] Gemini 3.8 returned empty output (proactive silence or no speech); Gemma will analyze directly.")
    except Exception as live_err:
        print(f"Warning: gemini-3.8-live-extended-thinking stage failed ({live_err}). Falling back to direct Gemma analysis...")
        live_analysis_text = ""

    # Stage 2: Gemma 4 Structured Output Extraction (or fallback direct analysis)
    if live_analysis_text:
        prompt = f"""
    You are a financial data structurer for the Brazilian Stock Market (B3).
    Below is a news item about {ticker} and the in-depth analysis produced by our senior analyst model (Gemini 3.8 Live Extended Thinking).

    News Title: {title}
    News Summary: {summary}

    --- GEMINI 3.8 EXTENDED THINKING ANALYSIS ---
    {live_analysis_text}
    ---------------------------------------------

    Task:
    Convert the senior analyst's evaluation above into the exact JSON structure below:
    1. "sentiment": POSITIVE, NEGATIVE, or NEUTRAL.
    2. "signal": BUY, SELL, or HOLD (be conservative, following the analyst's conclusion).
    3. "impact": estimated short-term price impact as a percentage (e.g. "+2%", "-5%", "0%").
    4. "reason": a very short reason (max 1 sentence) in Portuguese summarizing the analyst's conclusion.

    Output format (JSON only):
    {{
        "signal": "BUY/SELL/HOLD",
        "sentiment": "POSITIVE/NEGATIVE/NEUTRAL",
        "impact": "+/-X%",
        "reason": "Resumo do motivo em pt-br"
    }}
    """
    else:
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
            print(f"Error structuring/analyzing with Gemma: {fallback_err}")
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

