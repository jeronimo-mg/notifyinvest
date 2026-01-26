import time
import feedparser
import json
import sys
import os
import uuid

# Add libs to path imports work
# Add libs to path imports work
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))
# Also add the directory of this script to path so we can import sibling modules
sys.path.append(os.path.dirname(__file__))

try:
    from feeds import RSS_FEEDS
    from matcher import find_matches
    from brain import analyze_news, configure_genai
    from push import send_push_notification
    # Fallbacks not needed if sys.path is correct
except ImportError as e:
    print(f"Startup Import Error: {e}")
    # Last ditch effort
    try:
        from backend.feeds import RSS_FEEDS
        from backend.matcher import find_matches
        from backend.brain import analyze_news, configure_genai
        from backend.push import send_push_notification
    except:
        print("CRITICAL: importing modules failed.")
        raise
except ImportError:
    # Fallback if running from root
    from backend.feeds import RSS_FEEDS
    from backend.matcher import find_matches
    from backend.brain import analyze_news, configure_genai
    from backend.push import send_push_notification

# Configuration
# Configuration
POLL_INTERVAL = 30 # 30 seconds for testing
# Use absolute paths based on __file__ to avoid CWD issues
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(BASE_DIR, "seen_news.json")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")
EXPO_TOKEN = None # Will be set dynamically or loaded from config

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_seen(seen_set):
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(seen_set), f)

def update_status(message):
    status = {
        "status": "running",
        "last_update": time.time(),
        "message": message,
        "pid": os.getpid()
    }
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        print(f"Failed to update status: {e}")

SIGNALS_FILE = os.path.join(os.path.dirname(__file__), "signals.json")
MAX_SIGNALS = 1000 # Keep last 1000 signals (approx 3-6 months)

def save_signal(title, body, data):
    signals = []
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, 'r') as f:
                signals = json.load(f)
        except:
            signals = []
    
    # Add new item with UUID
    new_signal = {
        "id": str(uuid.uuid4()),
        "title": title,
        "body": body,
        "data": data,
        "timestamp": time.time()
    }
    
    signals.append(new_signal)
    
    # Keep only last MAX_SIGNALS
    signals = signals[-MAX_SIGNALS:]
    
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(signals, f)

def main():
    print("Starting B3 News Monitor...")
    configure_genai()
    
    seen_links = load_seen()
    
    # Prepare for multi-user support
    import json
    token_file = os.path.join(os.path.dirname(__file__), 'tokens.json')

    while True:
                # Load tokens dynamically (supports dict or list for migration)
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        # Migrate on the fly for memory
                        tokens = {t: {"min_buy": 0, "min_sell": 0} for t in data}
                    else:
                        tokens = data
            except:
                tokens = {}
        else:
            tokens = {}
        
        # Fallback (legacy file)
        legacy_token_file = os.path.join(os.path.dirname(__file__), 'token.txt')
        if os.path.exists(legacy_token_file):
             with open(legacy_token_file, 'r') as f:
                t = f.read().strip()
                if t and t not in tokens: 
                    tokens[t] = {"min_buy": 0, "min_sell": 0}

        # Logic: If we found new items, we want to check again immediately (Burst Mode)
        # because staying up-to-date during a news flood is critical.
        # If we found nothing new, we relax and wait POLL_INTERVAL.
        found_any_new = False

        print(f"Checking {len(RSS_FEEDS)} feeds for {len(tokens)} users...")
        update_status(f"Checking {len(RSS_FEEDS)} feeds...")
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    link = entry.link
                    if link in seen_links:
                        continue
                    
                    # We found a new item!
                    found_any_new = True
                    seen_links.add(link) 
                        
                    title = entry.title
                    summary = getattr(entry, 'summary', '')
                    
                    # Match (Gemma-12b)
                    try:
                        tickers = find_matches(title, summary)
                    except Exception as e:
                        print(f"Matcher failed for {title}: {e}")
                        tickers = []

                    if tickers:
                        print(f"[{tickers[0]}] Match found: {title}")
                        
                        # Analyze (Gemma-27b)
                        try:
                            analysis = analyze_news(tickers[0], title, summary)
                            print(f"Analysis: {analysis}")
                            update_status(f"Analyzing {tickers[0]}...")
                            
                            
                            if analysis.get('signal') in ['BUY', 'SELL']:
                                # New V3 Title Format: "PETR4: BUY"
                                push_title = f"{tickers[0]}: {analysis['signal']}"
                                
                                # New V3 Body Format: "Impact: +2% - Reason..."
                                impact_str = analysis.get('impact', '0%')
                                msg = f"Estimativa: {impact_str}\n{analysis['reason']}"
                                
                                # Parse Impact
                                try:
                                    # Removing %, +, whitespace
                                    clean_impact = impact_str.replace('%', '').replace('+', '').strip()
                                    impact_val = int(clean_impact)
                                except:
                                    impact_val = 0
                                
                                print(f"Sending V3 Notification: {push_title} (Impact: {impact_val}%)")
                                
                                push_data = {"url": link}

                                # Save to signals DB (Always save, regardless of user prefs)
                                save_signal(push_title, msg, push_data)

                                for user_token, prefs in tokens.items():
                                    should_send = False
                                    min_buy = prefs.get('min_buy', 0)
                                    min_sell = prefs.get('min_sell', 0)
                                    whitelist = prefs.get('whitelist', [])
                                    blacklist = prefs.get('blacklist', [])
                                    
                                    # Filter by Company (Ticker)
                                    # push_title is like "PETR4: BUY"
                                    ticker = push_title.split(':')[0].strip().upper()
                                    
                                    # 1. Blacklist Check (Strongest exclude)
                                    if ticker in blacklist:
                                        print(f"Skipping {ticker} for {user_token} (Blacklisted)")
                                        continue
                                        
                                    # 2. Whitelist Check (If active, must be in it)
                                    if whitelist and len(whitelist) > 0:
                                        if ticker not in whitelist:
                                            print(f"Skipping {ticker} for {user_token} (Not in Whitelist)")
                                            continue

                                    # 3. Impact Threshold Check
                                    if analysis['signal'] == 'BUY':
                                        if impact_val >= min_buy: should_send = True
                                    elif analysis['signal'] == 'SELL':
                                        if abs(impact_val) >= abs(min_sell): should_send = True
                                    
                                    if should_send:
                                        try:
                                            send_push_notification(user_token, push_title, msg, data=push_data)
                                        except Exception as push_err:
                                            print(f"Failed to send to {user_token}: {push_err}")
                            
                        except Exception as e:
                            print(f"Analysis failed: {e}")
                                
            except Exception as e:
                print(f"Error processing feed {feed_url}: {e}")
        
        save_seen(seen_links)
        
        if found_any_new:
            print("New items processed! Checking again immediately (Burst Mode)...")
            time.sleep(10) # Small buffer to be polite to the RSS server (avoid instant ban)
        else:
            print(f"No new items. Sleeping for {POLL_INTERVAL}s...")
            update_status(f"Sleeping ({POLL_INTERVAL}s)...")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
