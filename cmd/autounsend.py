import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from functions.unsendMessage import (
    schedule_unsend,
    unsend_message,
    cancel_scheduled_unsend,
    get_scheduled_unsends,
    unsend_last_bot_message,
)


def execute(sender_id, args, context):
    send_message_func = context["send_message"]
    get_last_bot_message_details = context["get_last_bot_message_details"]

    if not args:
        send_message_func(
            sender_id,
            "🔄 **Auto-Unsend Commands:**\n\n"
            "**Basic Usage:**\n"
            "• `autounsend [seconds] [message]` - Send message that auto-deletes\n"
            "• `autounsend now` - Unsend last bot message immediately\n"
            "• `autounsend cancel [message_id]` - Cancel scheduled unsend\n"
            "• `autounsend list` - Show scheduled unsends\n\n"
            "**Examples:**\n"
            "• `autounsend 5 This message will disappear in 5 seconds`\n"
            "• `autounsend 10 Secret message!`\n"
            "• `autounsend now`\n\n"
            "**Limits:**\n"
            "• Min delay: 1 second\n"
            "• Max delay: 300 seconds (5 minutes)\n"
            "• Only works on bot's own messages",
        )
        return

    action = args[0].lower()

    if action == "now":
        result = unsend_last_bot_message(get_last_bot_message_details)
        if result and result.get("success"):
            send_message_func(sender_id, "✅ Last message unsent successfully!")
        else:
            error_msg = (
                result.get("error", "Unknown error") if result else "Unknown error"
            )
            send_message_func(
                sender_id, f"❌ Failed to unsend last message: {error_msg}"
            )
        return

    elif action == "cancel":
        if len(args) < 2:
            send_message_func(
                sender_id,
                "⚠️ Please provide a message ID to cancel.\nExample: `autounsend cancel m_abc123`",
            )
            return

        message_id = args[1]
        if cancel_scheduled_unsend(message_id):
            send_message_func(
                sender_id, f"✅ Cancelled scheduled unsend for message: {message_id}"
            )
        else:
            send_message_func(
                sender_id, f"❌ No scheduled unsend found for message: {message_id}"
            )
        return

    elif action == "list":
        scheduled = get_scheduled_unsends()
        if scheduled:
            message = "📋 **Scheduled Unsends:**\n\n"
            for i, msg_id in enumerate(scheduled, 1):
                message += f"{i}. `{msg_id}`\n"
            message += f"\n📊 Total: {len(scheduled)} message(s)"
        else:
            message = "📋 No messages scheduled for auto-unsend."
        send_message_func(sender_id, message)
        return

    try:
        delay_seconds = int(action)
        if delay_seconds < 1:
            send_message_func(sender_id, "⚠️ Delay must be at least 1 second.")
            return
        elif delay_seconds > 300:
            send_message_func(sender_id, "⚠️ Maximum delay is 300 seconds (5 minutes).")
            return

        if len(args) < 2:
            send_message_func(
                sender_id,
                "⚠️ Please provide a message to send.\nExample: `autounsend 10 This will disappear in 10 seconds`",
            )
            return

        message_text = " ".join(args[1:])

        temp_message = f"⏰ {message_text}\n\n🔄 This message will auto-delete in {delay_seconds} second{'s' if delay_seconds != 1 else ''}..."

        response = send_message_func(sender_id, temp_message)

        if response and response.get("message_id"):
            message_id = response["message_id"]
            if schedule_unsend(message_id, delay_seconds):
                pass
            else:
                send_message_func(
                    sender_id, "⚠️ Failed to schedule auto-unsend, but message was sent."
                )
        else:
            send_message_func(sender_id, "❌ Failed to send message.")

    except ValueError:
        send_message_func(
            sender_id,
            f"❌ Invalid delay time: '{action}'. Please use a number (1-300 seconds).\n"
            "💡 Example: `autounsend 5 Hello world`",
        )
    except Exception as e:
        send_message_func(sender_id, f"❌ Error processing command: {str(e)}")
