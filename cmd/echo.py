def execute(sender_id, args, send_message_func):
    if not args:
        send_message_func(sender_id, "Usage: !echo [message]")
        return

    message = " ".join(args)
    send_message_func(sender_id, message)
