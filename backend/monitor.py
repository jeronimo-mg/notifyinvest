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
POLL_INTERVAL = 300 # 5 minutes
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
    
    # Try to load token from a file if it exists (saved by server/API in future)
    # For now, user might paste it here or we run without push
    token = None 
    if os.path.exists("token.txt"):
        with open("token.txt", "r") as f:
            token = f.read().strip()
            
    while True:
        # Logic: If we found new items, we want to check again immediately (Burst Mode)
        # because staying up-to-date during a news flood is critical.
        # If we found nothing new, we relax and wait POLL_INTERVAL.
        found_any_new = False

        print(f"Checking {len(RSS_FEEDS)} feeds...")
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
                                print(f"Sending Notification: {msg}")
                                if token:
                                    send_push_notification(token, "B3 Signal Detected!", msg)
                                else:
                                    print("No Expo Token to send push.")
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
