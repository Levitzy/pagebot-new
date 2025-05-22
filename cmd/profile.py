import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from functions.getUserProfile import get_user_profile


def execute(sender_id, args, context):
    send_message_func = context["send_message"]
    user_profile = get_user_profile(sender_id)

    if not user_profile:
        send_message_func(
            sender_id, "Sorry, I couldn't retrieve your profile information."
        )
        return

    first_name = user_profile.get("first_name", "")
    last_name = user_profile.get("last_name", "")

    message = f"Your profile:\nName: {first_name} {last_name}".strip()
    if not first_name and not last_name:
        message = "Your profile:\nName: Not available"

    send_message_func(sender_id, message)
