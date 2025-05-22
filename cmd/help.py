import os


def execute(sender_id, args, send_message_func):
    cmd_dir = os.path.dirname(__file__)
    commands = []

    for filename in os.listdir(cmd_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            command_name = filename[:-3]
            commands.append(command_name)

    if not commands:
        message = "No commands are available."
    else:
        message = "Available commands:\n"
        for cmd in sorted(commands):
            message += f"!{cmd}\n"

    send_message_func(sender_id, message)
