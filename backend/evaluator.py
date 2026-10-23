import json
import os
import re
import time
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import requests

try:
    from brain import evaluate_alert_reason
except ImportError:
    try:
        from backend.brain import evaluate_alert_reason
    except ImportError:
        evaluate_alert_reason = None

try:
    from b3_tickers import B3_TICKERS
except ImportError:
    try:
        from backend.b3_tickers import B3_TICKERS
    except ImportError:
        B3_TICKERS = {}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILE = os.path.join(BASE_DIR, "signals.json")
EVALUATIONS_FILE = os.path.join(BASE_DIR, "evaluations.json")

# Observation window parameters (3 full B3 trading days = ~21 trading hours, or max 120 elapsed hours)
MAX_TRADING_MINUTES = 21 * 60       # 21 hours of B3 trading (~3 trading sessions of 7h)
MAX_ELAPSED_SECONDS = 5 * 24 * 3600 # 5 calendar days max (covers weekends)
CONSOLIDATION_RATIO = 0.70          # >= 70% of estimated impact counts as consolidated
MIN_TARGET_PCT = 0.50               # Minimum 0.5% move required if estimated impact is tiny
REVERSAL_RATIO = 1.00               # 100% of estimated impact in the opposite direction triggers Reversal
MIN_REVERSAL_PCT = 1.50             # Minimum 1.5% adverse move to flag reversal


def atomic_write_json(filepath, data):
    dir_name = os.path.dirname(filepath)
    prefix = os.path.basename(filepath)
    fd, temp_path = tempfile.mkstemp(prefix=f".{prefix}.tmp", dir=dir_name, text=True)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, filepath)
    except Exception as e:
        print(f"Evaluator failed to write {filepath}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def load_evaluations():
    if os.path.exists(EVALUATIONS_FILE):
        try:
            with open(EVALUATIONS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"Error loading evaluations.json: {e}")
    return {"evaluations": {}, "summary": {}, "last_run": 0}


def save_evaluations(eval_store):
    atomic_write_json(EVALUATIONS_FILE, eval_store)


def parse_signal_record(sig):
    """
    Extracts structured fields (ticker, signal, sentiment, impact_pct, impact_str, reason)
    from either enriched signal.data or legacy title/body format.
    """
    data = sig.get("data") or {}
    title = sig.get("title") or ""
    body = sig.get("body") or ""

    # 1. Ticker & Signal
    ticker = data.get("ticker")
    signal_type = data.get("signal")
    if not ticker or not signal_type:
        if ":" in title:
            parts = title.split(":", 1)
            ticker = ticker or parts[0].strip().upper()
            sig_candidate = parts[1].strip().upper()
            if "BUY" in sig_candidate:
                signal_type = "BUY"
            elif "SELL" in sig_candidate:
                signal_type = "SELL"
            elif "HOLD" in sig_candidate:
                signal_type = "HOLD"

    if not ticker or signal_type not in ("BUY", "SELL"):
        return None

    # 2. Impact & Reason
    impact_str = data.get("impact")
    reason = data.get("reason")
    lines = body.split("\n", 1)
    if not impact_str:
        first_line = lines[0] if lines else ""
        impact_str = first_line.replace("Estimativa:", "").strip()
    if not reason:
        reason = lines[1].strip() if len(lines) > 1 else body.strip()

    # Parse numeric impact percentage
    impact_pct = 0.0
    m = re.search(r"([+-]?\d+(?:[.,]\d+)?)\s*%", impact_str or "")
    if m:
        try:
            impact_pct = float(m.group(1).replace(",", "."))
        except Exception:
            impact_pct = 0.0

    # Ensure sign matches signal direction for magnitude calculation
    expected_magnitude_pct = abs(impact_pct) if abs(impact_pct) > 0 else 1.5

    # 3. Sentiment
    sentiment = data.get("sentiment")
    if not sentiment:
        sentiment = "POSITIVE" if signal_type == "BUY" else "NEGATIVE"

    return {
        "id": sig.get("id") or f"{ticker}_{int(sig.get('timestamp', 0))}",
        "ticker": ticker,
        "signal": signal_type,
        "sentiment": sentiment,
        "impact_str": impact_str or (f"+{expected_magnitude_pct}%" if signal_type == "BUY" else f"-{expected_magnitude_pct}%"),
        "expected_magnitude_pct": expected_magnitude_pct,
        "reason": reason,
        "news_title": data.get("news_title") or "",
        "news_url": data.get("url") or "",
        "source_name": data.get("source_name") or "RSS",
        "source_type": data.get("source_type") or "FATOS",
        "timestamp": float(sig.get("timestamp") or time.time()),
        "initial_price": data.get("initial_price"),
    }


def fetch_current_b3_price(ticker):
    """Quickly fetches the latest price of a B3 ticker on Yahoo Finance."""
    clean_ticker = ticker.strip().upper().replace(".SA", "")
    symbol = f"{clean_ticker}.SA"
    headers = {"User-Agent": "Mozilla/5.0"}
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            url = f"https://{host}/v8/finance/chart/{symbol}?interval=15m&range=5d"
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code != 200:
                continue
            res = r.json().get("chart", {}).get("result")
            if not res:
                continue
            meta = res[0].get("meta", {})
            if meta.get("regularMarketPrice"):
                return float(meta["regularMarketPrice"])
            closes = res[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            valid = [c for c in closes if c is not None]
            if valid:
                return float(valid[-1])
        except Exception:
            continue
    return None


def fetch_b3_candles(ticker, start_ts, end_ts=None):
    """
    Fetches 15m (or 1h) OHLC candles from Yahoo Finance for {ticker}.SA
    starting slightly before start_ts (to capture the prior close reference price)
    up to end_ts.
    """
    clean_ticker = ticker.strip().upper().replace(".SA", "")
    symbol = f"{clean_ticker}.SA"
    now_ts = time.time()
    if end_ts is None or end_ts > now_ts:
        end_ts = now_ts

    # Look back 4 days before start_ts to guarantee at least 1 prior trading day close (even across weekends/holidays)
    period1 = int(start_ts - 4 * 86400)
    period2 = int(end_ts + 900)
    age_days = (now_ts - start_ts) / 86400.0
    interval = "15m" if age_days <= 55 else "1h"
    candle_minutes = 15 if interval == "15m" else 60

    headers = {"User-Agent": "Mozilla/5.0"}
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            url = (
                f"https://{host}/v8/finance/chart/{symbol}"
                f"?period1={period1}&period2={period2}&interval={interval}&includePrePost=false"
            )
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            chart = r.json().get("chart", {})
            results = chart.get("result")
            if not results:
                continue
            res = results[0]
            timestamps = res.get("timestamp") or []
            quotes = (res.get("indicators", {}).get("quote") or [{}])[0]
            opens = quotes.get("open") or []
            highs = quotes.get("high") or []
            lows = quotes.get("low") or []
            closes = quotes.get("close") or []

            candles = []
            for i, ts in enumerate(timestamps):
                c = closes[i] if i < len(closes) else None
                o = opens[i] if i < len(opens) else None
                h = highs[i] if i < len(highs) else None
                l = lows[i] if i < len(lows) else None
                if c is None:
                    continue
                candles.append({
                    "ts": float(ts),
                    "open": float(o if o is not None else c),
                    "high": float(h if h is not None else c),
                    "low": float(l if l is not None else c),
                    "close": float(c),
                    "minutes": candle_minutes,
                })
            return candles
        except Exception as e:
            print(f"Yahoo Finance error ({host}) for {symbol}: {e}")
            continue
    return []


def fetch_subsequent_news(ticker, alert_ts, max_items=6):
    """
    Fetches subsequent news from Google News RSS (PT-BR) for the ticker and company name
    published after alert_ts.
    """
    clean_ticker = ticker.strip().upper()
    # Find company name from B3_TICKERS if available
    company_names = [k for k, v in B3_TICKERS.items() if v == clean_ticker and len(k) > 3]
    company_name = company_names[0].title() if company_names else ""

    query = f"{clean_ticker}"
    if company_name and company_name.upper() != clean_ticker:
        query = f'"{clean_ticker}" OR "{company_name}"'

    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419"

    news_after = []
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                pub_date = item.findtext("pubDate") or ""
                source_el = item.find("source")
                source_name = source_el.text if source_el is not None else "Google News"

                pub_ts = None
                if pub_date:
                    try:
                        pub_ts = parsedate_to_datetime(pub_date).timestamp()
                    except Exception:
                        pub_ts = None

                # Include news published after (or up to 15 min before) the alert within 6 days
                if pub_ts and (alert_ts - 900) <= pub_ts <= (alert_ts + 6 * 86400):
                    news_after.append({
                        "title": title,
                        "url": link,
                        "source": source_name,
                        "timestamp": pub_ts,
                    })
    except Exception as e:
        print(f"Failed to fetch subsequent news for {ticker}: {e}")

    news_after.sort(key=lambda x: x.get("timestamp", 0))
    return news_after[:max_items]


def format_duration_pt(minutes):
    """Formats minutes into a human-friendly Portuguese string like '2h 15min' or '45min'."""
    if minutes is None:
        return "-"
    minutes = max(1, int(round(minutes)))
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes // 60
    rem = minutes % 60
    if rem == 0:
        return f"{hours}h"
    return f"{hours}h {rem}min"


def evaluate_single_signal(sig, existing_eval=None, force_ai=False):
    """
    Evaluates a single signal against B3 stock price action and subsequent news.
    """
    parsed = parse_signal_record(sig)
    if not parsed:
        return None

    now_ts = time.time()
    alert_ts = parsed["timestamp"]
    ticker = parsed["ticker"]
    signal_type = parsed["signal"]
    expected_mag = parsed["expected_magnitude_pct"]

    target_pct = max(MIN_TARGET_PCT, round(expected_mag * CONSOLIDATION_RATIO, 2))
    reversal_pct = max(MIN_REVERSAL_PCT, round(expected_mag * REVERSAL_RATIO, 2))

    window_end_ts = alert_ts + MAX_ELAPSED_SECONDS
    candles = fetch_b3_candles(ticker, alert_ts, min(now_ts, window_end_ts + 3600))

    # Determine Entry Price (reference price at or immediately before alert_ts)
    prior_candles = [c for c in candles if c["ts"] <= alert_ts]
    post_candles = [c for c in candles if c["ts"] > alert_ts and c["ts"] <= window_end_ts]

    entry_price = parsed.get("initial_price")
    entry_ts = alert_ts
    if not entry_price:
        if prior_candles:
            entry_price = prior_candles[-1]["close"]
            entry_ts = prior_candles[-1]["ts"]
        elif post_candles:
            entry_price = post_candles[0]["open"]
            entry_ts = post_candles[0]["ts"]

    # If no market data is available yet (e.g. brand new alert outside market hours and Yahoo failed)
    if not entry_price:
        return {
            "signal_id": parsed["id"],
            "ticker": ticker,
            "signal": signal_type,
            "sentiment": parsed["sentiment"],
            "impact_str": parsed["impact_str"],
            "expected_magnitude_pct": expected_mag,
            "target_threshold_pct": target_pct,
            "reason": parsed["reason"],
            "source_name": parsed["source_name"],
            "news_url": parsed["news_url"],
            "alert_timestamp": alert_ts,
            "status": "TRACKING",
            "status_label": "Aguardando Pregão",
            "status_badge": "⏳ Aguardando Pregão",
            "is_final": False,
            "last_evaluated": now_ts,
        }

    # Walk through post-alert candles up to MAX_TRADING_MINUTES
    trading_minutes = 0
    max_favorable_pct = 0.0
    max_favorable_ts = None
    max_adverse_pct = 0.0
    max_adverse_ts = None
    latest_price = entry_price
    latest_change_pct = 0.0
    latest_Signed_favorable_pct = 0.0

    consolidated = False
    consolidated_at = None
    trading_minutes_to_consolidate = None
    elapsed_minutes_to_consolidate = None
    consolidation_price = None
    consolidation_pct = None

    first_reversed_at = None
    trading_minutes_to_reverse = None

    checkpoints = {"1h": None, "4h": None, "1d": None, "3d": None}
    first_post_candle_ts = post_candles[0]["ts"] if post_candles else None

    for c in post_candles:
        if trading_minutes >= MAX_TRADING_MINUTES:
            break

        trading_minutes += c["minutes"]
        latest_price = c["close"]

        if signal_type == "BUY":
            fav_pct = ((c["high"] - entry_price) / entry_price) * 100.0
            adv_pct = ((c["low"] - entry_price) / entry_price) * 100.0  # negative when price drops
            close_fav_pct = ((c["close"] - entry_price) / entry_price) * 100.0
            raw_change_pct = close_fav_pct
            fav_price = c["high"]
        else:  # SELL
            fav_pct = ((entry_price - c["low"]) / entry_price) * 100.0   # positive when price drops (SELL wins)
            adv_pct = -((c["high"] - entry_price) / entry_price) * 100.0 # negative when price rises (SELL loses)
            close_fav_pct = ((entry_price - c["close"]) / entry_price) * 100.0
            raw_change_pct = ((c["close"] - entry_price) / entry_price) * 100.0
            fav_price = c["low"]

        latest_change_pct = round(raw_change_pct, 2)
        latest_Signed_favorable_pct = round(close_fav_pct, 2)

        if fav_pct > max_favorable_pct:
            max_favorable_pct = round(fav_pct, 2)
            max_favorable_ts = c["ts"]

        if adv_pct < max_adverse_pct:
            max_adverse_pct = round(adv_pct, 2)
            max_adverse_ts = c["ts"]

        # Check exact moment of consolidation (>= 70% of estimated impact)
        if not consolidated and fav_pct >= target_pct:
            consolidated = True
            consolidated_at = c["ts"]
            trading_minutes_to_consolidate = trading_minutes
            elapsed_minutes_to_consolidate = round(max(1.0, (c["ts"] - alert_ts) / 60.0), 1)
            consolidation_price = round(fav_price, 2)
            consolidation_pct = round(fav_pct, 2)

        # Check if it went strongly in the opposite direction before consolidating
        if not consolidated and first_reversed_at is None and adv_pct <= -reversal_pct:
            first_reversed_at = c["ts"]
            trading_minutes_to_reverse = trading_minutes

        # Record checkpoints by trading time
        if checkpoints["1h"] is None and trading_minutes >= 60:
            checkpoints["1h"] = round(raw_change_pct, 2)
        if checkpoints["4h"] is None and trading_minutes >= 240:
            checkpoints["4h"] = round(raw_change_pct, 2)
        if checkpoints["1d"] is None and trading_minutes >= 420:  # 1 B3 session (~7h)
            checkpoints["1d"] = round(raw_change_pct, 2)
        if checkpoints["3d"] is None and trading_minutes >= 1260: # 3 B3 sessions (~21h)
            checkpoints["3d"] = round(raw_change_pct, 2)

    elapsed_seconds = now_ts - alert_ts
    window_expired = (trading_minutes >= MAX_TRADING_MINUTES) or (elapsed_seconds >= MAX_ELAPSED_SECONDS and trading_minutes >= 60)

    # Determine Overall Status & Badge
    if consolidated:
        status = "CONSOLIDATED"
        dur_str = format_duration_pt(trading_minutes_to_consolidate)
        status_label = f"Consolidado em {dur_str} de pregão"
        status_badge = f"✅ Consolidado ({dur_str})"
        is_final = window_expired  # Keep updating peak until window finishes, or mark consolidated immediately
    elif window_expired:
        is_final = True
        if latest_Signed_favorable_pct <= -1.0 or (first_reversed_at and latest_Signed_favorable_pct < 0):
            status = "REVERSED"
            status_label = "Direção Contrária (Tese Invalidada)"
            status_badge = "🚨 Direção Contrária"
        elif max_favorable_pct >= (expected_mag * 0.35) and latest_Signed_favorable_pct > 0:
            status = "PARTIAL"
            status_label = "Acerto Parcial (Direção certa, abaixo de 70% da meta)"
            status_badge = "☑️ Acerto Parcial"
        else:
            status = "EXPIRED_MISSED"
            status_label = "Expirou sem atingir a meta"
            status_badge = "❌ Não Consolidou"
    else:
        is_final = False
        if trading_minutes == 0:
            status = "TRACKING"
            status_label = "Aguardando abertura do pregão"
            status_badge = "⏳ Aguardando Pregão"
        elif first_reversed_at is not None and latest_Signed_favorable_pct <= -reversal_pct:
            status = "REVERSED"
            status_label = "Indo na Direção Contrária (Stop atingido)"
            status_badge = "🚨 Direção Contrária"
        elif latest_Signed_favorable_pct <= -0.8:
            status = "TRACKING_ADVERSE"
            status_label = "Em observação (Movimento contrário no momento)"
            status_badge = "⚠️ Em Observação (Contra)"
        else:
            status = "TRACKING"
            status_label = "Em observação no pregão"
            status_badge = "⏳ Em Observação"

    # Compute Quantitative Scores (0 - 100) for Signal and Impact
    # 1. Signal Score (Did BUY/SELL get the direction right?)
    if consolidated:
        # Base 85-100 depending on whether it held or exceeded the target
        bonus = min(15.0, max(0.0, ((max_favorable_pct - target_pct) / max(0.5, expected_mag)) * 15.0))
        signal_score = int(round(85.0 + bonus))
    elif status == "PARTIAL":
        signal_score = int(round(60.0 + min(20.0, (max_favorable_pct / target_pct) * 20.0)))
    elif status in ("REVERSED", "TRACKING_ADVERSE"):
        penalty = min(85.0, abs(min(0.0, latest_Signed_favorable_pct)) / max(1.0, reversal_pct) * 70.0)
        signal_score = int(max(5, round(35.0 - penalty)))
    else:
        # Tracking or expired flat
        if max_favorable_pct > 0:
            signal_score = int(min(70, round((max_favorable_pct / target_pct) * 65.0)))
        else:
            signal_score = 40 if not window_expired else 25

    # 2. Impact Score (How close was actual max favorable move to expected_mag?)
    if max_favorable_pct <= 0 and latest_Signed_favorable_pct < 0:
        impact_score = max(0, int(round(20.0 - abs(latest_Signed_favorable_pct) * 5.0)))
    else:
        ratio = max_favorable_pct / max(0.5, expected_mag)
        if 0.70 <= ratio <= 1.50:
            # Sweet spot: very accurate impact estimation
            diff = abs(1.0 - ratio)
            impact_score = int(round(100.0 - diff * 30.0))
        elif ratio > 1.50:
            # Underestimated magnitude, but still profitable
            impact_score = max(75, int(round(90.0 - (ratio - 1.50) * 10.0)))
        else:
            # Fell short of 70% target
            impact_score = int(round(ratio / 0.70 * 70.0))

    # 3. Fetch subsequent news & run AI evaluation for Sentiment and Reason
    subsequent_news = (existing_eval or {}).get("subsequent_news") or []
    ai_eval = (existing_eval or {}).get("ai_evaluation")

    should_fetch_news = (
        not subsequent_news
        or force_ai
        or (consolidated and not ai_eval)
        or (window_expired and not ai_eval)
        or (now_ts - (existing_eval or {}).get("last_news_check", 0) > 1800)
    )
    last_news_check = (existing_eval or {}).get("last_news_check", 0)
    if should_fetch_news:
        subsequent_news = fetch_subsequent_news(ticker, alert_ts)
        last_news_check = now_ts

    should_run_ai = (
        evaluate_alert_reason is not None
        and trading_minutes >= 15
        and (
            force_ai
            or ai_eval is None
            or (consolidated and not (existing_eval or {}).get("ai_evaluated_after_consolidation"))
            or (window_expired and not (existing_eval or {}).get("ai_evaluated_after_expiry"))
        )
    )

    price_metrics = {
        "entry_price": round(entry_price, 2),
        "latest_price": round(latest_price, 2),
        "max_favorable_pct": max_favorable_pct,
        "max_adverse_pct": max_adverse_pct,
        "latest_change_pct": latest_change_pct,
        "status_label": status_label,
    }

    ai_evaluated_after_consolidation = (existing_eval or {}).get("ai_evaluated_after_consolidation", False)
    ai_evaluated_after_expiry = (existing_eval or {}).get("ai_evaluated_after_expiry", False)

    if should_run_ai:
        new_ai = evaluate_alert_reason(
            ticker=ticker,
            original_signal=signal_type,
            original_sentiment=parsed["sentiment"],
            original_impact=parsed["impact_str"],
            original_reason=parsed["reason"],
            original_title=parsed["news_title"],
            price_metrics=price_metrics,
            subsequent_news=subsequent_news,
        )
        if new_ai:
            ai_eval = new_ai
            if consolidated:
                ai_evaluated_after_consolidation = True
            if window_expired:
                ai_evaluated_after_expiry = True

    # Fallback heuristic scores for Sentiment and Reason if AI hasn't run yet
    if ai_eval and isinstance(ai_eval, dict):
        sentiment_score = int(max(0, min(100, ai_eval.get("sentiment_score", signal_score))))
        reason_score = int(max(0, min(100, ai_eval.get("reason_score", signal_score))))
        verdict = ai_eval.get("verdict") or status_label
        news_alignment = ai_eval.get("news_alignment") or "NEUTRAL"
    else:
        sentiment_score = int(round(0.7 * signal_score + 0.3 * impact_score))
        reason_score = int(round(0.6 * signal_score + 0.4 * impact_score))
        news_alignment = "CONFIRMED" if consolidated else ("CONTRADICTED" if status == "REVERSED" else "NEUTRAL")
        if consolidated:
            verdict = f"A ação confirmou a tese ({signal_type}) atingindo {consolidation_pct:+.2f}% em {format_duration_pt(trading_minutes_to_consolidate)} de pregão."
        elif status == "REVERSED":
            verdict = f"O mercado reagiu na direção oposta ao sinal ({latest_change_pct:+.2f}%), invalidando o impacto previsto."
        elif status == "PARTIAL":
            verdict = f"O ativo seguiu a direção prevista (pico de {max_favorable_pct:+.2f}%), mas sem força para atingir 70% da meta ({target_pct:.2f}%)."
        elif status == "EXPIRED_MISSED":
            verdict = f"Prazo de 3 pregões encerrado sem que o ativo atingisse o alvo de {target_pct:.2f}%."
        else:
            verdict = f"Em acompanhamento ({format_duration_pt(trading_minutes)} de pregão analisados até agora)."

    overall_score = int(
        round(
            0.35 * signal_score
            + 0.25 * impact_score
            + 0.20 * sentiment_score
            + 0.20 * reason_score
        )
    )

    return {
        "signal_id": parsed["id"],
        "ticker": ticker,
        "signal": signal_type,
        "sentiment": parsed["sentiment"],
        "impact_str": parsed["impact_str"],
        "expected_magnitude_pct": expected_mag,
        "target_threshold_pct": target_pct,
        "reversal_threshold_pct": reversal_pct,
        "reason": parsed["reason"],
        "source_name": parsed["source_name"],
        "source_type": parsed["source_type"],
        "news_url": parsed["news_url"],
        "alert_timestamp": alert_ts,
        "entry_price": round(entry_price, 2),
        "entry_timestamp": entry_ts,
        "first_trading_candle_ts": first_post_candle_ts,
        "latest_price": round(latest_price, 2),
        "latest_change_pct": latest_change_pct,
        "latest_favorable_pct": latest_Signed_favorable_pct,
        "max_favorable_pct": max_favorable_pct,
        "max_favorable_ts": max_favorable_ts,
        "max_adverse_pct": max_adverse_pct,
        "max_adverse_ts": max_adverse_ts,
        "trading_minutes_observed": trading_minutes,
        "trading_duration_observed_str": format_duration_pt(trading_minutes),
        "consolidated": consolidated,
        "consolidated_at": consolidated_at,
        "trading_minutes_to_consolidate": trading_minutes_to_consolidate,
        "trading_time_to_consolidate_str": format_duration_pt(trading_minutes_to_consolidate) if consolidated else None,
        "elapsed_minutes_to_consolidate": elapsed_minutes_to_consolidate,
        "elapsed_time_to_consolidate_str": format_duration_pt(elapsed_minutes_to_consolidate) if consolidated else None,
        "consolidation_price": consolidation_price,
        "consolidation_pct": consolidation_pct,
        "first_reversed_at": first_reversed_at,
        "trading_minutes_to_reverse": trading_minutes_to_reverse,
        "checkpoints": checkpoints,
        "status": status,
        "status_label": status_label,
        "status_badge": status_badge,
        "scores": {
            "signal": signal_score,
            "impact": impact_score,
            "sentiment": sentiment_score,
            "reason": reason_score,
            "overall": overall_score,
        },
        "verdict": verdict,
        "news_alignment": news_alignment,
        "subsequent_news": subsequent_news,
        "ai_evaluation": ai_eval,
        "ai_evaluated_after_consolidation": ai_evaluated_after_consolidation,
        "ai_evaluated_after_expiry": ai_evaluated_after_expiry,
        "last_news_check": last_news_check,
        "is_final": is_final,
        "last_evaluated": now_ts,
    }


def compute_global_summary(evaluations_dict):
    """Computes aggregate accuracy metrics across all evaluated signals."""
    items = list(evaluations_dict.values())
    total = len(items)
    if total == 0:
        return {
            "total_signals": 0,
            "evaluated_with_market_data": 0,
            "consolidated_count": 0,
            "partial_count": 0,
            "reversed_count": 0,
            "expired_missed_count": 0,
            "tracking_count": 0,
            "win_rate_strict_pct": 0.0,
            "win_rate_directional_pct": 0.0,
            "avg_trading_minutes_to_consolidate": None,
            "avg_trading_time_to_consolidate_str": "-",
            "avg_scores": {"signal": 0, "impact": 0, "sentiment": 0, "reason": 0, "overall": 0},
        }

    consolidated_items = [x for x in items if x.get("status") == "CONSOLIDATED"]
    partial_items = [x for x in items if x.get("status") == "PARTIAL"]
    reversed_items = [x for x in items if x.get("status") == "REVERSED"]
    expired_items = [x for x in items if x.get("status") == "EXPIRED_MISSED"]
    tracking_items = [x for x in items if x.get("status") in ("TRACKING", "TRACKING_ADVERSE")]

    # Resolved signals = Consolidated + Partial + Reversed + Expired
    resolved_count = len(consolidated_items) + len(partial_items) + len(reversed_items) + len(expired_items)
    denom = resolved_count if resolved_count > 0 else total

    win_rate_strict = round((len(consolidated_items) / denom) * 100.0, 1) if denom else 0.0
    win_rate_directional = round(((len(consolidated_items) + len(partial_items)) / denom) * 100.0, 1) if denom else 0.0

    cons_times = [
        x["trading_minutes_to_consolidate"]
        for x in consolidated_items
        if x.get("trading_minutes_to_consolidate") is not None
    ]
    avg_cons_min = round(sum(cons_times) / len(cons_times), 1) if cons_times else None

    scored_items = [x for x in items if x.get("scores") and x.get("trading_minutes_observed", 0) > 0]
    if not scored_items:
        scored_items = [x for x in items if x.get("scores")]

    if scored_items:
        n = len(scored_items)
        avg_scores = {
            "signal": int(round(sum(x["scores"]["signal"] for x in scored_items) / n)),
            "impact": int(round(sum(x["scores"]["impact"] for x in scored_items) / n)),
            "sentiment": int(round(sum(x["scores"]["sentiment"] for x in scored_items) / n)),
            "reason": int(round(sum(x["scores"]["reason"] for x in scored_items) / n)),
            "overall": int(round(sum(x["scores"]["overall"] for x in scored_items) / n)),
        }
    else:
        avg_scores = {"signal": 0, "impact": 0, "sentiment": 0, "reason": 0, "overall": 0}

    return {
        "total_signals": total,
        "resolved_signals": resolved_count,
        "consolidated_count": len(consolidated_items),
        "partial_count": len(partial_items),
        "reversed_count": len(reversed_items),
        "expired_missed_count": len(expired_items),
        "tracking_count": len(tracking_items),
        "win_rate_strict_pct": win_rate_strict,
        "win_rate_directional_pct": win_rate_directional,
        "avg_trading_minutes_to_consolidate": avg_cons_min,
        "avg_trading_time_to_consolidate_str": format_duration_pt(avg_cons_min) if avg_cons_min else "-",
        "avg_scores": avg_scores,
    }


def evaluate_all_signals(force_recalculate=False, max_signals_to_eval=100):
    """
    Loads signals.json, evaluates new or active signals, updates evaluations.json,
    and returns the complete store.
    """
    if not os.path.exists(SIGNALS_FILE):
        store = load_evaluations()
        store["summary"] = compute_global_summary(store.get("evaluations", {}))
        store["last_run"] = time.time()
        save_evaluations(store)
        return store

    try:
        with open(SIGNALS_FILE, "r") as f:
            signals = json.load(f)
    except Exception as e:
        print(f"Error reading signals.json in evaluator: {e}")
        return load_evaluations()

    store = load_evaluations()
    evals = store.get("evaluations", {})
    now_ts = time.time()

    # Process most recent signals first
    recent_signals = list(reversed(signals))[:max_signals_to_eval]

    for sig in recent_signals:
        sig_id = sig.get("id")
        if not sig_id:
            parsed = parse_signal_record(sig)
            if not parsed:
                continue
            sig_id = parsed["id"]

        existing = evals.get(sig_id)
        if existing and existing.get("is_final") and not force_recalculate:
            continue

        # Throttle active evaluations to once every 3 minutes unless forced
        if existing and not force_recalculate:
            if (now_ts - existing.get("last_evaluated", 0)) < 180:
                continue

        try:
            res = evaluate_single_signal(sig, existing_eval=existing, force_ai=force_recalculate)
            if res:
                evals[sig_id] = res
        except Exception as e:
            print(f"Error evaluating signal {sig_id}: {e}")

    store["evaluations"] = evals
    store["summary"] = compute_global_summary(evals)
    store["last_run"] = now_ts
    save_evaluations(store)
    return store


if __name__ == "__main__":
    print("Running NotifyInvest Alert Accuracy Evaluator...")
    result = evaluate_all_signals(force_recalculate=True)
    print("Summary:", json.dumps(result.get("summary", {}), indent=2, ensure_ascii=False))
