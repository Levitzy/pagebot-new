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

        # Handle fb.watch redirects
        if "fb.watch" in url:
            try:
                response = self.session.head(url, allow_redirects=True, timeout=10)
                url = response.url
            except:
                pass

        if "m.facebook.com" in url:
            url = url.replace("m.facebook.com", "www.facebook.com")

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
            # Multiple decoding passes
            decoded = encoded_url

            # Basic replacements
            decoded = (
                decoded.replace("\\/", "/")
                .replace("\\u0026", "&")
                .replace("\\u003d", "=")
                .replace("\\u003D", "=")
                .replace('\\"', '"')
                .replace("\\", "")
            )

            # HTML entities
            decoded = html.unescape(decoded)

            # URL decoding
            decoded = unquote(decoded)

            # Final cleanup
            decoded = decoded.replace("&amp;", "&")

            return decoded
        except:
            return encoded_url

    def extract_video_urls_comprehensive(self, html_content):
        """Comprehensive video extraction with all known patterns"""
        video_urls = []

        # All possible Facebook video patterns
        patterns = [
            # Modern Facebook patterns
            r'"browser_native_hd_url":"([^"]+)"',
            r'"browser_native_sd_url":"([^"]+)"',
            r'"playable_url":"([^"]+)"',
            r'"playable_url_quality_hd":"([^"]+)"',
            r'"playable_url_quality_sd":"([^"]+)"',
            # Legacy patterns
            r'"hd_src":"([^"]+)"',
            r'"sd_src":"([^"]+)"',
            r'"hd_src_no_ratelimit":"([^"]+)"',
            r'"sd_src_no_ratelimit":"([^"]+)"',
            # Video object patterns
            r'"__typename":"Video"[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"__typename":"Video"[^}]*"browser_native_sd_url":"([^"]+)"',
            r'"__typename":"Video"[^}]*"playable_url":"([^"]+)"',
            # Relay patterns
            r'"VideoPlayerRelay_video"[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"VideoPlayerRelay_video"[^}]*"browser_native_sd_url":"([^"]+)"',
            r'"CometVideoPlayer_video"[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"CometVideoPlayer_video"[^}]*"browser_native_sd_url":"([^"]+)"',
            # Reels patterns
            r'"short_form_video_context"[^}]*"video_url":"([^"]+)"',
            r'"playback_video"[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"playback_video"[^}]*"browser_native_sd_url":"([^"]+)"',
            r'"playback_video"[^}]*"playable_url":"([^"]+)"',
            # Creation story patterns
            r'"creation_story"[^}]*"attachments"[^}]*"media"[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"creation_story"[^}]*"attachments"[^}]*"media"[^}]*"browser_native_sd_url":"([^"]+)"',
            # Generic patterns
            r'"video"[^}]*"src":"([^"]+)"',
            r'"video_url":"([^"]+)"',
            r'"videoUrl":"([^"]+)"',
            r'"progressive_url":"([^"]+)"',
            r'"attachments"[^}]*"media"[^}]*"src":"([^"]+)"',
            # Direct MP4 patterns
            r'(https://[^"\s]*\.mp4[^"\s]*)',
            r'(https://[^"\s]*fbcdn[^"\s]*\.mp4[^"\s]*)',
            r'(https://video[^"\s]*\.mp4[^"\s]*)',
            r'(https://[^"\s]*\.fbcdn\.net[^"\s]*\.mp4[^"\s]*)',
            # Backup patterns
            r'src="([^"]*video[^"]*\.mp4[^"]*)"',
            r'href="([^"]*video[^"]*\.mp4[^"]*)"',
        ]

        for pattern in patterns:
            try:
                matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0] if match[0] else ""

                    if not match:
                        continue

                    decoded_url = self.decode_facebook_url(match)

                    # Validate URL
                    if (
                        decoded_url
                        and decoded_url.startswith("http")
                        and len(decoded_url) > 30
                        and (
                            ".mp4" in decoded_url.lower()
                            or "video" in decoded_url.lower()
                            or "fbcdn" in decoded_url.lower()
                        )
                        and not any(
                            skip in decoded_url.lower()
                            for skip in ["thumbnail", "preview", "cover"]
                        )
                    ):
                        # Determine quality
                        quality = "auto"
                        if (
                            "hd" in pattern.lower()
                            or "1080" in decoded_url
                            or "720" in decoded_url
                        ):
                            quality = "hd"
                        elif (
                            "sd" in pattern.lower()
                            or "480" in decoded_url
                            or "360" in decoded_url
                        ):
                            quality = "sd"

                        video_urls.append(
                            {
                                "url": decoded_url,
                                "quality": quality,
                            }
                        )
            except Exception:
                continue

        return video_urls

    def extract_video_urls(self, facebook_url):
        try:
            normalized_url = self.normalize_url(facebook_url)
            if not normalized_url:
                return []

            video_id = self.extract_video_id(normalized_url)

            # Try just a few strategic URLs to avoid spam
            urls_to_check = [normalized_url]

            # Add mobile version
            mobile_url = normalized_url.replace("www.facebook.com", "m.facebook.com")
            if mobile_url != normalized_url:
                urls_to_check.append(mobile_url)

            # If we have video ID, add one alternative format
            if video_id:
                if "/reel/" in normalized_url:
                    urls_to_check.append(
                        f"https://www.facebook.com/watch/?v={video_id}"
                    )
                else:
                    urls_to_check.append(f"https://www.facebook.com/reel/{video_id}")

            all_video_data = []

            for i, url in enumerate(urls_to_check):
                try:
                    if i > 0:
                        time.sleep(2)  # Rate limiting

                    response = self.session.get(url, timeout=20, allow_redirects=True)

                    if response.status_code == 200:
                        video_data = self.extract_video_urls_comprehensive(
                            response.text
                        )
                        all_video_data.extend(video_data)

                        # If we found good videos, stop searching
                        if len(video_data) >= 2:
                            break

                except Exception:
                    continue

            # Remove duplicates
            unique_videos = {}
            for video in all_video_data:
                try:
                    parsed = urlparse(video["url"])
                    dedup_key = f"{parsed.netloc}{parsed.path}"
                except:
                    dedup_key = video["url"].split("?")[0]

                if dedup_key not in unique_videos:
                    unique_videos[dedup_key] = video
                else:
                    # Keep higher quality
                    current_quality = unique_videos[dedup_key]["quality"]
                    new_quality = video["quality"]
                    quality_priority = {"hd": 3, "sd": 2, "auto": 1}
                    if quality_priority.get(new_quality, 0) > quality_priority.get(
                        current_quality, 0
                    ):
                        unique_videos[dedup_key] = video

            return list(unique_videos.values())

        except Exception:
            return []

    def test_video_url(self, url):
        """Test if video URL is accessible"""
        try:
            response = self.session.head(url, timeout=8, allow_redirects=True)
            if response.status_code in [200, 206]:
                content_length = response.headers.get("content-length", "0")
                size_mb = (
                    round(int(content_length) / (1024 * 1024), 2)
                    if content_length.isdigit()
                    else 0
                )
                return True, size_mb
        except:
            pass
        return False, 0

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
                return {
                    "error": "No video URLs found. The video might be private, deleted, or region-restricted."
                }

            # Test URLs and keep working ones
            working_videos = []
            for video_data in video_data_list:
                is_working, size_mb = self.test_video_url(video_data["url"])
                if is_working:
                    video_data["size_mb"] = size_mb
                    working_videos.append(video_data)

            if not working_videos:
                return {
                    "error": "No working video URLs found. All video links appear to be broken."
                }

            # Sort by quality and size
            working_videos.sort(
                key=lambda x: (
                    {"hd": 3, "sd": 2, "auto": 1}.get(x["quality"], 0),
                    x.get("size_mb", 0),
                ),
                reverse=True,
            )

            best_video = working_videos[0]

            # Get video info
            info = self.get_video_info(normalized_url) or {}

            return {
                "video_url_hd": (
                    best_video["url"] if best_video["quality"] == "hd" else None
                ),
                "video_url_sd": (
                    best_video["url"] if best_video["quality"] == "sd" else None
                ),
                "video_url_auto": best_video["url"],
                "title": info.get("title", "Facebook Video"),
                "author": info.get("author", "Unknown"),
                "duration": info.get("duration", "0:00"),
                "thumbnail": info.get("thumbnail", ""),
                "video_id": video_id,
                "quality_options": working_videos,
                "width": 0,
                "height": 0,
            }

        except Exception as e:
            return {"error": f"Failed to get video data: {str(e)}"}

    def get_video_info(self, facebook_url):
        """Extract video metadata"""
        try:
            response = self.session.get(facebook_url, timeout=15)
            if response.status_code != 200:
                return {}

            html_content = response.text
            info = {}

            # Extract title
            title_patterns = [
                r'"title":"([^"]+)"',
                r"<title[^>]*>([^<]*)</title>",
                r'property="og:title"[^>]*content="([^"]*)"',
            ]

            for pattern in title_patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match and match.group(1).strip():
                    title = html.unescape(match.group(1)).strip()
                    if title and len(title) > 3 and not title.startswith("Facebook"):
                        info["title"] = title[:150]
                        break

            # Extract author
            author_patterns = [
                r'"author":\s*{\s*"name":"([^"]+)"',
                r'"name":"([^"]+)".*?"__typename":"User"',
            ]

            for pattern in author_patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match and match.group(1).strip():
                    author = html.unescape(match.group(1)).strip()
                    if author and len(author) > 1:
                        info["author"] = author[:50]
                        break

            return info

        except Exception:
            return {}


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
        # Import the new attachment function
        import sys
        import os

        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        try:
            from functions.sendAttachment import send_video_attachment
        except ImportError:
            send_message_func(
                sender_id,
                "❌ Video sending system not available. Please check server configuration.",
            )
            return

        downloader = FacebookVideoDownloader()
        video_data = downloader.get_video_data(url)

        if "error" in video_data:
            send_message_func(sender_id, f"❌ Error: {video_data['error']}")
            return

        title = video_data.get("title", "Facebook Video")
        author = video_data.get("author", "Unknown")
        duration = video_data.get("duration", "0:00")

        video_url_hd = video_data.get("video_url_hd")
        video_url_sd = video_data.get("video_url_sd")
        video_url_auto = video_data.get("video_url_auto")

        info_message = f"✅ Facebook Video Found!\n\n"
        info_message += f"📝 Title: {title}\n"
        info_message += f"👤 Author: {author}\n"
        info_message += f"⏱️ Duration: {duration}\n\n"
        info_message += "📹 Processing video..."

        send_message_func(sender_id, info_message)

        # SMART SINGLE ATTEMPT - NO SPAM
        # Try SD first (usually smaller), then HD, then auto
        video_url_to_try = None
        quality_name = ""

        if video_url_sd:
            video_url_to_try = video_url_sd
            quality_name = "SD"
        elif video_url_auto:
            video_url_to_try = video_url_auto
            quality_name = "Standard"
        elif video_url_hd:
            video_url_to_try = video_url_hd
            quality_name = "HD"

        if video_url_to_try:
            send_typing_indicator(sender_id, True)
            send_message_func(
                sender_id, f"📤 Uploading video ({quality_name} quality)..."
            )

            result = send_video_attachment(sender_id, video_url_to_try)

            if result and result.get("message_id"):
                send_message_func(sender_id, "✅ Video sent successfully!")
            elif result and "error" in result:
                error_msg = result["error"]

                # Only try HD if SD failed and we haven't tried HD yet
                if (
                    quality_name == "SD"
                    and video_url_hd
                    and video_url_hd != video_url_to_try
                ):
                    send_message_func(
                        sender_id, "⚠️ SD quality failed, trying HD version..."
                    )

                    result2 = send_video_attachment(sender_id, video_url_hd)

                    if result2 and result2.get("message_id"):
                        send_message_func(
                            sender_id, "✅ Video sent successfully (HD quality)!"
                        )
                    else:
                        # Both failed
                        if "too large" in error_msg.lower():
                            send_message_func(
                                sender_id,
                                "❌ Video is too large to send (>20MB). Try a shorter Facebook video.",
                            )
                        elif "timeout" in error_msg.lower():
                            send_message_func(
                                sender_id,
                                "⏰ Upload timeout. The video might be too large or connection is slow.",
                            )
                        elif "download" in error_msg.lower():
                            send_message_func(
                                sender_id,
                                "❌ Failed to download video. The video might be private or region-restricted.",
                            )
                        else:
                            send_message_func(
                                sender_id, f"❌ Failed to send video: {error_msg}"
                            )
                else:
                    # Single attempt failed
                    if "too large" in error_msg.lower():
                        send_message_func(
                            sender_id,
                            "❌ Video is too large to send (>20MB). Try a shorter Facebook video.",
                        )
                    elif "timeout" in error_msg.lower():
                        send_message_func(
                            sender_id,
                            "⏰ Upload timeout. The video might be too large or connection is slow.",
                        )
                    elif "download" in error_msg.lower():
                        send_message_func(
                            sender_id,
                            "❌ Failed to download video. The video might be private or region-restricted.",
                        )
                    elif "400" in str(error_msg):
                        send_message_func(
                            sender_id,
                            "❌ Video format not supported by Facebook. Try a different Facebook video.",
                        )
                    else:
                        send_message_func(
                            sender_id, f"❌ Failed to send video: {error_msg}"
                        )
            else:
                send_message_func(
                    sender_id,
                    "❌ Failed to send video. The video might be private or unavailable.",
                )
        else:
            send_message_func(sender_id, "❌ No video URL found for sending.")

    except Exception as e:
        send_message_func(sender_id, f"❌ An unexpected error occurred: {str(e)}")
    finally:
        send_typing_indicator(sender_id, False)
