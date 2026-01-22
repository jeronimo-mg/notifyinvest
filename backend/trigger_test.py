import json
import requests

TOKEN_FILE = '/opt/notifyinvest/backend/tokens.json'

def send_push_notification(token, title, body):
    url = "https://exp.host/--/api/v2/push/send"
    headers = {
        "Host": "exp.host",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json"
    }
    data = {
        "to": token,
        "title": title,
        "body": body,
        "sound": "default"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Sent to {token}: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending to {token}: {e}")

try:
    with open(TOKEN_FILE, 'r') as f:
        tokens = json.load(f)
    
    print(f"Found {len(tokens)} tokens in {TOKEN_FILE}:")
    print(tokens)

    if not tokens:
        print("No tokens found! App registration failed.")
    else:
        print("Sending test messages...")
        for token in tokens:
            send_push_notification(token, "Test Verification", "If you see this, the Release APK is working! \uD83D\uDE80")

except FileNotFoundError:
    print(f"File not found: {TOKEN_FILE}")
except Exception as e:
    print(f"Error: {e}")
