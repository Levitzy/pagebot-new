def execute(sender_id, args, context):
    # This command will now attempt to delete the last message sent by the bot.
    get_last_bot_mid_func = context.get("get_last_bot_message_id")
    delete_func = context.get("delete_message")
    logger = context.get("logger")
    send_message_func = context.get("send_message")

    if not all([get_last_bot_mid_func, delete_func, logger, send_message_func]):
        if logger:
            logger.error("Delete command missing necessary context functions.")
        if context.get(
            "send_message"
        ):  # Use the original send_message from context if available
            context["send_message"](
                sender_id, "Error: Delete command could not be initialized properly."
            )
        return

    message_id_to_delete = get_last_bot_mid_func()

    if message_id_to_delete:
        logger.info(
            f"Attempting to delete BOT'S last message ID: {message_id_to_delete} for user {sender_id}"
        )
        try:
            result = delete_func(message_id_to_delete)
            if result and result.get("success"):
                logger.info(
                    f"Successfully deleted bot's message ID: {message_id_to_delete}"
                )
                send_message_func(
                    sender_id,
                    f"Bot's last message (ID: ...{message_id_to_delete[-10:]}) deleted.",
                )
            elif result:
                logger.warning(
                    f"Failed to delete bot's message ID: {message_id_to_delete}. Response: {result}"
                )
                send_message_func(
                    sender_id,
                    f"Could not delete bot's last message. API Response: {result.get('error', {}).get('message', 'Unknown error')}",
                )
            else:
                logger.error(
                    f"Delete function returned None or unexpected result for bot message ID: {message_id_to_delete}"
                )
                send_message_func(
                    sender_id,
                    "Failed to delete bot's last message (unexpected API response).",
                )

        except Exception as e:
            logger.error(
                f"Exception during bot message deletion ({message_id_to_delete}): {str(e)}"
            )
            send_message_func(
                sender_id,
                "An error occurred while trying to delete the bot's last message.",
            )
    else:
        logger.warning(
            f"Delete command called by user {sender_id}, but no bot message ID was stored to delete."
        )
        send_message_func(sender_id, "There's no recent bot message stored to delete.")
