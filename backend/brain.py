import asyncio
import importlib.util
import json
import os
import re
import sys

def _load_api_key_safely():
    """
    Loads GEMINI_API_KEY from backend/secrets.py without shadowing Python's standard
    library 'secrets' module (which websockets requires for secrets.token_bytes).
    """
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    # Ensure stdlib 'secrets' is loaded into sys.modules['secrets'] first
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
from google.genai import types

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


def _is_valid_live_analysis(text):
    """
    Checks whether the transcription/output from Gemini 3.8 Live contains an actual
    financial analysis rather than just a conversational filler or a backend 'system error' apology.
    """
    if not text or not text.strip():
        return False
    lower = text.lower()
    error_phrases = (
        "erro no sistema",
        "system error",
        "ocorreu um erro",
        "error occurred",
        "não consegui processar",
        "unable to process",
    )
    if any(phrase in lower for phrase in error_phrases):
        return False
    # Strip section headers to check actual content length
    cleaned = re.sub(r"parecer falado \(transcrição.*?\):", "", lower)
    cleaned = re.sub(r"texto gerado \(.*?\):", "", cleaned)
    cleaned = re.sub(r"raciocínio estendido \(.*?\):", "", cleaned).strip()
    if len(cleaned) < 40:
        return False
    return True


def _extract_structured_from_live_text(live_text):
    """
    Fallback parser if Gemma 4 endpoints are temporarily unavailable (500/503)
    after Gemini 3.8 Live has already produced a valid spoken analysis.
    """
    upper = live_text.upper()
    sentiment = "NEUTRAL"
    if "POSITIVE" in upper or "POSITIVO" in upper or "POSITIVA" in upper or "OTIMISTA" in upper:
        sentiment = "POSITIVE"
    elif "NEGATIVE" in upper or "NEGATIVO" in upper or "NEGATIVA" in upper or "PESSIMISTA" in upper:
        sentiment = "NEGATIVE"

    signal = "HOLD"
    if re.search(r"\b(BUY|COMPRA|COMPRAR)\b", upper):
        signal = "BUY"
    elif re.search(r"\b(SELL|VENDA|VENDER)\b", upper):
        signal = "SELL"

    impact = "0%"
    imp_match = re.search(r"([+-]?\s*\d+(?:[.,]\d+)?\s*%)", live_text)
    if imp_match:
        impact = imp_match.group(1).replace(" ", "").replace(",", ".")
        if not impact.startswith(("+", "-")) and impact != "0%":
            if sentiment == "POSITIVE":
                impact = "+" + impact
            elif sentiment == "NEGATIVE":
                impact = "-" + impact

    # Extract clean spoken text as reason
    reason = live_text
    if ":" in reason:
        reason = reason.split(":", 1)[1].strip()
    reason = re.sub(r"\s+", " ", reason).strip()
    if len(reason) > 220:
        reason = reason[:217].rstrip() + "..."

    return {
        "signal": signal,
        "sentiment": sentiment,
        "impact": impact,
        "reason": reason or "Análise gerada via Gemini 3.8 Live",
    }


async def _run_live_ws_session(model_id, ticker, title, summary, thinking_level=None):
    """
    Runs a single WebSocket BidiGenerateContent session against the specified Gemini 3.8 Live model,
    monitoring interactionStatus (IN_PROGRESS / THINKING / RESPONDING -> IDLE) and collecting
    outputAudioTranscription + modelTurn parts.
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
        "IMPORTANTE: Você já possui todas as informações necessárias na mensagem do usuário. "
        "NÃO tente acionar ferramentas externas, NÃO faça buscas e NÃO fale frases introdutórias de espera "
        "como 'Vou analisar' ou 'Deixe-me verificar'. "
        "Vá direto ao ponto na primeira resposta em português, informando: "
        "1) O sentimento da notícia para o ativo (POSITIVE, NEGATIVE ou NEUTRAL); "
        "2) O sinal recomendado (BUY, SELL ou HOLD, sendo conservador); "
        "3) A estimativa percentual de impacto no curto prazo (ex: +2%, -4%, 0%); "
        "4) Uma justificativa concisa de 1 frase em português."
    )

    gen_config = {
        "responseModalities": ["AUDIO"],
    }
    if thinking_level:
        gen_config["thinkingConfig"] = {
            "thinkingLevel": thinking_level,
        }

    setup_payload = {
        "setup": {
            "model": model_id,
            "generationConfig": gen_config,
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "outputAudioTranscription": {},
        }
    }

    user_prompt = (
        f"Dados completos da notícia sobre a ação {ticker} na B3:\n"
        f"Título: {title}\n"
        f"Resumo: {summary}\n\n"
        f"Sem usar ferramentas externas e sem frases de espera, diga diretamente o sentimento "
        f"(POSITIVE, NEGATIVE ou NEUTRAL), o sinal (BUY, SELL ou HOLD), "
        f"a estimativa de impacto percentual (+/-X%) e a justificativa em 1 frase."
    )

    client_content_payload = {
        "clientContent": {
            "turns": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "turnComplete": True,
        }
    }

    thoughts_chunks = []
    transcript_chunks = []
    text_chunks = []

    async with ws_connect(uri) as ws:
        await ws.send(json.dumps(setup_payload))
        setup_raw = await ws.recv()
        if isinstance(setup_raw, bytes):
            setup_raw = setup_raw.decode("utf-8")
        setup_resp = json.loads(setup_raw)
        if "error" in setup_resp:
            raise RuntimeError(f"Live API Setup Error ({model_id}): {setup_resp['error']}")

        await ws.send(json.dumps(client_content_payload))

        last_status = "IN_PROGRESS"
        while True:
            recv_timeout = 25.0 if ("IN_PROGRESS" in last_status or "THINKING" in last_status) else 6.0
            try:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
            except asyncio.TimeoutError:
                break

            if isinstance(raw_msg, bytes):
                raw_msg = raw_msg.decode("utf-8")
            msg = json.loads(raw_msg)

            if "error" in msg:
                raise RuntimeError(f"Live API Stream Error ({model_id}): {msg['error']}")

            sc = msg.get("serverContent") or msg.get("server_content") or {}

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

            # 3. Monitor interactionStatus at both top-level message and serverContent
            raw_status = (
                msg.get("interactionStatus")
                or msg.get("interaction_status")
                or sc.get("interactionStatus")
                or sc.get("interaction_status")
                or ""
            )
            status_str = str(raw_status).upper()
            if status_str:
                last_status = status_str

            turn_complete = bool(sc.get("turnComplete") or sc.get("turn_complete"))

            if "IDLE" in status_str:
                break
            elif any(s in status_str for s in ("IN_PROGRESS", "THINKING", "RESPONDING", "LISTENING")):
                continue
            elif turn_complete and not any(s in last_status for s in ("IN_PROGRESS", "THINKING")):
                break

    combined_sections = []
    if transcript_chunks:
        combined_sections.append(f"Parecer falado (Transcrição {model_id}): " + "".join(transcript_chunks).strip())
    if text_chunks:
        combined_sections.append(f"Texto gerado ({model_id}): " + "".join(text_chunks).strip())
    if thoughts_chunks:
        combined_sections.append("Raciocínio estendido (Extended Thinking): " + "\n".join(thoughts_chunks).strip())

    return "\n\n".join(combined_sections).strip()


async def _analyze_with_gemini_3_8_live(ticker, title, summary):
    """
    Stage 1: Connects first to 'models/gemini-3.8-live-extended-thinking' via the
    Gemini Live WebSocket API (BidiGenerateContent v1beta) with thinkingLevel="HIGH",
    monitoring interactionStatus (IN_PROGRESS -> IDLE). If the extended-thinking
    background sub-agent emits a spoken 'system error' apology, automatically retries
    Stage 1 with 'models/gemini-3.8-live'.
    """
    # Primary attempt: Gemini 3.8 Live Extended Thinking (HIGH depth)
    text = await _run_live_ws_session(
        model_id="models/gemini-3.8-live-extended-thinking",
        ticker=ticker,
        title=title,
        summary=summary,
        thinking_level="HIGH",
    )
    if _is_valid_live_analysis(text):
        return text

    print(
        f"[{ticker}] gemini-3.8-live-extended-thinking (HIGH) returned filler/system-error ({text!r}); "
        f"retrying Stage 1 with models/gemini-3.8-live...",
        flush=True,
    )
    text_fallback = await _run_live_ws_session(
        model_id="models/gemini-3.8-live",
        ticker=ticker,
        title=title,
        summary=summary,
        thinking_level=None,
    )
    if _is_valid_live_analysis(text_fallback):
        return text_fallback

    return ""


def _extract_interaction_output_text(data):
    """
    Extracts the final model text and a summary of executed agent steps (such as
    google_search, url_context, thought) from a v1beta/interactions response object.
    """
    if not isinstance(data, dict):
        return "", []

    tool_steps_used = []
    text_parts = []

    for step in data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        stype = step.get("type") or ""
        if stype and stype not in ("model_output", "user_input"):
            tool_steps_used.append(stype)
        if stype == "model_output":
            content = step.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("text"):
                        text_parts.append(item["text"])
            elif isinstance(step.get("text"), str):
                text_parts.append(step["text"])

    if not text_parts and isinstance(data.get("output_text"), str):
        text_parts.append(data["output_text"])

    if not text_parts:
        for out in data.get("outputs") or []:
            if isinstance(out, dict) and out.get("text"):
                text_parts.append(out["text"])

    return "\n".join(text_parts).strip(), tool_steps_used


def _analyze_with_antigravity_argon(ticker, title, summary, url=""):
    """
    Calls the Managed Agent 'antigravity-preview-09-2026' configured with
    agent_config={'type': 'antigravity', 'model': 'gemini-4-argon'} via the
    Gemini Interactions REST API (v1beta/interactions).
    Runs inside Google's remote Linux sandbox with 'url_context' and 'google_search'
    enabled, consuming zero CPU/RAM on the local Oracle VM.
    """
    import requests
    import time as _time

    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": API_KEY,
        "Api-Revision": "2026-05-20",
    }

    url_line = f"Link da Notícia (use url_context se precisar ler o texto completo): {url}\n" if url else ""
    prompt_input = (
        f"Você é um analista financeiro sênior especialista na Bolsa de Valores do Brasil (B3).\n"
        f"Analise a seguinte notícia sobre a ação {ticker}:\n\n"
        f"Título: {title}\n"
        f"Resumo: {summary}\n"
        f"{url_line}\n"
        f"Instruções:\n"
        f"1. Se o link da notícia estiver disponível e o resumo for curto ou incompleto, você pode usar `url_context` "
        f"para ler a matéria completa, ou `google_search` para verificar o contexto recente de {ticker} na B3.\n"
        f"2. Avalie o sentimento da notícia para {ticker} (POSITIVE, NEGATIVE ou NEUTRAL).\n"
        f"3. Defina o sinal de operação (BUY, SELL ou HOLD, sendo conservador).\n"
        f"4. Estime o impacto percentual no preço da ação no curto prazo (ex: '+2%', '-3%', '0%').\n"
        f"5. Escreva uma justificativa concisa de no máximo 1 frase em português.\n\n"
        f"Responda ao final OBRIGATORIAMENTE com um objeto JSON válido exatamente neste formato:\n"
        f"{{\n"
        f'  "signal": "BUY/SELL/HOLD",\n'
        f'  "sentiment": "POSITIVE/NEGATIVE/NEUTRAL",\n'
        f'  "impact": "+/-X%",\n'
        f'  "reason": "Resumo conciso do motivo em 1 frase em pt-br"\n'
        f"}}"
    )

    payload = {
        "agent": "antigravity-preview-09-2026",
        "input": prompt_input,
        "environment": "remote",
        "agent_config": {
            "type": "antigravity",
            "model": "gemini-4-argon",
        },
        "tools": [
            {"type": "google_search"},
            {"type": "url_context"},
        ],
    }

    resp = requests.post(endpoint, headers=headers, json=payload, timeout=180)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    interaction_id = data.get("id")
    status = str(data.get("status") or "").lower()

    # If the interaction is running asynchronously, poll until completion
    poll_start = _time.time()
    while status in ("in_progress", "running", "pending") and interaction_id:
        if (_time.time() - poll_start) > 150:
            raise TimeoutError(f"Antigravity interaction {interaction_id} timed out after 150s")
        _time.sleep(4.0)
        poll_resp = requests.get(f"{endpoint}/{interaction_id}", headers=headers, timeout=30)
        if poll_resp.status_code >= 400:
            raise RuntimeError(f"Poll HTTP {poll_resp.status_code}: {poll_resp.text[:300]}")
        data = poll_resp.json()
        status = str(data.get("status") or "").lower()

    output_text, tools_used = _extract_interaction_output_text(data)
    usage = data.get("usage") or {}
    print(
        f"[{ticker}] antigravity-preview-09-2026 (gemini-4-argon) finished | "
        f"status={status or 'completed'} | steps={tools_used} | usage={usage}",
        flush=True,
    )
    return output_text


def analyze_news(ticker, title, summary, url=""):
    """
    News analysis pipeline for B3 stocks:
    1. Primary: Uses 'antigravity-preview-09-2026' with agent_config.model='gemini-4-argon'
       (supporting url_context and google_search in Google's remote sandbox) to analyze the news
       and return the structured JSON output directly.
    2. Fallback: If Antigravity returns unstructured text or fails, uses Gemini 3.8 Live Extended Thinking
       + Gemma 4 ('gemma-4-31b-it' / 'gemma-4-26b-a4b-it') to guarantee a valid JSON output.
    """
    import time as _time
    try:
        client = configure_genai()
    except Exception as e:
        print(f"FATAL: Could not initialize GenAI client. {e}", flush=True)
        raise e

    # Primary Flow: antigravity-preview-09-2026 with agent_config.model = "gemini-4-argon"
    antigravity_text = ""
    try:
        print(
            f"[{ticker}] Analyzing with antigravity-preview-09-2026 (agent_config.model='gemini-4-argon')...",
            flush=True,
        )
        antigravity_text = _analyze_with_antigravity_argon(ticker, title, summary, url=url)
        if antigravity_text:
            preview = antigravity_text.replace("\n", " ")[:240]
            print(f"[{ticker}] Antigravity (gemini-4-argon) output ({len(antigravity_text)} chars): {preview}", flush=True)
            try:
                parsed_direct = _parse_json_object(antigravity_text)
                if (
                    isinstance(parsed_direct, dict)
                    and parsed_direct.get("signal") in ("BUY", "SELL", "HOLD")
                    and parsed_direct.get("sentiment") in ("POSITIVE", "NEGATIVE", "NEUTRAL")
                ):
                    return parsed_direct
            except Exception as parse_err:
                print(
                    f"[{ticker}] Antigravity output was not direct JSON ({parse_err}); "
                    f"passing analysis to Gemma 4 for JSON structuring...",
                    flush=True,
                )
    except Exception as ag_err:
        print(
            f"Warning: antigravity-preview-09-2026 (gemini-4-argon) failed ({ag_err}). "
            f"Falling back to Gemini 3.8 Live Extended Thinking + Gemma 4...",
            flush=True,
        )
        antigravity_text = ""

    # Fallback Stage 1: Gemini 3.8 Live Extended Thinking (only if Antigravity did not return text)
    live_analysis_text = antigravity_text
    if not live_analysis_text:
        try:
            print(f"[{ticker}] Fallback Stage 1: Analyzing with gemini-3.8-live-extended-thinking (Live API)...", flush=True)
            live_analysis_text = asyncio.run(
                asyncio.wait_for(
                    _analyze_with_gemini_3_8_live(ticker, title, summary),
                    timeout=65.0
                )
            )
            if live_analysis_text:
                preview = live_analysis_text.replace("\n", " ")[:220]
                print(f"[{ticker}] Gemini 3.8 Live output captured ({len(live_analysis_text)} chars): {preview}...", flush=True)
            else:
                print(f"[{ticker}] Gemini 3.8 Live returned no valid analysis; Gemma 4 will analyze directly.", flush=True)
        except Exception as live_err:
            print(f"Warning: gemini-3.8-live-extended-thinking stage failed ({live_err}). Falling back to direct Gemma 4 analysis...", flush=True)
            live_analysis_text = ""

    # Stage 2: Gemma 4 Structured Output Extraction (or fallback direct analysis)
    if live_analysis_text:
        prompt = f"""
    You are a financial data structurer for the Brazilian Stock Market (B3).
    Below is a news item about {ticker} and the in-depth analysis produced by our senior analyst model.

    News Title: {title}
    News Summary: {summary}

    [SENIOR ANALYST EVALUATION]
    {live_analysis_text}

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

    # Only use the two Gemma 4 models available on the user's account, with 3 retry rounds
    gemma_4_models = ('gemma-4-31b-it', 'gemma-4-26b-a4b-it')
    for attempt in range(3):
        for model_name in gemma_4_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return _parse_json_object(response.text)
            except Exception as e:
                wait_sec = 2.0 * (attempt + 1)
                print(
                    f"Warning: {model_name} (round {attempt + 1}/3) failed ({e}), "
                    f"waiting {wait_sec:.0f}s before next try...",
                    flush=True,
                )
                _time.sleep(wait_sec)
                continue

    if live_analysis_text:
        print(f"[{ticker}] All Gemma 4 retries exhausted; extracting structured fields from analyst text.", flush=True)
        return _extract_structured_from_live_text(live_analysis_text)

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

    import time as _time
    for attempt in range(2):
        for model_name in ('gemma-4-31b-it', 'gemma-4-26b-a4b-it'):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                parsed = _parse_json_object(response.text)
                if isinstance(parsed, dict) and "reason_score" in parsed:
                    return parsed
            except Exception as e:
                print(f"Warning: {model_name} evaluation (round {attempt + 1}/2) failed ({e})")
                _time.sleep(2.0)
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

