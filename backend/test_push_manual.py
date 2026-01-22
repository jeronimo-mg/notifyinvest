
import sys
import os

# Add libs to path imports work
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))

try:
    from push import send_push_notification
except ImportError:
    from backend.push import send_push_notification

try:
    token = open('/opt/notifyinvest/backend/token.txt').read().strip()
    print(f"Sending test push to {token}")
    send_push_notification(token, "[Cloud ☁️] Teste Manual", "Teste forçado de notificação da nuvem! Se estivesse parado, agora você sabe que voltou a funcionar.")
except Exception as e:
    print(f"Error: {e}")
