from flask import Flask, request, jsonify
import json
import os
import importlib.util
import logging

# Attempt to import functions, handle if they are missing gracefully later if needed
try:
    from functions.sendMessage import send_message as original_send_message
    from functions.sendTyping import send_typing_indicator
    from functions.deleteMessage import delete_message

    FUNCTIONS_AVAILABLE = True
except ImportError as e:
    logging.critical(
        f"Failed to import one or more function modules: {e}. Bot functionality will be severely limited."
    )
    FUNCTIONS_AVAILABLE = False

    # Define dummy functions if imports fail, to prevent NameErrors later,
    # though the bot won't work correctly.
    def original_send_message(recipient_id, message_text):
        logging.error("sendMessage function not available.")
        return None

    def send_typing_indicator(recipient_id, typing_on=True):
        logging.error("sendTyping function not available.")
        return None

    def delete_message(message_id):
        logging.error("deleteMessage function not available.")
        return None


app = Flask(__name__)

# --- Configuration Loading ---
PAGE_ACCESS_TOKEN = None
VERIFY_TOKEN = None
PREFIX = "!"  # Default prefix

try:
    with open("config.json", "r") as f:
        config = json.load(f)
    PAGE_ACCESS_TOKEN = config.get("page_access_token")
    VERIFY_TOKEN = config.get("verify_token")
    PREFIX = config.get("prefix", "!")
except FileNotFoundError:
    logging.critical("CRITICAL: config.json not found. Bot cannot start without it.")
except json.JSONDecodeError:
    logging.critical(
        "CRITICAL: config.json is not valid JSON. Please check its syntax."
    )
except Exception as e:
    logging.critical(f"CRITICAL: An unexpected error occurred loading config.json: {e}")


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not FUNCTIONS_AVAILABLE:
    logger.critical(
        "One or more critical function modules (sendMessage, sendTyping, deleteMessage) are missing. Bot will not operate correctly."
    )
if not PAGE_ACCESS_TOKEN:
    logger.critical(
        "CRITICAL: Page Access Token is NOT configured in config.json or config.json is missing/invalid. The bot WILL NOT be able to interact with Facebook API."
    )
    logger.critical(
        "Ensure you have a VALID PAGE ACCESS TOKEN with 'pages_messaging' permission."
    )
if not VERIFY_TOKEN:
    logger.warning(
        "Warning: Verify Token is missing from config.json. Webhook verification might fail."
    )


# --- State for last bot message ID ---
last_bot_message_id_store = {"id": None}


# --- Enhanced Send Message Function ---
def enhanced_send_message(recipient_id, message_text):
    if not PAGE_ACCESS_TOKEN or not FUNCTIONS_AVAILABLE:
        logger.error(
            "Cannot send message: PAGE_ACCESS_TOKEN is not configured or sendMessage function is unavailable."
        )
        return None

    # Turn typing off before sending the actual message, as sending a message implies activity has finished.
    # However, Facebook often auto-turns off typing when a message is received by the user.
    # For explicit control, ensure it's off if it was on.
    # send_typing_indicator(recipient_id, False) # Optional: more aggressive typing off

    response_data = original_send_message(recipient_id, message_text)
    if response_data and response_data.get("message_id"):
        last_bot_message_id_store["id"] = response_data.get("message_id")
        logger.info(f"Stored last bot message ID: {last_bot_message_id_store['id']}")
    elif response_data:
        logger.warning(
            f"send_message response did not contain a message_id: {response_data}"
        )
    else:
        logger.error(f"Failed to send message to {recipient_id}. Text: {message_text}")
    return response_data


# --- Command Module Loading ---
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


# --- Webhook Verification Route ---
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
        if VERIFY_TOKEN and mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("Webhook verified successfully!")
            return challenge, 200
        else:
            logger.error(
                f"Verification failed. Mode: '{mode}', Received token: '{token}', Expected token: '{VERIFY_TOKEN}'. Tokens do not match, mode is not 'subscribe', or VERIFY_TOKEN is not configured."
            )
            return (
                "Verification Failed: Token mismatch, invalid mode, or server configuration error.",
                403,
            )
    else:
        logger.error(
            "Verification failed: 'hub.mode' or 'hub.verify_token' missing from query parameters."
        )
        return "Verification Failed: Missing parameters.", 400


# --- Webhook Message Handling Route ---
@app.route("/webhook", methods=["POST"])
def webhook_handler():
    data = request.get_json()
    logger.info(
        f"Received POST request on /webhook with data: {json.dumps(data, indent=1)}"
    )  # Indent for readability

    if not PAGE_ACCESS_TOKEN or not FUNCTIONS_AVAILABLE:
        logger.error(
            "Webhook handling aborted: PAGE_ACCESS_TOKEN not configured or core functions unavailable."
        )
        return "SERVER_ERROR_NO_TOKEN_OR_FUNCTIONS", 500

    if data and data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                if not sender_id:
                    logger.warning("Received messaging event without sender ID.")
                    continue

                # Default to typing off, will be turned on if processing a message
                # and turned off again in finally.
                is_typing_on = False
                try:
                    if "message" in messaging_event:
                        message_data = messaging_event["message"]
                        message_text = message_data.get("text")
                        original_message_id_from_user = message_data.get("mid")

                        if message_text:
                            send_typing_indicator(sender_id, True)
                            is_typing_on = True
                            process_message(
                                sender_id, message_text, original_message_id_from_user
                            )
                        else:
                            logger.info(
                                f"Received message event from {sender_id} without text content. MID: {original_message_id_from_user}"
                            )
                    # Handle other event types if necessary
                    elif "postback" in messaging_event:
                        logger.info(
                            f"Received postback event from {sender_id}: {messaging_event.get('postback')}"
                        )
                        # process_postback(sender_id, messaging_event.get('postback')) # Example
                    # ... other event types like delivery, read
                except Exception as e:
                    logger.error(
                        f"Error in webhook_handler main loop for sender {sender_id}: {e}",
                        exc_info=True,
                    )
                finally:
                    if is_typing_on:  # Only turn off if it was turned on
                        send_typing_indicator(sender_id, False)

    return "EVENT_RECEIVED", 200


# --- Message Processing Logic ---
def process_message(sender_id, message_text, original_message_id_from_user):
    # PAGE_ACCESS_TOKEN and FUNCTIONS_AVAILABLE already checked before calling this
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

    # Determine command
    if first_word.startswith(PREFIX):
        command_candidate = first_word[len(PREFIX) :].lower()
        is_prefixed_command = True
        if command_candidate in cmd_modules:
            actual_command_name = command_candidate
    else:
        command_candidate = first_word.lower()
        if command_candidate in cmd_modules:  # Allow commands without prefix
            actual_command_name = command_candidate

    context = {
        "send_message": enhanced_send_message,
        "send_typing": send_typing_indicator,  # Commands generally should not control typing on/off
        "delete_message": delete_message,
        "original_user_message_id": original_message_id_from_user,
        "get_last_bot_message_id": lambda: last_bot_message_id_store["id"],
        "prefix": PREFIX,
        "logger": logger,
        "config": config,  # Pass the loaded config dict
        "cmd_module_keys": list(cmd_modules.keys()),
    }

    try:
        if actual_command_name:
            command_module = cmd_modules[actual_command_name]
            logger.info(
                f"Executing command '{actual_command_name}' for user {sender_id} with args: {args}"
            )
            command_module.execute(sender_id, args, context)
        elif is_prefixed_command:  # Only a prefixed command was attempted but not found
            logger.info(
                f"Unknown prefixed command '{command_candidate}' from user {sender_id}."
            )
            enhanced_send_message(sender_id, f"Unknown command: {command_candidate}")
        else:  # No prefix, and not a recognized command word
            logger.info(
                f"No command matched for message from {sender_id}: '{message_text}'. Sending default reply."
            )
            enhanced_send_message(sender_id, f"You said: {message_text}")
    except Exception as e:
        logger.error(
            f"Error during command execution or sending default reply for user {sender_id}: {str(e)}",
            exc_info=True,
        )
        try:
            # Avoid calling enhanced_send_message if the error was within it, to prevent loops
            original_send_message(
                sender_id, f"An error occurred while processing your request."
            )
        except Exception as send_err:
            logger.error(
                f"CRITICAL: Failed to send error message to user {sender_id} after a processing error: {str(send_err)}"
            )


# --- Main Application Runner ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask app on host 0.0.0.0 and port {port}")
    if not PAGE_ACCESS_TOKEN or not VERIFY_TOKEN or not FUNCTIONS_AVAILABLE:
        logger.critical(
            "FATAL: Bot cannot start properly due to missing critical configurations (PAGE_ACCESS_TOKEN, VERIFY_TOKEN) or unavailable function modules. Please check config.json and function imports."
        )
        # Optionally, exit here if you don't want Flask to run in a broken state
        # import sys
        # sys.exit(1)

    # Turn off debug mode for production on Render
    app.run(host="0.0.0.0", port=port, debug=False)  # Set debug=False for production
