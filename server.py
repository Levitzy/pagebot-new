from flask import Flask, request, jsonify
import json
import os
import importlib.util
import logging
from functions.sendMessage import send_message as original_send_message
from functions.sendTyping import send_typing_indicator
from functions.deleteMessage import delete_message

app = Flask(__name__)

try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    logging.critical("CRITICAL: config.json not found. Bot cannot start without it.")
    config = {}
except json.JSONDecodeError:
    logging.critical(
        "CRITICAL: config.json is not valid JSON. Please check its syntax."
    )
    config = {}

PAGE_ACCESS_TOKEN = config.get("page_access_token")
VERIFY_TOKEN = config.get("verify_token")
PREFIX = config.get("prefix", "!")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not PAGE_ACCESS_TOKEN:
    logger.critical(
        "CRITICAL: Page Access Token is missing from config.json. The bot will not be able to interact with Facebook API."
    )
if not VERIFY_TOKEN:
    logger.warning(
        "Warning: Verify Token is missing from config.json. Webhook verification might fail."
    )


last_bot_message_id_store = {"id": None}


def enhanced_send_message(recipient_id, message_text):
    if not PAGE_ACCESS_TOKEN:
        logger.error("Cannot send message: PAGE_ACCESS_TOKEN is not configured.")
        return None
    response_data = original_send_message(recipient_id, message_text)
    if response_data and response_data.get("message_id"):
        last_bot_message_id_store["id"] = response_data.get("message_id")
        logger.info(f"Stored last bot message ID: {last_bot_message_id_store['id']}")
    elif response_data:
        logger.warning(
            f"send_message response did not contain a message_id: {response_data}"
        )
    return response_data


cmd_modules = {}
cmd_dir = os.path.join(os.path.dirname(__file__), "cmd")
if os.path.isdir(cmd_dir):
    for filename in os.listdir(cmd_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            module_path = os.path.join(cmd_dir, filename)
            try:
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    cmd_modules[module_name] = module
                    logger.info(f"Loaded command module: {module_name}")
                else:
                    logger.error(
                        f"Could not load spec for module: {module_name} at {module_path}"
                    )
            except Exception as e:
                logger.error(
                    f"Error loading command module {module_name} from {module_path}: {str(e)}"
                )
else:
    logger.warning(
        f"Commands directory '{cmd_dir}' not found. No commands will be loaded."
    )


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    logger.info("Received GET request on /webhook for verification.")
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logger.info(
        f"Attempting verification: hub.mode='{mode}', hub.verify_token (received)='{token}', Expected VERIFY_TOKEN='{VERIFY_TOKEN}'"
    )

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("Webhook verified successfully!")
            return challenge, 200
        else:
            logger.error(
                f"Verification failed. Mode: '{mode}', Received token: '{token}', Expected token: '{VERIFY_TOKEN}'. Tokens do not match or mode is not 'subscribe'."
            )
            return "Verification Failed: Token mismatch or invalid mode.", 403
    else:
        logger.error(
            "Verification failed: 'hub.mode' or 'hub.verify_token' missing from query parameters."
        )
        return "Verification Failed: Missing parameters.", 400


@app.route("/webhook", methods=["POST"])
def webhook_handler():
    data = request.get_json()
    logger.info(
        f"Received POST request on /webhook with data: {json.dumps(data, indent=1)}"
    )

    if data and data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                if not sender_id:
                    logger.warning("Received messaging event without sender ID.")
                    continue

                if "message" in messaging_event:
                    message_data = messaging_event["message"]
                    message_text = message_data.get("text")
                    original_message_id_from_user = message_data.get("mid")

                    if message_text:
                        if PAGE_ACCESS_TOKEN:
                            send_typing_indicator(sender_id, True)
                        try:
                            process_message(
                                sender_id, message_text, original_message_id_from_user
                            )
                        finally:
                            if PAGE_ACCESS_TOKEN:
                                send_typing_indicator(sender_id, False)
                    else:
                        logger.info(
                            f"Received message event from {sender_id} without text content. MID: {original_message_id_from_user}"
                        )
                elif "postback" in messaging_event:
                    logger.info(
                        f"Received postback event from {sender_id}: {messaging_event.get('postback')}"
                    )
                elif "delivery" in messaging_event:
                    logger.debug(
                        f"Received delivery confirmation: {messaging_event.get('delivery')}"
                    )
                elif "read" in messaging_event:
                    logger.debug(
                        f"Received read receipt: {messaging_event.get('read')}"
                    )
                else:
                    logger.info(
                        f"Received unhandled messaging event type from {sender_id}: {messaging_event}"
                    )

    return "EVENT_RECEIVED", 200


def process_message(sender_id, message_text, original_message_id_from_user):
    if not PAGE_ACCESS_TOKEN:
        logger.error("Cannot process message: PAGE_ACCESS_TOKEN is not configured.")
        return

    logger.info(
        f"Processing message from {sender_id}: '{message_text}' (User's MID: {original_message_id_from_user})"
    )

    parts = message_text.split()
    if not parts:
        logger.warning(f"Received empty message text from {sender_id}.")
        return

    first_word = parts[0]
    command_candidate = ""
    args = parts[1:]

    is_prefixed_command = False
    actual_command_name = None

    if first_word.startswith(PREFIX):
        command_candidate = first_word[len(PREFIX) :].lower()
        is_prefixed_command = True
        if command_candidate in cmd_modules:
            actual_command_name = command_candidate
    else:
        command_candidate = first_word.lower()
        if command_candidate in cmd_modules:
            actual_command_name = command_candidate

    context = {
        "send_message": enhanced_send_message,
        "send_typing": send_typing_indicator,
        "delete_message": delete_message,
        "original_user_message_id": original_message_id_from_user,
        "get_last_bot_message_id": lambda: last_bot_message_id_store["id"],
        "prefix": PREFIX,
        "logger": logger,
        "config": config,
        "cmd_module_keys": list(cmd_modules.keys()),
    }

    try:
        if actual_command_name:
            command_module = cmd_modules[actual_command_name]
            logger.info(
                f"Executing command '{actual_command_name}' for user {sender_id} with args: {args}"
            )
            command_module.execute(sender_id, args, context)
        elif is_prefixed_command:
            logger.info(
                f"Unknown prefixed command '{command_candidate}' from user {sender_id}."
            )
            enhanced_send_message(sender_id, f"Unknown command: {command_candidate}")
        else:
            logger.info(
                f"No command matched for message from {sender_id}: '{message_text}'. Sending default reply."
            )
            enhanced_send_message(sender_id, f"You said: {message_text}")
    except Exception as e:
        logger.error(
            f"Error during command processing or sending default reply for user {sender_id}: {str(e)}",
            exc_info=True,
        )
        try:
            enhanced_send_message(
                sender_id, f"An error occurred while processing your request."
            )
        except Exception as send_err:
            logger.error(
                f"Failed to send error message to user {sender_id}: {str(send_err)}"
            )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask app on host 0.0.0.0 and port {port}")
    if not PAGE_ACCESS_TOKEN or not VERIFY_TOKEN:
        logger.critical(
            "FATAL: Bot cannot start due to missing PAGE_ACCESS_TOKEN or VERIFY_TOKEN in config.json."
        )
    else:
        app.run(host="0.0.0.0", port=port, debug=True)
