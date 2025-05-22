import requests
import json
import logging

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]


def get_user_profile(user_id):
    params = {
        "fields": "first_name,last_name,profile_pic",
        "access_token": PAGE_ACCESS_TOKEN,
    }

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{user_id}"

    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            logger.error(
                f"Failed to get user profile: {response.status_code} {response.text}"
            )
            return None
        return response.json()
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        return None
