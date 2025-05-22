def execute(sender_id, args, context):
    logger = context.get("logger")
    send_message_func = context.get(
        "send_message"
    )  # This is enhanced_send_message from server.py
    edit_bot_message_func = context.get("edit_bot_message")
    get_last_bot_details_func = context.get("get_last_bot_message_details")

    if not all(
        [logger, send_message_func, edit_bot_message_func, get_last_bot_details_func]
    ):
        if logger:
            logger.error("Edit command missing necessary context functions.")
        # Avoid sending message if send_message_func itself is missing
        if send_message_func and callable(send_message_func):
            send_message_func(
                sender_id, "Error: Edit command could not be initialized properly."
            )
        return

    if not args:
        send_message_func(
            sender_id, f"Usage: {context.get('prefix', '!')}edit <new message text>"
        )
        logger.info(f"Edit command called by {sender_id} without new text.")
        return

    new_text = " ".join(args)
    last_bot_mid, last_bot_recipient_id = get_last_bot_details_func()

    if (
        last_bot_mid and last_bot_recipient_id == sender_id
    ):  # Ensure we're "editing" a message sent to this user
        logger.info(
            f"User {sender_id} attempting to 'edit' bot's last message (ID: {last_bot_mid}) with text: '{new_text}'"
        )

        # Initialize editMessage config if not already done (this is a bit of a workaround for module-level config)
        # A better approach is dependency injection or ensuring config is loaded before this module.
        # For now, assuming server.py calls init_edit_message_config.
        # If functions.editMessage.PAGE_ACCESS_TOKEN is None: # Check if config needs to be passed
        #    from functions import editMessage # Re-import to access module directly
        #    editMessage.init_edit_message_config(context.get('config'))

        edit_response = edit_bot_message_func(last_bot_mid, new_text, sender_id)

        if edit_response and edit_response.get("message_id"):
            # The enhanced_send_message (aliased as send_message_func here if edit_bot_message_func uses it)
            # would have already updated the last_bot_message_id_store with the new message ID.
            logger.info(
                f"Bot's message 'edited' (new message sent) for user {sender_id}. New MID: {edit_response.get('message_id')}"
            )
            # No need to send another confirmation if edit_bot_message_func already implies it or if it's clear.
            # send_message_func(sender_id, f"Previous message has been updated with new content.")
        else:
            logger.warning(
                f"Failed to 'edit' (send new message for) bot's last message for user {sender_id}."
            )
            send_message_func(sender_id, "Could not update the previous message.")

    elif last_bot_mid and last_bot_recipient_id != sender_id:
        logger.warning(
            f"User {sender_id} tried to edit last bot message, but it was sent to a different recipient ({last_bot_recipient_id})."
        )
        send_message_func(
            sender_id,
            "Cannot edit the last message as it wasn't sent to you in this context.",
        )
    else:
        logger.info(
            f"Edit command called by user {sender_id}, but no recent bot message to this user was found to 'edit'."
        )
        send_message_func(
            sender_id, "There's no recent message from me to you to edit."
        )
