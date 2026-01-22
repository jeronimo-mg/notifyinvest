import time
import feedparser
import json
import sys
import os

# Add libs to path imports work
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))

try:
    from feeds import RSS_FEEDS
    from matcher import find_matches
    from brain import analyze_news, configure_genai
    from push import send_push_notification
except ImportError:
    # Fallback if running from root
    from backend.feeds import RSS_FEEDS
    from backend.matcher import find_matches
    from backend.brain import analyze_news, configure_genai
    from backend.push import send_push_notification

# Configuration
POLL_INTERVAL = 30 # 30 seconds for testing
SEEN_FILE = "seen_news.json"
EXPO_TOKEN = None # Will be set dynamically or loaded from config

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_seen(seen_set):
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(seen_set), f)

def main():
    print("Starting B3 News Monitor...")
    configure_genai()
    
    seen_links = load_seen()
    
    # Prepare for multi-user support
    import json
    token_file = os.path.join(os.path.dirname(__file__), 'tokens.json')

    while True:
        # Load tokens dynamically every loop (so new users get added instantly)
        tokens = []
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    tokens = json.load(f)
            except:
                tokens = []
        
        # Fallback for migration (if token.txt still exists)
        legacy_token_file = os.path.join(os.path.dirname(__file__), 'token.txt')
        if os.path.exists(legacy_token_file):
             with open(legacy_token_file, 'r') as f:
                t = f.read().strip()
                if t and t not in tokens: tokens.append(t)

        # Logic: If we found new items, we want to check again immediately (Burst Mode)
        # because staying up-to-date during a news flood is critical.
        # If we found nothing new, we relax and wait POLL_INTERVAL.
        found_any_new = False

        print(f"Checking {len(RSS_FEEDS)} feeds for {len(tokens)} users...")
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
                            
                            if analysis.get('signal') in ['BUY', 'SELL']:
                                msg = f"{tickers[0]}: {analysis['signal']} - {analysis['reason']}"
                                print(f"Sending Notification to {len(tokens)} users: {msg}")
                                
                                for user_token in tokens:
                                    try:
                                        send_push_notification(user_token, "[Cloud ☁️] B3 Signal Detected!", msg)
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
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
