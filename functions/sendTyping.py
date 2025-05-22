import requests
import json
import logging

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]


def send_typing_indicator(recipient_id, typing_on=True):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "sender_action": "typing_on" if typing_on else "typing_off",
    }

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

    try:
        response = requests.post(url, params=params, headers=headers, json=data)
        if response.status_code != 200:
            logger.error(
                f"Failed to send typing indicator: {response.status_code} {response.text}"
            )
        return response.json()
    except Exception as e:
        logger.error(f"Error sending typing indicator: {str(e)}")
        return None
