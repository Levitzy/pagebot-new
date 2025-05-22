from flask import Flask, request, jsonify
import json
import os
import importlib.util
import logging
from functions.sendMessage import send_message
from functions.sendTyping import send_typing_indicator
from functions.deleteMessage import delete_message

app = Flask(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
VERIFY_TOKEN = config["verify_token"]
PREFIX = config.get("prefix", "!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cmd_modules = {}
cmd_dir = os.path.join(os.path.dirname(__file__), "cmd")
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
                logger.error(f"Could not load spec for module: {module_name}")
        except Exception as e:
            logger.error(f"Error loading command module {module_name}: {str(e)}")


@app.route("/", methods=["GET"])
def verify():
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == VERIFY_TOKEN
    ):
        logger.info("Webhook verified!")
        return request.args.get("hub.challenge")
    else:
        logger.error("Verification failed. The tokens do not match.")
        return "Verification Failed", 403


@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    logger.info(f"Received webhook data: {data}")

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                if not sender_id:
                    continue

                if "message" in messaging_event:
                    message_data = messaging_event["message"]
                    message_text = message_data.get("text")
                    original_message_id = message_data.get("mid")

                    if message_text:
                        process_message(sender_id, message_text, original_message_id)

    return "EVENT_RECEIVED", 200


def process_message(sender_id, message_text, original_message_id):
    send_typing_indicator(sender_id, True)
    logger.info(
        f"Processing message from {sender_id}: {message_text} (ID: {original_message_id})"
    )

    parts = message_text.split()
    if not parts:
        send_typing_indicator(sender_id, False)
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
        "send_message": send_message,
        "send_typing": send_typing_indicator,
        "delete_message": delete_message,
        "original_message_id": original_message_id,
        "prefix": PREFIX,
        "logger": logger,
        "config": config,
        "cmd_module_keys": list(cmd_modules.keys()),
    }

    if actual_command_name:
        command_module = cmd_modules[actual_command_name]
        try:
            command_module.execute(sender_id, args, context)
            logger.info(f"Executed command: {actual_command_name}")
        except Exception as e:
            logger.error(f"Error executing command {actual_command_name}: {str(e)}")
            send_message(sender_id, f"An error occurred while executing the command.")
    elif is_prefixed_command:
        send_message(sender_id, f"Unknown command: {command_candidate}")
    else:
        send_message(sender_id, f"You said: {message_text}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
