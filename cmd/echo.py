def execute(sender_id, args, context):
    send_message_func = context["send_message"]
    prefix = context["prefix"]

    if not args:
        send_message_func(sender_id, f"Usage: {prefix}echo [message] or echo [message]")
        return

    message = " ".join(args)
    send_message_func(sender_id, message)
