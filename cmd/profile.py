import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from functions.getUserProfile import get_user_profile


def execute(sender_id, args, send_message_func):
    user_profile = get_user_profile(sender_id)

    if not user_profile:
        send_message_func(
            sender_id, "Sorry, I couldn't retrieve your profile information."
        )
        return

    message = f"Your profile:\nName: {user_profile.get('first_name', '')} {user_profile.get('last_name', '')}"
    send_message_func(sender_id, message)
