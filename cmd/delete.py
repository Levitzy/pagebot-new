def execute(sender_id, args, context):
    original_message_id = context.get("original_message_id")
    delete_func = context.get("delete_message")
    logger = context.get("logger")

    if not all([original_message_id, delete_func, logger]):
        if logger:
            logger.error(
                "Delete command missing necessary context (original_message_id, delete_function, or logger)."
            )
        if context.get("send_message"):
            context["send_message"](
                sender_id, "Error: Delete command could not be initialized."
            )
        return

    logger.info(
        f"Attempting to delete message ID: {original_message_id} for user {sender_id}"
    )
    try:
        result = delete_func(original_message_id)
        if result and result.get("success"):
            logger.info(f"Successfully deleted message ID: {original_message_id}")
        elif result:
            logger.warning(
                f"Failed to delete message ID: {original_message_id}. Response: {result}"
            )
            # context['send_message'](sender_id, "Could not delete the previous message.") # Optional feedback
        else:
            logger.error(
                f"Delete function returned None or unexpected result for message ID: {original_message_id}"
            )

    except Exception as e:
        logger.error(
            f"Exception during message deletion ({original_message_id}): {str(e)}"
        )
        # context['send_message'](sender_id, "An error occurred while trying to delete the message.") # Optional feedback
