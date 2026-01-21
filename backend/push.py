from exponent_server_sdk import (
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
from requests.exceptions import ConnectionError, HTTPError

def send_push_notification(token, title, message, data=None):
    """
    Sends a push notification to an Expo Push Token.
    """
    if not token:
        print("No push token provided. Skipping notification.")
        return

    try:
        response = PushClient().publish(
            PushMessage(to=token,
                        title=title,
                        body=message,
                        data=data)
        )
    except PushServerError as exc:
        print(f"Push Server Error: {exc.errors}")
        raise
    except (ConnectionError, HTTPError) as exc:
        print(f"Connection Error: {exc}")
        raise

    try:
        response.validate_response()
    except PushTicketError as exc:
        print(f"Push Ticket Error: {exc.push_response}")
        raise
