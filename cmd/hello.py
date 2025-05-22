def execute(sender_id, args, send_message_func):
    if args:
        name = " ".join(args)
        message = f"Hello, {name}! Nice to meet you."
    else:
        message = "Hello there! How can I help you today?"

    send_message_func(sender_id, message)
