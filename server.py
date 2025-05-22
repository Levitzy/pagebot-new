from flask import Flask, request, jsonify
import json
import os
import importlib.util
import logging
from functions.sendMessage import send_message

app = Flask(__name__)

with open('config.json', 'r') as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config['page_access_token']
VERIFY_TOKEN = config['verify_token']

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cmd_modules = {}
cmd_dir = os.path.join(os.path.dirname(__file__), 'cmd')
for filename in os.listdir(cmd_dir):
    if filename.endswith('.py') and filename != '__init__.py':
        module_name = filename[:-3]
        module_path = os.path.join(cmd_dir, filename)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cmd_modules[module_name] = module
        logger.info(f"Loaded command module: {module_name}")

@app.route('/', methods=['GET'])
def verify():
    if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
        logger.info("Webhook verified!")
        return request.args.get('hub.challenge')
    else:
        logger.error("Verification failed. The tokens do not match.")
        return 'Verification Failed', 403

@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()
    logger.info(f"Received webhook data: {data}")

    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry.get('messaging', []):
                sender_id = messaging_event['sender']['id']
                
                if 'message' in messaging_event:
                    message_text = messaging_event['message'].get('text')
                    
                    if message_text:
                        process_message(sender_id, message_text)
                        
    return 'EVENT_RECEIVED', 200

def process_message(sender_id, message_text):
    logger.info(f"Processing message from {sender_id}: {message_text}")
    
    if message_text.startswith('!'):
        command = message_text[1:].split()[0].lower()
        args = message_text.split()[1:] if len(message_text.split()) > 1 else []
        
        if command in cmd_modules:
            try:
                cmd_modules[command].execute(sender_id, args, send_message)
                logger.info(f"Executed command: {command}")
            except Exception as e:
                logger.error(f"Error executing command {command}: {str(e)}")
                send_message(sender_id, f"Error executing command: {str(e)}")
        else:
            send_message(sender_id, f"Unknown command: {command}")
    else:
        send_message(sender_id, f"You said: {message_text}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)