import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def handle_gagstock_postback(sender_id, payload, send_message_func):
    """
    Handle gagstock-related postback events (button clicks)
    """
    logger.info(f"Handling gagstock postback for {sender_id}: {payload}")

    try:
        from cmd import gagstock

        if payload.startswith("gagstock_refresh_"):
            logger.info(f"Processing refresh request from {sender_id}")
            gagstock.handle_refresh(sender_id, send_message_func)

        elif payload.startswith("gagstock_stop_"):
            logger.info(f"Processing stop request from {sender_id}")
            gagstock.handle_stop(sender_id, send_message_func)

        else:
            logger.warning(f"Unknown gagstock payload: {payload}")
            send_message_func(sender_id, "⚠️ Unknown action. Please try again.")

    except ImportError as e:
        logger.error(f"Failed to import gagstock module: {e}")
        send_message_func(sender_id, "❌ Gagstock module not available.")

    except Exception as e:
        logger.error(f"Error in gagstock postback handler: {e}")
        send_message_func(sender_id, "❌ An error occurred processing your request.")


def get_handler_info():
    """
    Return information about this handler
    """
    return {
        "name": "gagstock_handler",
        "description": "Handles gagstock button interactions",
        "supported_payloads": ["gagstock_refresh_*", "gagstock_stop_*"],
    }
