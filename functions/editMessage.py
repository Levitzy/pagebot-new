import requests
import json
import logging

logger = logging.getLogger(__name__)

# This function needs to be loaded after config is loaded in server.py
# or config needs to be passed to it. For simplicity, assuming config is loaded globally
# For a better design, PAGE_ACCESS_TOKEN and GRAPH_API_VERSION would be passed as arguments.

PAGE_ACCESS_TOKEN = None
GRAPH_API_VERSION = None


def init_edit_message_config(config):
    global PAGE_ACCESS_TOKEN, GRAPH_API_VERSION
    PAGE_ACCESS_TOKEN = config.get("page_access_token")
    GRAPH_API_VERSION = config.get(
        "graph_api_version", "v19.0"
    )  # Default if not in config


def edit_bot_message(message_id_to_edit, new_text, recipient_id):
    """
    Attempts to "edit" a message. Since Facebook API does not support
    direct editing of Page messages, this function will send a new message
    indicating it's an update to a previous one.
    It does NOT delete the original message.
    """
    if not PAGE_ACCESS_TOKEN:
        logger.error("edit_bot_message: PAGE_ACCESS_TOKEN not configured.")
        return None

    logger.info(
        f"Attempting to 'edit' message ID {message_id_to_edit} for recipient {recipient_id} with new text: {new_text}"
    )

    # Inform the user that direct editing isn't supported and send a new message.
    # For a true "edit" (delete + send new), the deleteMessage function would be needed.

    edited_message_text = f"[Edited Content for previous message (ID ending ...{message_id_to_edit[-6:] if message_id_to_edit else 'N/A'} )]:\n{new_text}"

    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {"recipient": {"id": recipient_id}, "message": {"text": edited_message_text}}

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

    try:
        response = requests.post(url, params=params, headers=headers, json=data)
        response_data = response.json()
        if response.status_code == 200 and response_data.get("message_id"):
            logger.info(
                f"'Edited' message sent successfully to {recipient_id}. New MID: {response_data.get('message_id')}. Original attempted edit for MID: {message_id_to_edit}"
            )
            return response_data
        else:
            logger.error(
                f"Failed to send 'edited' message (new message): {response.status_code} {response.text}. Original MID for edit: {message_id_to_edit}"
            )
            return None
    except Exception as e:
        logger.error(
            f"Error sending 'edited' message (new message): {str(e)}. Original MID for edit: {message_id_to_edit}"
        )
        return None


# In server.py, after loading config, you would call:
# from functions import editMessage
# editMessage.init_edit_message_config(config_data) # where config_data is the loaded config dictionary
