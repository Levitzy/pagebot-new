def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    if args:
        name = " ".join(args)
        message = f"Hello, {name}! Nice to meet you."
    else:
        message = "Hello there! How can I help you today?"

    send_message_func(sender_id, message)
