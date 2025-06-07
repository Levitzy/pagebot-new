import requests
import json
import logging
import threading
import time

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]

scheduled_unsends = {}


def unsend_message(message_id):
    if not message_id:
        logger.error("unsend_message: message_id is required")
        return None

    params = {"access_token": PAGE_ACCESS_TOKEN}
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{message_id}"

    try:
        response = requests.delete(url, params=params, timeout=10)
        response_data = response.json() if response.content else {}

        if response.status_code == 200:
            logger.info(f"Message {message_id} unsent successfully")
            return {"success": True, "message_id": message_id}
        else:
            logger.error(
                f"Failed to unsend message {message_id}: {response.status_code} {response.text}"
            )
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "message_id": message_id,
            }
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while unsending message {message_id}")
        return {"success": False, "error": "Timeout", "message_id": message_id}
    except Exception as e:
        logger.error(f"Error unsending message {message_id}: {str(e)}")
        return {"success": False, "error": str(e), "message_id": message_id}


def schedule_unsend(message_id, delay_seconds):
    if not message_id or delay_seconds <= 0:
        logger.error("schedule_unsend: invalid message_id or delay_seconds")
        return False

    def delayed_unsend():
        time.sleep(delay_seconds)
        if message_id in scheduled_unsends:
            result = unsend_message(message_id)
            if result and result.get("success"):
                logger.info(
                    f"Auto-unsent message {message_id} after {delay_seconds} seconds"
                )
            else:
                logger.error(f"Failed to auto-unsend message {message_id}")
            del scheduled_unsends[message_id]

    try:
        timer = threading.Thread(target=delayed_unsend, daemon=True)
        scheduled_unsends[message_id] = timer
        timer.start()
        logger.info(
            f"Scheduled unsend for message {message_id} in {delay_seconds} seconds"
        )
        return True
    except Exception as e:
        logger.error(f"Error scheduling unsend for message {message_id}: {str(e)}")
        return False


def cancel_scheduled_unsend(message_id):
    if message_id in scheduled_unsends:
        del scheduled_unsends[message_id]
        logger.info(f"Cancelled scheduled unsend for message {message_id}")
        return True
    return False


def get_scheduled_unsends():
    return list(scheduled_unsends.keys())


def unsend_last_bot_message(get_last_message_func):
    last_message_id, recipient_id = get_last_message_func()
    if last_message_id:
        return unsend_message(last_message_id)
    else:
        logger.warning("No last bot message found to unsend")
        return {"success": False, "error": "No last message found"}
