import requests
import json
import logging

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]


def send_message(recipient_id, message_text):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

    try:
        response = requests.post(url, params=params, headers=headers, json=data)
        response_data = response.json()
        if response.status_code != 200:
            logger.error(
                f"Failed to send message: {response.status_code} {response.text}"
            )
            return None
        logger.info(
            f"Message sent successfully to {recipient_id}. Response: {response_data}"
        )
        return response_data  # Return the full response which includes message_id
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return None
