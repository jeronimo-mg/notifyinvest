import json
import requests
import time

TOKEN_FILE = '/opt/notifyinvest/backend/tokens.json'

def send_push_notification(token, title, body, data=None):
    url = "https://exp.host/--/api/v2/push/send"
    headers = {
        "Host": "exp.host",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json"
    }
    payload = {
        "to": token,
        "title": title,
        "body": body,
        "sound": "default",
        "data": data
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Sent to {token}: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending to {token}: {e}")

try:
    with open(TOKEN_FILE, 'r') as f:
        tokens = json.load(f)
    
    print(f"Found {len(tokens)} tokens in {TOKEN_FILE}")

    if not tokens:
        print("No tokens found! App registration failed.")
    else:
        print("Sending V3 Test messages...")
        link = "https://finance.yahoo.com/quote/PETR4.SA"
        
        for token in tokens:
            # Simulate a V3 Signal
            send_push_notification(
                token, 
                "PETR4: BUY", 
                "Estimativa: +3.5%\nPetrobras announce record dividends for Q4.",
                data={"url": link}
            )

except Exception as e:
    print(f"Error: {e}")
