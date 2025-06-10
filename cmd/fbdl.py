import requests
import re
import json
import os
import time
import random
from urllib.parse import unquote, urlparse, parse_qs
import html
from datetime import datetime
import tempfile
import threading


class FacebookVideoDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.setup_session()

    def setup_session(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        self.session.headers.update(headers)

    def normalize_url(self, url):
        if "facebook.com" not in url and "fb.watch" not in url:
            return None

        if "fb.watch" in url:
            return url

        if "m.facebook.com" in url:
            url = url.replace("m.facebook.com", "www.facebook.com")

        if "/share/r/" in url:
            reel_id = self.extract_reel_id_from_share(url)
            if reel_id:
                return f"https://www.facebook.com/reel/{reel_id}"

        allowed_patterns = [
            "/video.php",
            "/videos/",
            "/watch/",
            "/share/v/",
            "/reel/",
            "/posts/",
            "/share/r/",
        ]

        if not any(pattern in url for pattern in allowed_patterns):
            return None

        return url

    def extract_reel_id_from_share(self, url):
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            final_url = response.url

            reel_match = re.search(r"/reel/(\d+)", final_url)
            if reel_match:
                return reel_match.group(1)

            share_match = re.search(r"/share/r/([a-zA-Z0-9_-]+)", url)
            if share_match:
                return share_match.group(1)

        except:
            pass
        return None

    def extract_video_id(self, url):
        patterns = [
            r"facebook\.com\/.*\/videos\/(\d+)",
            r"facebook\.com\/video\.php\?v=(\d+)",
            r"facebook\.com\/.*\/posts\/(\d+)",
            r"fb\.watch\/([a-zA-Z0-9_-]+)",
            r"facebook\.com\/watch\/\?v=(\d+)",
            r"facebook\.com\/share\/v\/([a-zA-Z0-9_-]+)",
            r"facebook\.com\/reel\/(\d+)",
            r"facebook\.com\/share\/r\/([a-zA-Z0-9_-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def decode_facebook_url(self, encoded_url):
        try:
            decoded = (
                encoded_url.replace("\\/", "/")
                .replace("\\u0026", "&")
                .replace("\\", "")
            )
            decoded = html.unescape(decoded)
            decoded = unquote(decoded)
            return decoded
        except:
            return encoded_url

    def extract_video_urls_with_quality(self, html_content):
        video_data = []

        quality_patterns = {
            "hd": [
                r'"hd_src(?:_no_ratelimit)?":"([^"]+)"',
                r'"playable_url_quality_hd":"([^"]+)"',
                r'"browser_native_hd_url":"([^"]+)"',
                r'hd_src:"([^"]+)"',
                r'"video_hd_url":"([^"]+)"',
                r'"hd_src_no_ratelimit":"([^"]+)"',
                r'"HD"[^}]*"src":"([^"]+)"',
                r'"quality":"hd"[^}]*"src":"([^"]+)"',
            ],
            "sd": [
                r'"sd_src(?:_no_ratelimit)?":"([^"]+)"',
                r'"playable_url_quality_sd":"([^"]+)"',
                r'"browser_native_sd_url":"([^"]+)"',
                r'sd_src:"([^"]+)"',
                r'"video_sd_url":"([^"]+)"',
                r'"sd_src_no_ratelimit":"([^"]+)"',
                r'"SD"[^}]*"src":"([^"]+)"',
                r'"quality":"sd"[^}]*"src":"([^"]+)"',
            ],
            "auto": [
                r'"playable_url":"([^"]+)"',
                r'"progressive_url":"([^"]+)"',
                r'"src":"([^"]+mp4[^"]*)"',
                r'"video_url":"([^"]+)"',
                r'"videoUrl":"([^"]+)"',
                r'"video_src":"([^"]+)"',
                r'"reels_video_url":"([^"]+)"',
                r'"video_dash_url":"([^"]+)"',
                r'"video_progressive_url":"([^"]+)"',
                r'"playback_url":"([^"]+)"',
                r'"browser_native_(?:hd|sd)_url":"([^"]+)"',
            ],
        }

        reel_specific_patterns = [
            r'"videoData":\[\"([^"]+)\"\]',
            r'"video_url":"([^"]+)".*?"reel"',
            r'"attachments":\[.*?"media".*?"src":"([^"]+)"',
            r'"story_bucket_owner":[^}]*"src":"([^"]+)"',
            r'videoSrc["\']?\s*:\s*["\']([^"\']+)["\']',
            r'"video":\s*{[^}]*"src":\s*"([^"]+)"',
            r'"media":\s*{[^}]*"video_src":\s*"([^"]+)"',
            r'"creation_story"[^}]*"attachments"[^}]*"media"[^}]*"browser_native_(?:hd|sd)_url":"([^"]+)"',
            r'"video_versions":\[.*?"url":"([^"]+)"',
            r'"dash_manifest":"([^"]+)"',
            r'"video_dash_prefetch_representation"[^}]*"base_url":"([^"]+)"',
        ]

        for quality, patterns in quality_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    decoded_url = self.decode_facebook_url(match)
                    if (
                        decoded_url
                        and (
                            "video" in decoded_url.lower()
                            or ".mp4" in decoded_url.lower()
                        )
                        and decoded_url.startswith("http")
                    ):
                        video_data.append(
                            {
                                "url": decoded_url,
                                "quality": quality,
                                "source_pattern": pattern,
                            }
                        )

        for pattern in reel_specific_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                decoded_url = self.decode_facebook_url(match)
                if (
                    decoded_url
                    and (
                        "video" in decoded_url.lower() or ".mp4" in decoded_url.lower()
                    )
                    and decoded_url.startswith("http")
                ):
                    video_data.append(
                        {
                            "url": decoded_url,
                            "quality": "auto",
                            "source_pattern": "reel_specific",
                        }
                    )

        return video_data

    def get_video_quality_info(self, url):
        try:
            response = self.session.head(url, timeout=10, allow_redirects=True)
            content_type = response.headers.get("content-type", "").lower()
            content_length = response.headers.get("content-length", "0")

            if response.status_code != 200:
                return None

            size_mb = (
                round(int(content_length) / (1024 * 1024), 2)
                if content_length.isdigit()
                else 0
            )

            quality_indicators = {
                "hd": size_mb > 30,
                "sd": 10 < size_mb <= 30,
                "low": size_mb <= 10,
            }

            detected_quality = "unknown"
            for quality, condition in quality_indicators.items():
                if condition:
                    detected_quality = quality
                    break

            return {
                "working": True,
                "size_bytes": int(content_length) if content_length.isdigit() else 0,
                "size_mb": size_mb,
                "content_type": content_type,
                "detected_quality": detected_quality,
            }
        except:
            return None

    def extract_video_urls(self, facebook_url):
        try:
            normalized_url = self.normalize_url(facebook_url)
            if not normalized_url:
                return []

            all_video_data = []
            is_reel = "/reel/" in normalized_url
            urls_to_check = [normalized_url]

            if is_reel:
                mobile_reel = normalized_url.replace(
                    "www.facebook.com", "m.facebook.com"
                )
                urls_to_check.append(mobile_reel)

                reel_id = self.extract_video_id(normalized_url)
                if reel_id:
                    story_url = f"https://www.facebook.com/stories/{reel_id}"
                    mobile_story_url = f"https://m.facebook.com/stories/{reel_id}"
                    urls_to_check.extend([story_url, mobile_story_url])
            else:
                mobile_url = normalized_url.replace(
                    "www.facebook.com", "m.facebook.com"
                )
                urls_to_check.append(mobile_url)

            for url in urls_to_check:
                try:
                    response = self.session.get(url, timeout=15, allow_redirects=True)

                    if response.status_code == 200:
                        video_data = self.extract_video_urls_with_quality(response.text)
                        all_video_data.extend(video_data)

                    time.sleep(random.uniform(1, 2))
                except Exception as e:
                    continue

            unique_videos = {}
            for video in all_video_data:
                clean_url = (
                    video["url"].split("?")[0] if "?" in video["url"] else video["url"]
                )

                if clean_url not in unique_videos:
                    unique_videos[clean_url] = video
                else:
                    current_quality = unique_videos[clean_url]["quality"]
                    new_quality = video["quality"]

                    quality_priority = {"hd": 3, "sd": 2, "auto": 1}
                    if quality_priority.get(new_quality, 0) > quality_priority.get(
                        current_quality, 0
                    ):
                        unique_videos[clean_url] = video

            return list(unique_videos.values())

        except Exception as e:
            return []

    def analyze_video_qualities(self, video_data_list):
        quality_options = []

        for video_data in video_data_list:
            quality_info = self.get_video_quality_info(video_data["url"])

            if quality_info and quality_info["working"]:
                quality_label = video_data["quality"].upper()
                if quality_label == "AUTO":
                    quality_label = quality_info["detected_quality"].upper()

                quality_options.append(
                    {
                        "url": video_data["url"],
                        "quality": quality_label,
                        "size_mb": quality_info["size_mb"],
                        "size_bytes": quality_info["size_bytes"],
                        "resolution_estimate": self.estimate_resolution(
                            quality_info["size_mb"]
                        ),
                    }
                )

        quality_options.sort(key=lambda x: x["size_bytes"], reverse=True)
        return quality_options

    def estimate_resolution(self, size_mb):
        if size_mb > 50:
            return "1080p (estimated)"
        elif size_mb > 25:
            return "720p (estimated)"
        elif size_mb > 10:
            return "480p (estimated)"
        else:
            return "360p or lower (estimated)"

    def extract_enhanced_video_info(self, html_content):
        info = {}

        title_patterns = [
            r'"title":"([^"]+)"',
            r'"text":"([^"]+)".*?"creation_story"',
            r'"message":\s*{\s*"text":"([^"]+)"',
            r"<title[^>]*>([^<]*)</title>",
            r'"name":"([^"]+)".*?"video"',
            r'"attachments"[^}]*"title":"([^"]+)"',
            r'"story_bucket_owner"[^}]*"name":"([^"]+)"',
        ]

        for pattern in title_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match and match.group(1).strip():
                title = html.unescape(match.group(1)).strip()
                if title and len(title) > 3 and not title.startswith("Facebook"):
                    info["title"] = title
                    break

        author_patterns = [
            r'"author":\s*{\s*"name":"([^"]+)"',
            r'"owner":\s*{\s*"name":"([^"]+)"',
            r'"name":"([^"]+)".*?"__typename":"User"',
            r'"story_bucket_owner"[^}]*"name":"([^"]+)"',
            r'"creation_story"[^}]*"short_form_video_context"[^}]*"playback_video"[^}]*"owner"[^}]*"name":"([^"]+)"',
            r'"page_info"[^}]*"name":"([^"]+)"',
        ]

        for pattern in author_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match and match.group(1).strip():
                author = html.unescape(match.group(1)).strip()
                if author and len(author) > 1:
                    info["author"] = author
                    break

        duration_patterns = [
            r'"duration":(\d+)',
            r'"length_in_milliseconds":(\d+)',
            r'"playable_duration_in_ms":(\d+)',
            r'"duration_ms":(\d+)',
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, html_content)
            if match:
                duration_ms = int(match.group(1))
                if pattern.endswith(r'_ms"):(\d+)') or "milliseconds" in pattern:
                    duration_sec = duration_ms // 1000
                else:
                    duration_sec = duration_ms

                if duration_sec > 0:
                    minutes = duration_sec // 60
                    seconds = duration_sec % 60
                    info["duration"] = f"{minutes}:{seconds:02d}"
                    break

        thumbnail_patterns = [
            r'"preferred_thumbnail"[^}]*"image"[^}]*"uri":"([^"]+)"',
            r'"thumbnail"[^}]*"image"[^}]*"uri":"([^"]+)"',
            r'"thumbnailImage"[^}]*"uri":"([^"]+)"',
            r'"image"[^}]*"uri":"([^"]+)"',
            r'"cover_photo"[^}]*"source":"([^"]+)"',
        ]

        for pattern in thumbnail_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                thumbnail_url = self.decode_facebook_url(match.group(1))
                if thumbnail_url and thumbnail_url.startswith("http"):
                    info["thumbnail"] = thumbnail_url
                    break

        description_patterns = [
            r'"description":"([^"]+)"',
            r'"message":\s*{\s*"text":"([^"]+)"',
            r'"creation_story"[^}]*"comet_sections"[^}]*"story"[^}]*"message"[^}]*"text":"([^"]+)"',
        ]

        for pattern in description_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match and match.group(1).strip():
                description = html.unescape(match.group(1)).strip()
                if description and len(description) > 3:
                    info["description"] = description[:200] + (
                        "..." if len(description) > 200 else ""
                    )
                    break

        return info

    def get_video_info(self, facebook_url):
        try:
            normalized_url = self.normalize_url(facebook_url)
            if not normalized_url:
                return None

            response = self.session.get(normalized_url, timeout=15)
            if response.status_code != 200:
                mobile_url = normalized_url.replace(
                    "www.facebook.com", "m.facebook.com"
                )
                response = self.session.get(mobile_url, timeout=15)

            if response.status_code != 200:
                return None

            return self.extract_enhanced_video_info(response.text)

        except Exception as e:
            return None

    def get_video_data(self, url):
        try:
            normalized_url = self.normalize_url(url)
            if not normalized_url:
                return {"error": "Invalid Facebook URL"}

            video_id = self.extract_video_id(normalized_url)
            if not video_id:
                return {"error": "Could not extract video ID"}

            video_data_list = self.extract_video_urls(normalized_url)
            if not video_data_list:
                return {"error": "No video URLs found"}

            quality_options = self.analyze_video_qualities(video_data_list)
            if not quality_options:
                return {"error": "No working video URLs found"}

            best_quality = quality_options[0]
            info = self.get_video_info(normalized_url) or {}

            hd_url = None
            sd_url = None
            auto_url = best_quality["url"]

            for option in quality_options:
                if option["quality"] == "HD" and not hd_url:
                    hd_url = option["url"]
                elif option["quality"] == "SD" and not sd_url:
                    sd_url = option["url"]

            return {
                "video_url_hd": hd_url,
                "video_url_sd": sd_url,
                "video_url_auto": auto_url,
                "title": info.get("title", "Facebook Video"),
                "author": info.get("author", "Unknown"),
                "duration": info.get("duration", "0:00"),
                "thumbnail": info.get("thumbnail", ""),
                "video_id": video_id,
                "quality_options": quality_options,
                "width": 0,
                "height": 0,
            }

        except Exception as e:
            return {"error": f"Failed to get video data: {str(e)}"}


def send_typing_indicator(recipient_id, typing_on=True):
    try:
        import json

        with open("config.json", "r") as f:
            config = json.load(f)

        PAGE_ACCESS_TOKEN = config["page_access_token"]
        GRAPH_API_VERSION = config["graph_api_version"]
        PAGE_ID = config.get("page_id", "612984285242194")

        if not recipient_id or not PAGE_ACCESS_TOKEN:
            return None

        if str(recipient_id) == str(PAGE_ID):
            return None

        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "sender_action": "typing_on" if typing_on else "typing_off",
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(url, params=params, headers=headers, json=data)
        return response.json()
    except Exception as e:
        return None


def send_button_template(recipient_id, text, buttons):
    try:
        import json

        with open("config.json", "r") as f:
            config = json.load(f)

        PAGE_ACCESS_TOKEN = config["page_access_token"]
        GRAPH_API_VERSION = config["graph_api_version"]

        if not PAGE_ACCESS_TOKEN:
            return None

        if not text or not buttons or not isinstance(buttons, list):
            return None

        if len(buttons) > 3:
            buttons = buttons[:3]

        if len(text) > 640:
            text = text[:637] + "..."

        template_payload = {"template_type": "button", "text": text, "buttons": buttons}

        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {"type": "template", "payload": template_payload}
            },
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=30
        )
        return response.json()
    except Exception as e:
        return None


def send_generic_template(recipient_id, elements):
    try:
        import json

        with open("config.json", "r") as f:
            config = json.load(f)

        PAGE_ACCESS_TOKEN = config["page_access_token"]
        GRAPH_API_VERSION = config["graph_api_version"]

        if not PAGE_ACCESS_TOKEN:
            return None

        if not elements or not isinstance(elements, list):
            return None

        if len(elements) > 10:
            elements = elements[:10]

        template_payload = {"template_type": "generic", "elements": elements}

        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {"type": "template", "payload": template_payload}
            },
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=30
        )
        return response.json()
    except Exception as e:
        return None


def create_url_button(title, url, webview_height_ratio="tall"):
    if len(title) > 20:
        title = title[:20]

    return {
        "type": "web_url",
        "title": title,
        "url": url,
        "webview_height_ratio": webview_height_ratio,
    }


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
