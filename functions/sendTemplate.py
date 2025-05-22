import requests
import json
import logging

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]


def send_template_message(recipient_id, template_payload):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"attachment": {"type": "template", "payload": template_payload}},
    }

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

    try:
        response = requests.post(url, params=params, headers=headers, json=data)
        if response.status_code != 200:
            logger.error(
                f"Failed to send template message: {response.status_code} {response.text}"
            )
        return response.json()
    except Exception as e:
        logger.error(f"Error sending template message: {str(e)}")
        return None


def send_button_template(recipient_id, text, buttons):
    template_payload = {"template_type": "button", "text": text, "buttons": buttons}

    return send_template_message(recipient_id, template_payload)


def send_generic_template(recipient_id, elements):
    template_payload = {"template_type": "generic", "elements": elements}

    return send_template_message(recipient_id, template_payload)
