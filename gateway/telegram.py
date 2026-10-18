import requests

from exceptions import HansardGatewayError

_TELEGRAM_API_URL = "https://api.telegram.org"
_TELEGRAM_TIMEOUT_SECONDS = 10


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    try:
        response = requests.post(
            url=f"{_TELEGRAM_API_URL}/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=_TELEGRAM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    # NOTE: from None, because the request error's text holds the URL and so the bot token
    except requests.exceptions.RequestException:
        raise HansardGatewayError("Telegram message failed") from None
