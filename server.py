from flask import Flask, request, jsonify
import json
import os
import importlib.util
import logging
import sys

FUNCTIONS_AVAILABLE = True
original_send_message = None
send_typing_indicator = None
edit_bot_message = None
config_data = {}

try:
    with open("config.json", "r") as f:
        config_data = json.load(f)
except FileNotFoundError:
    logging.critical("CRITICAL: config.json not found. Bot cannot start without it.")
except json.JSONDecodeError:
    logging.critical(
        "CRITICAL: config.json is not valid JSON. Please check its syntax."
    )
except Exception as e:
    logging.critical(f"CRITICAL: An unexpected error occurred loading config.json: {e}")

try:
    from functions.sendMessage import send_message as original_send_message_imported

    original_send_message = original_send_message_imported
    from functions.sendTyping import (
        send_typing_indicator as send_typing_indicator_imported,
    )

    send_typing_indicator = send_typing_indicator_imported
    from functions.editMessage import (
        edit_bot_message as edit_bot_message_imported,
        init_edit_message_config,
    )

    edit_bot_message = edit_bot_message_imported
    if config_data:
        init_edit_message_config(config_data)
    else:
        logging.warning(
            "config_data not loaded, editMessage function might not be properly initialized."
        )

except ImportError as e:
    logging.critical(
        f"Failed to import one or more function modules: {e}. Bot functionality will be severely limited."
    )
    FUNCTIONS_AVAILABLE = False
    if not original_send_message:

        def original_send_message(recipient_id, message_text):
            logging.error("sendMessage function not available due to import error.")
            return None

    if not send_typing_indicator:

        def send_typing_indicator(recipient_id, typing_on=True):
            logging.error("sendTyping function not available due to import error.")
            return None

    if not edit_bot_message:

        def edit_bot_message(message_id, new_text, recipient_id):
            logging.error("editMessage function not available due to import error.")
            return None


try:
    from handlers.postback_router import router as postback_router

    POSTBACK_ROUTER_AVAILABLE = True
    logging.info("Postback router loaded successfully")
except ImportError as e:
    logging.error(f"Failed to load postback router: {e}")
    POSTBACK_ROUTER_AVAILABLE = False


app = Flask(__name__)

PAGE_ACCESS_TOKEN = config_data.get("page_access_token")
VERIFY_TOKEN = config_data.get("verify_token")
PREFIX = config_data.get("prefix", "!")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not FUNCTIONS_AVAILABLE:
    logger.critical(
        "One or more critical function modules (sendMessage, sendTyping, editMessage) are missing or failed to import. Bot will not operate correctly."
    )
if not PAGE_ACCESS_TOKEN:
    logger.critical(
        "CRITICAL: Page Access Token is NOT configured in config.json or config.json is missing/invalid. The bot WILL NOT be able to interact with Facebook API."
    )
if not VERIFY_TOKEN:
    logger.warning(
        "Warning: Verify Token is missing from config.json. Webhook verification might fail."
    )

if not POSTBACK_ROUTER_AVAILABLE:
    logger.warning(
        "Warning: Postback router not available. Button interactions will not work properly."
    )

last_bot_message_id_store = {"id": None, "recipient_id": None}


def enhanced_send_message(recipient_id, message_text):
    if not PAGE_ACCESS_TOKEN or not original_send_message:
        logger.error(
            "Cannot send message: PAGE_ACCESS_TOKEN is not configured or sendMessage function is unavailable."
        )
        return None

    response_data = original_send_message(recipient_id, message_text)
    if response_data and response_data.get("message_id"):
        last_bot_message_id_store["id"] = response_data.get("message_id")
        last_bot_message_id_store["recipient_id"] = recipient_id
        logger.info(
            f"Stored last bot message ID: {last_bot_message_id_store['id']} for recipient {recipient_id}"
        )
    elif response_data:
        logger.warning(
            f"send_message response did not contain a message_id: {response_data}"
        )
    else:
        logger.error(f"Failed to send message to {recipient_id}. Text: {message_text}")
    return response_data


cmd_modules = {}
cmd_dir = os.path.join(os.path.dirname(__file__), "cmd")
if os.path.isdir(cmd_dir):
    for filename in os.listdir(cmd_dir):
        if (
            filename.endswith(".py")
            and filename != "__init__.py"
            and filename != "delete.py"
        ):
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


@app.route("/webhook", methods=["POST"])
def webhook_handler():
    data = request.get_json()
    logger.info(
        f"Received POST request on /webhook with data: {json.dumps(data, indent=1)}"
    )

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

                is_typing_on = False
                replied_to_mid = None
                try:
                    if "message" in messaging_event:
                        message_data = messaging_event["message"]
                        message_text = message_data.get("text")
                        original_message_id_from_user = message_data.get("mid")

                        if message_data.get("reply_to"):
                            replied_to_mid = message_data["reply_to"].get("mid")

                        if message_text:
                            if send_typing_indicator:
                                send_typing_indicator(sender_id, True)
                                is_typing_on = True
                            process_message(
                                sender_id,
                                message_text,
                                original_message_id_from_user,
                                replied_to_mid,
                            )
                        else:
                            logger.info(
                                f"Received message event from {sender_id} without text content. MID: {original_message_id_from_user}"
                            )
                    elif "postback" in messaging_event:
                        postback_data = messaging_event.get("postback", {})
                        payload = postback_data.get("payload", "")
                        logger.info(
                            f"Received postback event from {sender_id}: {payload}"
                        )
                        if send_typing_indicator:
                            send_typing_indicator(sender_id, True)
                            is_typing_on = True
                        process_postback(sender_id, payload)
                except Exception as e:
                    logger.error(
                        f"Error in webhook_handler main loop for sender {sender_id}: {e}",
                        exc_info=True,
                    )
                finally:
                    if is_typing_on and send_typing_indicator:
                        send_typing_indicator(sender_id, False)

    return "EVENT_RECEIVED", 200


def process_postback(sender_id, payload):
    """
    Process postback events using the postback router
    """
    logger.info(f"Processing postback from {sender_id}: '{payload}'")

    try:
        if POSTBACK_ROUTER_AVAILABLE:
            postback_router.route_postback(sender_id, payload, enhanced_send_message)
        else:
            logger.error("Postback router not available")
            enhanced_send_message(sender_id, "❌ Button functionality not available.")

    except Exception as e:
        logger.error(
            f"Error processing postback for {sender_id}: {str(e)}", exc_info=True
        )
        enhanced_send_message(
            sender_id, "❌ An error occurred processing your request."
        )


def process_message(
    sender_id, message_text, original_message_id_from_user, replied_to_message_id
):
    logger.info(
        f"Processing message from {sender_id}: '{message_text}' (User's MID: {original_message_id_from_user}, Replied to MID: {replied_to_message_id})"
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
        "edit_bot_message": edit_bot_message,
        "original_user_message_id": original_message_id_from_user,
        "replied_to_message_id": replied_to_message_id,
        "get_last_bot_message_details": lambda: (
            last_bot_message_id_store["id"],
            last_bot_message_id_store["recipient_id"],
        ),
        "prefix": PREFIX,
        "logger": logger,
        "config": config_data,
        "cmd_module_keys": list(cmd_modules.keys()),
        "postback_router": postback_router if POSTBACK_ROUTER_AVAILABLE else None,
    }

    try:
        if actual_command_name:
            command_module = cmd_modules[actual_command_name]
            logger.info(
                f"Executing command '{actual_command_name}' for user {sender_id} with args: {args}"
            )
            if callable(getattr(command_module, "execute", None)):
                command_module.execute(sender_id, args, context)
            else:
                logger.error(
                    f"Command module {actual_command_name} does not have a callable 'execute' function."
                )
                enhanced_send_message(
                    sender_id,
                    f"Error: Command '{actual_command_name}' is not correctly configured.",
                )
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
            f"Error during command execution or sending default reply for user {sender_id}: {str(e)}",
            exc_info=True,
        )
        try:
            if original_send_message:
                original_send_message(
                    sender_id, f"An error occurred while processing your request."
                )
        except Exception as send_err:
            logger.error(
                f"CRITICAL: Failed to send error message to user {sender_id} after a processing error: {str(send_err)}"
            )


@app.route("/admin/handlers", methods=["GET"])
def get_handlers_info():
    """
    Admin endpoint to view loaded handlers
    """
    if POSTBACK_ROUTER_AVAILABLE:
        return jsonify(
            {
                "status": "success",
                "loaded_handlers": postback_router.get_loaded_handlers(),
                "postback_router_available": True,
            }
        )
    else:
        return jsonify(
            {
                "status": "error",
                "message": "Postback router not available",
                "postback_router_available": False,
            }
        )


@app.route("/admin/reload-handlers", methods=["POST"])
def reload_handlers():
    """
    Admin endpoint to reload handlers
    """
    if POSTBACK_ROUTER_AVAILABLE:
        try:
            postback_router.reload_handlers()
            return jsonify(
                {
                    "status": "success",
                    "message": "Handlers reloaded successfully",
                    "loaded_handlers": postback_router.get_loaded_handlers(),
                }
            )
        except Exception as e:
            return jsonify(
                {"status": "error", "message": f"Failed to reload handlers: {str(e)}"}
            )
    else:
        return jsonify({"status": "error", "message": "Postback router not available"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask app on host 0.0.0.0 and port {port}")
    if not PAGE_ACCESS_TOKEN or not VERIFY_TOKEN or not FUNCTIONS_AVAILABLE:
        logger.critical(
            "FATAL: Bot cannot start properly due to missing critical configurations or unavailable function modules."
        )

    if POSTBACK_ROUTER_AVAILABLE:
        logger.info(f"Loaded handlers: {postback_router.get_loaded_handlers()}")

    app.run(host="0.0.0.0", port=port, debug=False)
