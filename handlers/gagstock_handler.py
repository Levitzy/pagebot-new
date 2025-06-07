import logging
import sys
import os
import importlib.util

logger = logging.getLogger(__name__)


def load_gagstock_module():
    """
    Dynamically load the gagstock module from cmd directory
    """
    try:
        # Get the path to the cmd directory
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd_dir = os.path.join(script_dir, "cmd")
        gagstock_path = os.path.join(cmd_dir, "gagstock.py")

        if not os.path.exists(gagstock_path):
            logger.error(f"gagstock.py not found at {gagstock_path}")
            return None

        # Load the module
        spec = importlib.util.spec_from_file_location("gagstock", gagstock_path)
        if spec and spec.loader:
            gagstock = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gagstock)
            logger.info("Successfully loaded gagstock module")
            return gagstock
        else:
            logger.error("Failed to create spec for gagstock module")
            return None

    except Exception as e:
        logger.error(f"Error loading gagstock module: {e}")
        return None


def handle_gagstock_postback(sender_id, payload, send_message_func):
    """
    Handle gagstock-related postback events (button clicks)
    """
    logger.info(f"Handling gagstock postback for {sender_id}: {payload}")

    try:
        # Load gagstock module dynamically
        gagstock = load_gagstock_module()

        if not gagstock:
            logger.error("Failed to load gagstock module")
            send_message_func(
                sender_id,
                "❌ Gagstock module not available. Please try the text commands: `gagstock refresh` or `gagstock off`",
            )
            return

        if payload.startswith("gagstock_refresh_"):
            logger.info(f"Processing refresh request from {sender_id}")
            if hasattr(gagstock, "handle_refresh"):
                gagstock.handle_refresh(sender_id, send_message_func)
            else:
                logger.error("gagstock module missing handle_refresh function")
                send_message_func(
                    sender_id,
                    "❌ Refresh function not available. Try: `gagstock refresh`",
                )

        elif payload.startswith("gagstock_stop_"):
            logger.info(f"Processing stop request from {sender_id}")
            if hasattr(gagstock, "handle_stop"):
                gagstock.handle_stop(sender_id, send_message_func)
            else:
                logger.error("gagstock module missing handle_stop function")
                send_message_func(
                    sender_id, "❌ Stop function not available. Try: `gagstock off`"
                )

        else:
            logger.warning(f"Unknown gagstock payload: {payload}")
            send_message_func(
                sender_id, "⚠️ Unknown action. Please try again or use text commands."
            )

    except Exception as e:
        logger.error(f"Error in gagstock postback handler: {e}", exc_info=True)
        send_message_func(
            sender_id,
            "❌ An error occurred. Try text commands: `gagstock refresh` or `gagstock off`",
        )


def get_handler_info():
    """
    Return information about this handler
    """
    return {
        "name": "gagstock_handler",
        "description": "Handles gagstock button interactions with dynamic module loading",
        "supported_payloads": ["gagstock_refresh_*", "gagstock_stop_*"],
    }
