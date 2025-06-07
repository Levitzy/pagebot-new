import logging
import os
import sys

logger = logging.getLogger(__name__)


class PostbackRouter:
    def __init__(self):
        self.handlers = {}
        self.load_handlers()

    def load_handlers(self):
        """
        Load all handler modules from the handlers directory
        """
        try:
            # Import gagstock handler directly
            from . import gagstock_handler

            self.handlers["gagstock_handler"] = gagstock_handler
            logger.info("Loaded gagstock_handler successfully")

        except Exception as e:
            logger.error(f"Failed to load gagstock_handler: {e}")

    def route_postback(self, sender_id, payload, send_message_func):
        """
        Route postback to appropriate handler based on payload prefix
        """
        logger.info(f"Routing postback: {payload} from {sender_id}")

        try:
            if payload.startswith("gagstock_"):
                if "gagstock_handler" in self.handlers:
                    handler = self.handlers["gagstock_handler"]
                    handler.handle_gagstock_postback(
                        sender_id, payload, send_message_func
                    )
                else:
                    logger.error("Gagstock handler not loaded")
                    send_message_func(
                        sender_id,
                        "❌ Gagstock handler not available. Try text commands: `gagstock refresh` or `gagstock off`",
                    )

            else:
                logger.warning(f"No handler found for payload: {payload}")
                send_message_func(
                    sender_id,
                    "⚠️ Button action not recognized. Try using text commands instead.",
                )

        except Exception as e:
            logger.error(f"Error routing postback {payload}: {e}", exc_info=True)
            send_message_func(
                sender_id,
                "❌ An error occurred processing your request. Try using text commands instead.",
            )

    def get_loaded_handlers(self):
        """
        Return list of loaded handlers
        """
        return list(self.handlers.keys())

    def reload_handlers(self):
        """
        Reload all handlers (useful for development)
        """
        self.handlers.clear()
        self.load_handlers()
        logger.info("Reloaded all postback handlers")


# Create global router instance
router = PostbackRouter()
