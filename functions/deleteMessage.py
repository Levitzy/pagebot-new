import requests
import json
import logging

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]


def delete_message(message_id):
    params = {"access_token": PAGE_ACCESS_TOKEN}

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{message_id}"

    try:
        response = requests.delete(url, params=params)
        if response.status_code != 200:
            logger.error(
                f"Failed to delete message: {response.status_code} {response.text}"
            )
        return response.json()
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
        return None
