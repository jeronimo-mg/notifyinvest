import json
import time
import os
import uuid
import sys

# Ensure we can import backend paths
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))

try:
    from push import send_push_notification
except ImportError:
    # If running from root
    sys.path.append('backend')
    from backend.push import send_push_notification

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Should be /home/opc/notifyinvest/backend
TOKENS_FILE = os.path.join(BASE_DIR, 'tokens.json')
SIGNALS_FILE = os.path.join(BASE_DIR, 'signals.json')

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    print("No tokens found.")
    return []

def save_signal(title, body, data):
    signals = []
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, 'r') as f:
                signals = json.load(f)
        except:
            signals = []
    
    new_signal = {
        "id": str(uuid.uuid4()),
        "title": title,
        "body": body,
        "data": data,
        "timestamp": time.time()
    }
    
    signals.append(new_signal)
    signals = signals[-1000:] # Keep last 1000
    
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(signals, f)
    print("Signal saved to DB.")

def main():
    print("--- MANUAL SIGNAL TRIGGER ---")
    tokens = load_tokens()
    print(f"Found {len(tokens)} registered devices.")

    title = "TESTE: TRIGGER MANUAL"
    body = "Estimativa: +0%\nIsso é um teste de verificação de sistema."
    data = {"url": "https://google.com"}

    # 1. Save to DB (Dash update)
    save_signal(title, body, data)

    # 2. Send Push
    for token in tokens:
        print(f"Sending to {token}...")
        try:
            send_push_notification(token, title, body, data)
            print("Success!")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    main()
