import calendar
import time
import feedparser
import json
import sys
import os
import uuid
import tempfile

# Add libs to path so imports work
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))
# Also add the directory of this script to path so we can import sibling modules
sys.path.append(os.path.dirname(__file__))

try:
    from feeds import RSS_FEEDS
    from matcher import find_matches
    from brain import analyze_news, configure_genai
    from push import send_push_notification
    from evaluator import evaluate_all_signals, fetch_current_b3_price
    from cvm_rad import fetch_recent_cvm_filings, extract_cvm_pdf_text
except ImportError as e:
    print(f"Startup Import Error: {e}")
    try:
        from backend.feeds import RSS_FEEDS
        from backend.matcher import find_matches
        from backend.brain import analyze_news, configure_genai
        from backend.push import send_push_notification
        from backend.evaluator import evaluate_all_signals, fetch_current_b3_price
        from backend.cvm_rad import fetch_recent_cvm_filings, extract_cvm_pdf_text
    except Exception:
        print("CRITICAL: importing modules failed.")
        raise

# Configuration
POLL_INTERVAL = 30  # 30 seconds
MAX_RSS_ENTRIES_PER_FEED = 10
MAX_NEWS_AGE_SECONDS = 3 * 3600  # Ignore RSS articles published > 3 hours ago

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(BASE_DIR, "seen_news.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")
SIGNALS_FILE = os.path.join(BASE_DIR, "signals.json")
MAX_SIGNALS = 1000  # Keep last 1000 signals (approx 3-6 months)
EXPO_TOKEN = None

CVM_SOURCE_META = {
    "name": "CVM (Fatos Relevantes & RAD)",
    "url": "https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx",
    "type": "FATOS",
}


def atomic_write_json(filepath, data):
    """Safely write JSON to a file using a temp file and atomic rename."""
    dir_name = os.path.dirname(filepath)
    prefix = os.path.basename(filepath)

    fd, temp_path = tempfile.mkstemp(prefix=f".{prefix}.tmp", dir=dir_name, text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f)
        os.replace(temp_path, filepath)
    except Exception as e:
        print(f"Failed to write {filepath}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen_set):
    atomic_write_json(SEEN_FILE, list(seen_set))


def update_status(message):
    all_sources = [CVM_SOURCE_META] + list(RSS_FEEDS)
    status = {
        "status": "running",
        "last_update": time.time(),
        "message": message,
        "rss_source_count": len(all_sources),
        "rss_feeds": all_sources,
        "pid": os.getpid()
    }
    atomic_write_json(STATUS_FILE, status)


def save_signal(title, body, data):
    signals = []
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, 'r') as f:
                signals = json.load(f)
        except Exception:
            signals = []

    new_signal = {
        "id": str(uuid.uuid4()),
        "title": title,
        "body": body,
        "data": data,
        "timestamp": time.time()
    }

    signals.append(new_signal)
    signals = signals[-MAX_SIGNALS:]
    atomic_write_json(SIGNALS_FILE, signals)


def _get_entry_timestamp(entry):
    """Extracts unix timestamp from a feedparser entry if available."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, attr, None) or (entry.get(attr) if isinstance(entry, dict) else None)
        if parsed:
            try:
                return float(calendar.timegm(parsed))
            except Exception:
                continue
    return None


def dispatch_analyzed_signal(ticker, title, link, source_name, source_type, analysis, tokens):
    """Saves BUY/SELL signal to signals.json and sends filtered push notifications to users."""
    if not isinstance(analysis, dict) or analysis.get('signal') not in ['BUY', 'SELL']:
        return

    push_title = f"{ticker}: {analysis['signal']}"
    impact_str = analysis.get('impact', '0%')
    msg = f"Estimativa: {impact_str}\n{analysis.get('reason', '')}"

    try:
        clean_impact = str(impact_str).replace('%', '').replace('+', '').strip()
        impact_val = float(clean_impact.replace(',', '.'))
    except Exception:
        impact_val = 0

    print(f"Sending V3 Notification: {push_title} (Impact: {impact_val}%)", flush=True)

    initial_price = None
    try:
        initial_price = fetch_current_b3_price(ticker)
    except Exception:
        initial_price = None

    push_data = {
        "url": link,
        "source_type": source_type,
        "source_name": source_name,
        "ticker": ticker,
        "signal": analysis.get("signal"),
        "sentiment": analysis.get("sentiment", "POSITIVE" if analysis.get("signal") == "BUY" else "NEGATIVE"),
        "impact": impact_str,
        "reason": analysis.get("reason", ""),
        "news_title": title,
        "initial_price": initial_price
    }

    save_signal(push_title, msg, push_data)

    for user_token, prefs in tokens.items():
        should_send = False
        min_buy = prefs.get('min_buy', 0)
        min_sell = prefs.get('min_sell', 0)
        whitelist = prefs.get('whitelist', [])
        blacklist = prefs.get('blacklist', [])
        source_whitelist = prefs.get('source_whitelist', [])

        norm_ticker = ticker.strip().upper()

        # 1. Blacklist Check
        if norm_ticker in blacklist:
            print(f"Skipping {norm_ticker} for {user_token} (Blacklisted)")
            continue

        # 2. Whitelist Check
        if whitelist and len(whitelist) > 0:
            if norm_ticker not in whitelist:
                print(f"Skipping {norm_ticker} for {user_token} (Not in Whitelist)")
                continue

        # 3. Source Whitelist Check
        if source_whitelist and len(source_whitelist) > 0:
            if source_name not in source_whitelist and not (
                source_name.startswith("CVM") and "CVM (Fatos Relevantes & RAD)" in source_whitelist
            ):
                continue

        # 4. Impact Threshold Check
        if analysis['signal'] == 'BUY':
            if impact_val >= min_buy:
                should_send = True
        elif analysis['signal'] == 'SELL':
            if abs(impact_val) >= abs(min_sell):
                should_send = True

        if should_send:
            try:
                send_push_notification(user_token, push_title, msg, data=push_data)
            except Exception as push_err:
                print(f"Failed to send to {user_token}: {push_err}")


# Global for heartbeat
CURRENT_MESSAGE = "Initializing..."


def heartbeat_loop():
    """Keeps the status file fresh so Dashboard sees us as Online."""
    while True:
        try:
            update_status(CURRENT_MESSAGE)
        except Exception:
            pass
        time.sleep(15)


def main():
    print("Starting B3 News & CVM Primary Monitor...", flush=True)
    configure_genai()

    seen_links = load_seen()

    import threading
    t = threading.Thread(target=heartbeat_loop, daemon=True)
    t.start()

    token_file = os.path.join(os.path.dirname(__file__), 'tokens.json')

    global CURRENT_MESSAGE
    last_eval_run = time.time()

    # Check if CVM RAD has ever been seeded into seen_links
    has_cvm_seed = any("rad.cvm.gov.br" in u for u in seen_links)

    while True:
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        tokens = {tok: {"min_buy": 0, "min_sell": 0} for tok in data}
                    else:
                        tokens = data
            except Exception:
                tokens = {}
        else:
            tokens = {}

        legacy_token_file = os.path.join(os.path.dirname(__file__), 'token.txt')
        if os.path.exists(legacy_token_file):
            with open(legacy_token_file, 'r') as f:
                tok = f.read().strip()
                if tok and tok not in tokens:
                    tokens[tok] = {"min_buy": 0, "min_sell": 0}

        found_any_new = False
        now_ts = time.time()

        # =====================================================================
        # 1. FONTE ZERO: CVM RAD / Empresas.NET (Fatos Relevantes, Dividendos, Releases)
        # =====================================================================
        try:
            CURRENT_MESSAGE = "Checking CVM RAD (Fatos Relevantes & Releases)..."
            update_status(CURRENT_MESSAGE)
            cvm_filings = fetch_recent_cvm_filings(lookback_hours=6)

            if not has_cvm_seed and cvm_filings:
                # On first boot with CVM connector, seed filings older than 90 minutes to avoid replaying old items
                for cf in cvm_filings:
                    if (now_ts - cf.get("timestamp", 0)) > 5400:
                        seen_links.add(cf["link"])
                has_cvm_seed = True
                save_seen(seen_links)

            for filing in cvm_filings:
                link = filing["link"]
                if link in seen_links:
                    continue

                seen_links.add(link)
                found_any_new = True

                ticker = filing["ticker"]
                title = filing["title"]
                summary = filing["summary"]
                source_name = filing.get("source_name", "CVM (Fatos Relevantes & RAD)")
                source_type = filing.get("source_type", "FATOS")

                print(f"[{ticker}] CVM Primary Filing detected: {title}", flush=True)
                try:
                    CURRENT_MESSAGE = f"Reading CVM PDF & Analyzing ({ticker})..."
                    update_status(CURRENT_MESSAGE)

                    pdf_text = extract_cvm_pdf_text(link, max_chars=3500)
                    if pdf_text:
                        summary = f"{summary}\n\n[CONTEÚDO INTEGRAL EXTRAÍDO DO DOCUMENTO OFICIAL CVM]:\n{pdf_text}"

                    analysis = analyze_news(ticker, title, summary, url=link)
                    print(f"[{ticker}] CVM Filing Analysis: {analysis}", flush=True)
                    dispatch_analyzed_signal(ticker, title, link, source_name, source_type, analysis, tokens)
                except Exception as cvm_an_err:
                    print(f"CVM filing analysis failed for {ticker}: {cvm_an_err}", flush=True)
        except Exception as cvm_err:
            print(f"Error checking CVM RAD: {cvm_err}", flush=True)

        # =====================================================================
        # 2. RSS FEEDS (Primary Wires, Regulators, Sell-Side & Specialized News)
        # =====================================================================
        print(f"Checking {len(RSS_FEEDS)} RSS feeds for {len(tokens)} users...", flush=True)
        CURRENT_MESSAGE = f"Checking {len(RSS_FEEDS)} feeds..."
        update_status(CURRENT_MESSAGE)

        for feed_item in RSS_FEEDS:
            feed_url = feed_item['url']
            source_type = feed_item['type']
            source_name = feed_item.get('name', 'Unknown')
            try:
                feed = feedparser.parse(feed_url)
                entries = list(getattr(feed, 'entries', []) or [])

                # Check if this feed is being scanned for the very first time
                feed_links = [getattr(e, 'link', '') for e in entries if getattr(e, 'link', '')]
                is_first_scan_for_feed = bool(feed_links) and not any(fl in seen_links for fl in feed_links)
                if is_first_scan_for_feed:
                    # Seed older items on first scan so newly added feeds do not flood matcher.py
                    for old_entry in entries[1:]:
                        old_link = getattr(old_entry, 'link', '')
                        if old_link:
                            seen_links.add(old_link)

                for entry in entries[:MAX_RSS_ENTRIES_PER_FEED]:
                    link = getattr(entry, 'link', '')
                    if not link or link in seen_links:
                        continue

                    seen_links.add(link)

                    # Skip stale RSS articles (> 3 hours old) so we only analyze fresh pre-move catalysts
                    entry_ts = _get_entry_timestamp(entry)
                    if entry_ts and (time.time() - entry_ts) > MAX_NEWS_AGE_SECONDS:
                        continue

                    found_any_new = True
                    title = getattr(entry, 'title', '')
                    summary = getattr(entry, 'summary', '')

                    try:
                        tickers = find_matches(title, summary)
                    except Exception as e:
                        print(f"Matcher failed for {title}: {e}", flush=True)
                        tickers = []

                    if tickers:
                        primary_ticker = tickers[0]
                        print(f"[{primary_ticker}] Match found ({source_name}): {title}", flush=True)

                        try:
                            CURRENT_MESSAGE = f"Waiting for Gemini API ({primary_ticker})..."
                            update_status(CURRENT_MESSAGE)

                            analysis = analyze_news(primary_ticker, title, summary, url=link)
                            print(f"Analysis: {analysis}", flush=True)
                            dispatch_analyzed_signal(
                                primary_ticker, title, link, source_name, source_type, analysis, tokens
                            )
                        except Exception as e:
                            print(f"Analysis failed: {e}", flush=True)

            except Exception as e:
                print(f"Error processing feed {feed_url}: {e}", flush=True)

        save_seen(seen_links)

        if found_any_new:
            print("New items processed! Checking again immediately (Burst Mode)...", flush=True)
            CURRENT_MESSAGE = "Burst Mode: Checking again..."
            time.sleep(10)
        else:
            # Run B3 price consolidation check sequentially (single-threaded) every 10 minutes while idle
            if (time.time() - last_eval_run) >= 600:
                try:
                    CURRENT_MESSAGE = "Updating B3 alert evaluations..."
                    update_status(CURRENT_MESSAGE)
                    evaluate_all_signals(force_recalculate=False, max_signals_to_eval=6)
                except Exception as eval_err:
                    print(f"Sequential evaluator error: {eval_err}", flush=True)
                last_eval_run = time.time()

            print(f"No new items. Sleeping for {POLL_INTERVAL}s...", flush=True)
            CURRENT_MESSAGE = f"Sleeping ({POLL_INTERVAL}s)..."
            update_status(CURRENT_MESSAGE)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
