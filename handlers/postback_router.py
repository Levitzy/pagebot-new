import logging
import importlib
import os

logger = logging.getLogger(__name__)


class PostbackRouter:
    def __init__(self):
        self.handlers = {}
        self.load_handlers()

    def load_handlers(self):
        """
        Dynamically load all handler modules from the handlers directory
        """
        handlers_dir = os.path.dirname(__file__)

        for filename in os.listdir(handlers_dir):
            if filename.endswith("_handler.py"):
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(f"handlers.{module_name}")

                    if hasattr(module, "get_handler_info"):
                        handler_info = module.get_handler_info()
                        self.handlers[handler_info["name"]] = module
                        logger.info(f"Loaded postback handler: {handler_info['name']}")
                    else:
                        logger.warning(
                            f"Handler {module_name} missing get_handler_info function"
                        )

                except Exception as e:
                    logger.error(f"Failed to load handler {module_name}: {e}")

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
                    send_message_func(sender_id, "❌ Gagstock handler not available.")

            else:
                logger.warning(f"No handler found for payload: {payload}")
                send_message_func(sender_id, "⚠️ Button action not recognized.")

        except Exception as e:
            logger.error(f"Error routing postback {payload}: {e}")
            send_message_func(
                sender_id, "❌ An error occurred processing your request."
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


router = PostbackRouter()
