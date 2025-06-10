import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tiktokscrape import TikTokScraper
from functions.sendTyping import send_typing_indicator
from functions.sendTemplate import send_button_template, create_url_button
import tempfile
import requests


def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    if not args:
        send_message_func(
            sender_id,
            "Please provide a TikTok video URL.\nUsage: tiktokdl [video_tiktok_link]",
        )
        return

    url = args[0]

    if (
        "tiktok.com" not in url
        and "vm.tiktok.com" not in url
        and "vt.tiktok.com" not in url
    ):
        send_message_func(sender_id, "Please provide a valid TikTok URL.")
        return

    send_typing_indicator(sender_id, True)
    send_message_func(sender_id, "🔄 Processing TikTok video... Please wait.")

    try:
        scraper = TikTokScraper()
        video_data = scraper.get_video_data(url)

        if "error" in video_data:
            send_message_func(sender_id, f"❌ Error: {video_data['error']}")
            return

        title = video_data.get("title", "TikTok Video")
        author = video_data.get("author", "Unknown")
        duration = video_data.get("duration", "0:00")

        video_url_no_watermark = video_data.get("video_url_no_watermark")
        video_url_watermark = video_data.get("video_url_watermark")

        info_message = f"✅ TikTok Video Found!\n\n"
        info_message += f"📝 Title: {title}\n"
        info_message += f"👤 Author: @{author}\n"
        info_message += f"⏱️ Duration: {duration}\n\n"

        if video_url_no_watermark or video_url_watermark:
            info_message += "Choose download option:"

            buttons = []

            if video_url_no_watermark:
                buttons.append(
                    create_url_button("No Watermark", video_url_no_watermark)
                )

            if video_url_watermark and video_url_watermark != video_url_no_watermark:
                buttons.append(create_url_button("With Watermark", video_url_watermark))

            if len(buttons) > 0:
                send_button_template(sender_id, info_message, buttons)
            else:
                send_message_func(
                    sender_id, info_message + "\n\n❌ No download links available."
                )
        else:
            send_message_func(
                sender_id, info_message + "\n\n❌ No download links found."
            )

    except Exception as e:
        send_message_func(sender_id, f"❌ An unexpected error occurred: {str(e)}")
    finally:
        send_typing_indicator(sender_id, False)
