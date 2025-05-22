import os


def execute(sender_id, args, context):
    send_message_func = context["send_message"]
    prefix = context["prefix"]

    available_commands = sorted(context.get("cmd_module_keys", []))

    if not available_commands:
        message = "No commands are available."
    else:
        message = "Available commands:\n"
        message += f"You can use commands with the prefix '{prefix}' (e.g., {prefix}help) or without a prefix (e.g., help).\n\n"
        for cmd_name in available_commands:
            message += f"- {cmd_name}\n"

    send_message_func(sender_id, message)
