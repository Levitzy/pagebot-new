import requests
import json
import logging

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]


def send_template_message(recipient_id, template_payload):
    """
    Send a template message to a recipient

    Args:
        recipient_id (str): The recipient's Facebook user ID
        template_payload (dict): The template payload containing template data

    Returns:
        dict: Response from Facebook API or None if failed
    """
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN not configured")
        return None

    if not recipient_id:
        logger.error("recipient_id is required")
        return None

    if not template_payload:
        logger.error("template_payload is required")
        return None

    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"attachment": {"type": "template", "payload": template_payload}},
    }

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

    try:
        logger.debug(
            f"Sending template message to {recipient_id}: {json.dumps(template_payload, indent=2)}"
        )

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=30
        )
        response_data = response.json()

        if response.status_code == 200:
            logger.info(
                f"Template message sent successfully to {recipient_id}. Message ID: {response_data.get('message_id', 'N/A')}"
            )
            return response_data
        else:
            logger.error(
                f"Failed to send template message to {recipient_id}: {response.status_code} - {response.text}"
            )
            return None

    except requests.exceptions.Timeout:
        logger.error(f"Timeout sending template message to {recipient_id}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(
            f"Request error sending template message to {recipient_id}: {str(e)}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error sending template message to {recipient_id}: {str(e)}"
        )
        return None


def send_button_template(recipient_id, text, buttons):
    """
    Send a button template message

    Args:
        recipient_id (str): The recipient's Facebook user ID
        text (str): The message text (max 640 characters)
        buttons (list): List of button objects

    Returns:
        dict: Response from Facebook API or None if failed
    """
    if not text:
        logger.error("text is required for button template")
        return None

    if not buttons or not isinstance(buttons, list):
        logger.error("buttons must be a non-empty list")
        return None

    if len(buttons) > 3:
        logger.warning(
            f"Button template supports max 3 buttons, got {len(buttons)}. Using first 3."
        )
        buttons = buttons[:3]

    if len(text) > 640:
        logger.warning(
            f"Button template text too long ({len(text)} chars). Truncating to 640 chars."
        )
        text = text[:637] + "..."

    template_payload = {"template_type": "button", "text": text, "buttons": buttons}

    logger.debug(
        f"Sending button template to {recipient_id} with {len(buttons)} buttons"
    )
    return send_template_message(recipient_id, template_payload)


def send_generic_template(recipient_id, elements):
    """
    Send a generic template (carousel) message

    Args:
        recipient_id (str): The recipient's Facebook user ID
        elements (list): List of element objects for the carousel

    Returns:
        dict: Response from Facebook API or None if failed
    """
    if not elements or not isinstance(elements, list):
        logger.error("elements must be a non-empty list")
        return None

    if len(elements) > 10:
        logger.warning(
            f"Generic template supports max 10 elements, got {len(elements)}. Using first 10."
        )
        elements = elements[:10]

    template_payload = {"template_type": "generic", "elements": elements}

    logger.debug(
        f"Sending generic template to {recipient_id} with {len(elements)} elements"
    )
    return send_template_message(recipient_id, template_payload)


def send_quick_reply(recipient_id, text, quick_replies):
    """
    Send a message with quick reply buttons

    Args:
        recipient_id (str): The recipient's Facebook user ID
        text (str): The message text
        quick_replies (list): List of quick reply objects

    Returns:
        dict: Response from Facebook API or None if failed
    """
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN not configured")
        return None

    if not text:
        logger.error("text is required for quick reply")
        return None

    if not quick_replies or not isinstance(quick_replies, list):
        logger.error("quick_replies must be a non-empty list")
        return None

    if len(quick_replies) > 11:
        logger.warning(
            f"Quick replies support max 11 items, got {len(quick_replies)}. Using first 11."
        )
        quick_replies = quick_replies[:11]

    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text, "quick_replies": quick_replies},
    }

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

    try:
        logger.debug(
            f"Sending quick reply to {recipient_id} with {len(quick_replies)} options"
        )

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=30
        )
        response_data = response.json()

        if response.status_code == 200:
            logger.info(
                f"Quick reply sent successfully to {recipient_id}. Message ID: {response_data.get('message_id', 'N/A')}"
            )
            return response_data
        else:
            logger.error(
                f"Failed to send quick reply to {recipient_id}: {response.status_code} - {response.text}"
            )
            return None

    except Exception as e:
        logger.error(f"Error sending quick reply to {recipient_id}: {str(e)}")
        return None


def create_postback_button(title, payload):
    """
    Helper function to create a postback button

    Args:
        title (str): Button text (max 20 chars)
        payload (str): Postback payload (max 1000 chars)

    Returns:
        dict: Button object
    """
    if len(title) > 20:
        logger.warning(
            f"Button title too long ({len(title)} chars). Truncating to 20 chars."
        )
        title = title[:20]

    if len(payload) > 1000:
        logger.warning(
            f"Button payload too long ({len(payload)} chars). Truncating to 1000 chars."
        )
        payload = payload[:1000]

    return {"type": "postback", "title": title, "payload": payload}


def create_url_button(title, url, webview_height_ratio="tall"):
    """
    Helper function to create a URL button

    Args:
        title (str): Button text (max 20 chars)
        url (str): URL to open
        webview_height_ratio (str): Height of webview ("compact", "tall", "full")

    Returns:
        dict: Button object
    """
    if len(title) > 20:
        logger.warning(
            f"Button title too long ({len(title)} chars). Truncating to 20 chars."
        )
        title = title[:20]

    return {
        "type": "web_url",
        "title": title,
        "url": url,
        "webview_height_ratio": webview_height_ratio,
    }


def create_quick_reply_text(title, payload):
    """
    Helper function to create a text quick reply

    Args:
        title (str): Quick reply text (max 20 chars)
        payload (str): Payload sent when tapped (max 1000 chars)

    Returns:
        dict: Quick reply object
    """
    if len(title) > 20:
        logger.warning(
            f"Quick reply title too long ({len(title)} chars). Truncating to 20 chars."
        )
        title = title[:20]

    if len(payload) > 1000:
        logger.warning(
            f"Quick reply payload too long ({len(payload)} chars). Truncating to 1000 chars."
        )
        payload = payload[:1000]

    return {"content_type": "text", "title": title, "payload": payload}


def validate_template_payload(template_payload):
    """
    Validate template payload structure

    Args:
        template_payload (dict): The template payload to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(template_payload, dict):
        logger.error("Template payload must be a dictionary")
        return False

    template_type = template_payload.get("template_type")
    if not template_type:
        logger.error("Template payload missing template_type")
        return False

    if template_type == "button":
        if "text" not in template_payload:
            logger.error("Button template missing text")
            return False
        if "buttons" not in template_payload:
            logger.error("Button template missing buttons")
            return False

    elif template_type == "generic":
        if "elements" not in template_payload:
            logger.error("Generic template missing elements")
            return False

    return True
