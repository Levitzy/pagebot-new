def execute(sender_id, args, context):
    logger = context.get("logger")
    send_message_func = context.get("send_message")
    edit_bot_message_func = context.get("edit_bot_message")
    replied_to_message_id = context.get("replied_to_message_id")
    prefix = context.get("prefix", "!")

    if not logger or not send_message_func or not edit_bot_message_func:
        if logger:
            logger.error(
                "Edit command missing critical context functions (logger, send_message, or edit_bot_message)."
            )
        if send_message_func and callable(send_message_func):
            send_message_func(
                sender_id,
                "Error: Edit command could not be initialized properly. Please contact support.",
            )
        else:
            # If send_message_func is also missing, log to console if possible
            print(
                f"ERROR: Edit command for {sender_id} cannot initialize and cannot send message."
            )
        return

    if not args:
        send_message_func(
            sender_id,
            f"To edit my last message, please reply to it and use the command: {prefix}edit <your new message text>",
        )
        logger.info(
            f"Edit command called by {sender_id} without new text or not as a reply."
        )
        return

    if not replied_to_message_id:
        send_message_func(
            sender_id,
            f"Please reply to the message you want to edit, then use the command: {prefix}edit <your new message text>",
        )
        logger.info(
            f"Edit command by {sender_id} was not a reply to a specific message."
        )
        return

    new_text = " ".join(args)
    message_id_to_target_for_edit = replied_to_message_id

    logger.info(
        f"User {sender_id} attempting to 'edit' (via reply) message ID: {message_id_to_target_for_edit} with new text: '{new_text}'"
    )

    edit_response = edit_bot_message_func(
        message_id_to_target_for_edit, new_text, sender_id
    )

    if edit_response and edit_response.get("message_id"):
        logger.info(
            f"Bot's message 'edited' (new message sent in response to edit command) for user {sender_id}. New MID: {edit_response.get('message_id')}"
        )
        # The enhanced_send_message in server.py, if used by edit_bot_message_func,
        # would update the last_bot_message_id_store.
        # No explicit confirmation message here as edit_bot_message_func sends the "edited" content.
    else:
        logger.warning(
            f"Failed to 'edit' (send new message for) bot's message (ID: {message_id_to_target_for_edit}) for user {sender_id}."
        )
        send_message_func(
            sender_id, "Could not update the replied-to message. Please try again."
        )
