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
    Stage 1: Connects directly to 'models/gemini-3.8-live-extended-thinking' via the
    Gemini Live WebSocket API (BidiGenerateContent v1beta).
    Using direct WebSocket JSON frames bypasses outdated Python 3.9 Pydantic schemas
    for 'thinking_level' and 'interactionStatus' while supporting full asynchronous
    background reasoning (IN_PROGRESS -> IDLE).
    """
    try:
        from websockets.asyncio.client import connect as ws_connect
    except ImportError:
        from websockets import connect as ws_connect

    uri = (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        f"?key={API_KEY}"
    )

    system_instruction = (
        "Você é um analista financeiro sênior especialista na Bolsa de Valores do Brasil (B3). "
        "Para toda notícia enviada pelo usuário, responda sempre de forma direta e analítica em português, "
        "avaliando o impacto para a ação indicada. Informe claramente: "
        "1) O sentimento da notícia para o ativo (POSITIVE, NEGATIVE ou NEUTRAL); "
        "2) O sinal recomendado (BUY, SELL ou HOLD, sendo conservador); "
        "3) A estimativa percentual de impacto no curto prazo (ex: +2%, -4%, 0%); "
        "4) Uma justificativa concisa de 1 frase em português."
    )

    # Wire format for Gemini 3.8 Live Extended Thinking setup:
    # - responseModalities: ["AUDIO"]
    # - thinkingConfig: {"include_thoughts": True, "thinking_level": "HIGH"}
    # - outputAudioTranscription: {}
    # - proactive_audio is permanently enabled by default on 3.8 Live
    setup_payload = {
        "setup": {
            "model": "models/gemini-3.8-live-extended-thinking",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "thinkingConfig": {
                    "include_thoughts": True,
                    "thinking_level": "HIGH",
                },
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "outputAudioTranscription": {},
        }
    }

    user_prompt = (
        f"Analise esta notícia para a ação {ticker} na B3:\n"
        f"Título: {title}\n"
        f"Resumo: {summary}\n\n"
        f"Qual é o sentimento (POSITIVE/NEGATIVE/NEUTRAL), o sinal (BUY/SELL/HOLD), "
        f"a estimativa de impacto percentual (+/-X%) e o motivo em 1 frase?"
    )

    client_content_payload = {
        "client_content": {
            "turns": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "turn_complete": True,
        }
    }

    thoughts_chunks = []
    transcript_chunks = []
    text_chunks = []

    async with ws_connect(uri) as ws:
        # 1. Send Setup message and await setupComplete
        await ws.send(json.dumps(setup_payload))
        setup_raw = await ws.recv()
        if isinstance(setup_raw, bytes):
            setup_raw = setup_raw.decode("utf-8")
        setup_resp = json.loads(setup_raw)
        if "error" in setup_resp:
            raise RuntimeError(f"Live API Setup Error: {setup_resp['error']}")

        # 2. Send User News Prompt
        await ws.send(json.dumps(client_content_payload))

        # 3. Asynchronous reasoning loop monitoring interactionStatus (IN_PROGRESS vs IDLE).
        # With Extended Thinking, turnComplete=True does NOT mean the session is idle if
        # interactionStatus is still IN_PROGRESS.
        while True:
            raw_msg = await ws.recv()
            if isinstance(raw_msg, bytes):
                raw_msg = raw_msg.decode("utf-8")
            msg = json.loads(raw_msg)

            if "error" in msg:
                raise RuntimeError(f"Live API Stream Error: {msg['error']}")

            sc = msg.get("serverContent") or msg.get("server_content")
            if not sc:
                continue

            # 1. Capture thought summaries and text parts from modelTurn
            model_turn = sc.get("modelTurn") or sc.get("model_turn") or {}
            for part in model_turn.get("parts") or []:
                if part.get("thought") and part.get("text"):
                    thoughts_chunks.append(part["text"])
                elif part.get("text"):
                    text_chunks.append(part["text"])

            # 2. Capture real-time output audio transcription
            out_trans = sc.get("outputTranscription") or sc.get("output_transcription") or {}
            if out_trans.get("text"):
                transcript_chunks.append(out_trans["text"])

            # 3. Monitor interactionStatus (IN_PROGRESS vs IDLE)
            raw_status = sc.get("interactionStatus") or sc.get("interaction_status") or ""
            status_str = str(raw_status).upper()
            turn_complete = bool(sc.get("turnComplete") or sc.get("turn_complete"))

            if "IDLE" in status_str:
                break
            elif "IN_PROGRESS" in status_str:
                # Background extended thinking is still running; keep listening even if turnComplete is True
                continue
            elif turn_complete and not status_str:
                # Fallback if server frame omits interactionStatus
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

