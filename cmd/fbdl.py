import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fbvideo import FacebookVideoDownloader
from functions.sendTyping import send_typing_indicator
from functions.sendTemplate import (
    send_button_template,
    create_url_button,
    send_generic_template,
)


def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    if not args:
        send_message_func(
            sender_id,
            "Please provide a Facebook video URL.\nUsage: fbdl [video_fb_link]",
        )
        return

    url = args[0]

    if "facebook.com" not in url and "fb.watch" not in url:
        send_message_func(sender_id, "Please provide a valid Facebook video URL.")
        return

    send_typing_indicator(sender_id, True)
    send_message_func(sender_id, "🔄 Processing Facebook video... Please wait.")

    try:
        downloader = FacebookVideoDownloader()
        video_data = downloader.get_video_data(url)

        if "error" in video_data:
            send_message_func(sender_id, f"❌ Error: {video_data['error']}")
            return

        title = video_data.get("title", "Facebook Video")
        author = video_data.get("author", "Unknown")
        duration = video_data.get("duration", "0:00")
        thumbnail = video_data.get("thumbnail", "")

        video_url_hd = video_data.get("video_url_hd")
        video_url_sd = video_data.get("video_url_sd")
        video_url_auto = video_data.get("video_url_auto")
        quality_options = video_data.get("quality_options", [])

        info_message = f"✅ Facebook Video Found!\n\n"
        info_message += f"📝 Title: {title}\n"
        info_message += f"👤 Author: {author}\n"
        info_message += f"⏱️ Duration: {duration}\n\n"

        available_urls = []
        if video_url_hd:
            available_urls.append(("HD Quality", video_url_hd))
        if video_url_sd and video_url_sd != video_url_hd:
            available_urls.append(("SD Quality", video_url_sd))
        if video_url_auto and video_url_auto not in [video_url_hd, video_url_sd]:
            available_urls.append(("Auto Quality", video_url_auto))

        if quality_options and len(quality_options) > len(available_urls):
            for option in quality_options[:3]:
                quality_label = f"{option['quality']} ({option['size_mb']:.1f}MB)"
                if option["url"] not in [url for _, url in available_urls]:
                    available_urls.append((quality_label, option["url"]))

        if available_urls:
            if len(available_urls) <= 3:
                info_message += "Choose download quality:"
                buttons = []
                for label, download_url in available_urls:
                    buttons.append(create_url_button(label, download_url))
                send_button_template(sender_id, info_message, buttons)
            else:
                elements = []
                element = {
                    "title": title[:80],
                    "subtitle": f"By {author} • {duration}",
                    "buttons": [],
                }

                if thumbnail:
                    element["image_url"] = thumbnail

                for i, (label, download_url) in enumerate(available_urls[:3]):
                    element["buttons"].append(create_url_button(label, download_url))

                elements.append(element)
                send_generic_template(sender_id, elements)
        else:
            send_message_func(
                sender_id, info_message + "\n\n❌ No download links available."
            )

    except Exception as e:
        send_message_func(sender_id, f"❌ An unexpected error occurred: {str(e)}")
    finally:
        send_typing_indicator(sender_id, False)
