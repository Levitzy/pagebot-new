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
                .replace("\\u003d", "=")
                .replace("\\u003D", "=")
            )
            decoded = html.unescape(decoded)
            decoded = unquote(decoded)
            return decoded
        except:
            return encoded_url

    def extract_video_urls_with_quality(self, html_content):
        video_data = []

        # Enhanced patterns for modern Facebook
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
                r'"representation":\s*{\s*"__typename":"VideoRepresentation"[^}]*"base_url":"([^"]+)"[^}]*"quality_label":"720p"',
                r'"representation":\s*{\s*"__typename":"VideoRepresentation"[^}]*"base_url":"([^"]+)"[^}]*"quality_label":"1080p"',
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
                r'"representation":\s*{\s*"__typename":"VideoRepresentation"[^}]*"base_url":"([^"]+)"[^}]*"quality_label":"480p"',
                r'"representation":\s*{\s*"__typename":"VideoRepresentation"[^}]*"base_url":"([^"]+)"[^}]*"quality_label":"360p"',
            ],
            "auto": [
                r'"playable_url":"([^"]+)"',
                r'"progressive_url":"([^"]+)"',
                r'"src":"([^"]+\.mp4[^"]*)"',
                r'"video_url":"([^"]+)"',
                r'"videoUrl":"([^"]+)"',
                r'"video_src":"([^"]+)"',
                r'"reels_video_url":"([^"]+)"',
                r'"video_dash_url":"([^"]+)"',
                r'"video_progressive_url":"([^"]+)"',
                r'"playback_url":"([^"]+)"',
                r'"browser_native_(?:hd|sd)_url":"([^"]+)"',
                r'"representation":\s*{\s*"__typename":"VideoRepresentation"[^}]*"base_url":"([^"]+)"',
                r'"video_data":\s*{\s*"video_url":"([^"]+)"',
                r'"video_attachment":\s*{\s*"video":\s*{\s*"src":"([^"]+)"',
            ],
        }

        # Reel and modern Facebook patterns
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
            r'"short_form_video_context"[^}]*"video_url":"([^"]+)"',
            r'"playback_video"[^}]*"__typename":"Video"[^}]*"browser_native_(?:hd|sd)_url":"([^"]+)"',
            r'"VideoPlayerRelay_video"[^}]*"browser_native_(?:hd|sd)_url":"([^"]+)"',
            r'"CometVideoPlayer_video"[^}]*"browser_native_(?:hd|sd)_url":"([^"]+)"',
        ]

        # Modern Facebook video extraction patterns
        modern_patterns = [
            r'"__typename":"Video"[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"__typename":"Video"[^}]*"browser_native_sd_url":"([^"]+)"',
            r'"VideoPlayerRelay_video":\s*{[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"VideoPlayerRelay_video":\s*{[^}]*"browser_native_sd_url":"([^"]+)"',
            r'"CometVideoPlayer_video":\s*{[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"CometVideoPlayer_video":\s*{[^}]*"browser_native_sd_url":"([^"]+)"',
            r'"playback_video":\s*{[^}]*"browser_native_hd_url":"([^"]+)"',
            r'"playback_video":\s*{[^}]*"browser_native_sd_url":"([^"]+)"',
        ]

        # Process quality patterns
        for quality, patterns in quality_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    decoded_url = self.decode_facebook_url(match)
                    if (
                        decoded_url
                        and (
                            "video" in decoded_url.lower()
                            or ".mp4" in decoded_url.lower()
                            or "fbcdn" in decoded_url.lower()
                        )
                        and decoded_url.startswith("http")
                        and len(decoded_url) > 20
                    ):
                        video_data.append(
                            {
                                "url": decoded_url,
                                "quality": quality,
                                "source_pattern": pattern,
                            }
                        )

        # Process reel patterns
        for pattern in reel_specific_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                decoded_url = self.decode_facebook_url(match)
                if (
                    decoded_url
                    and (
                        "video" in decoded_url.lower()
                        or ".mp4" in decoded_url.lower()
                        or "fbcdn" in decoded_url.lower()
                    )
                    and decoded_url.startswith("http")
                    and len(decoded_url) > 20
                ):
                    video_data.append(
                        {
                            "url": decoded_url,
                            "quality": "auto",
                            "source_pattern": "reel_specific",
                        }
                    )

        # Process modern patterns
        for pattern in modern_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                decoded_url = self.decode_facebook_url(match)
                if (
                    decoded_url
                    and (
                        "video" in decoded_url.lower()
                        or ".mp4" in decoded_url.lower()
                        or "fbcdn" in decoded_url.lower()
                    )
                    and decoded_url.startswith("http")
                    and len(decoded_url) > 20
                ):
                    quality = (
                        "hd" if "hd" in pattern else "sd" if "sd" in pattern else "auto"
                    )
                    video_data.append(
                        {
                            "url": decoded_url,
                            "quality": quality,
                            "source_pattern": "modern_facebook",
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

            # Add mobile versions and different formats
            if is_reel:
                mobile_reel = normalized_url.replace(
                    "www.facebook.com", "m.facebook.com"
                )
                urls_to_check.append(mobile_reel)

                reel_id = self.extract_video_id(normalized_url)
                if reel_id:
                    story_url = f"https://www.facebook.com/stories/{reel_id}"
                    mobile_story_url = f"https://m.facebook.com/stories/{reel_id}"
                    watch_url = f"https://www.facebook.com/watch/?v={reel_id}"
                    mobile_watch_url = f"https://m.facebook.com/watch/?v={reel_id}"
                    urls_to_check.extend(
                        [story_url, mobile_story_url, watch_url, mobile_watch_url]
                    )
            else:
                mobile_url = normalized_url.replace(
                    "www.facebook.com", "m.facebook.com"
                )
                urls_to_check.append(mobile_url)

                video_id = self.extract_video_id(normalized_url)
                if video_id:
                    # Try different URL formats
                    watch_url = f"https://www.facebook.com/watch/?v={video_id}"
                    mobile_watch_url = f"https://m.facebook.com/watch/?v={video_id}"
                    video_php_url = f"https://www.facebook.com/video.php?v={video_id}"
                    mobile_video_php_url = (
                        f"https://m.facebook.com/video.php?v={video_id}"
                    )
                    urls_to_check.extend(
                        [
                            watch_url,
                            mobile_watch_url,
                            video_php_url,
                            mobile_video_php_url,
                        ]
                    )

            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in urls_to_check:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)

            for url in unique_urls:
                try:
                    # Add random delay to avoid rate limiting
                    time.sleep(random.uniform(0.5, 1.5))

                    response = self.session.get(url, timeout=20, allow_redirects=True)

                    if response.status_code == 200:
                        video_data = self.extract_video_urls_with_quality(response.text)
                        all_video_data.extend(video_data)

                        # If we found videos, we can break early
                        if video_data:
                            break

                except Exception as e:
                    continue

            # Remove duplicates and prioritize by quality
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
            r'"short_form_video_context"[^}]*"title":"([^"]+)"',
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
            r'"video_owner"[^}]*"name":"([^"]+)"',
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
            r'"video_duration":(\d+)',
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
            r'"preview_image"[^}]*"uri":"([^"]+)"',
        ]

        for pattern in thumbnail_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                thumbnail_url = self.decode_facebook_url(match.group(1))
                if thumbnail_url and thumbnail_url.startswith("http"):
                    info["thumbnail"] = thumbnail_url
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
                return {
                    "error": "No video URLs found. The video might be private, deleted, or in an unsupported format."
                }

            quality_options = self.analyze_video_qualities(video_data_list)
            if not quality_options:
                return {
                    "error": "No working video URLs found. All video links appear to be broken or inaccessible."
                }

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
            # Enhanced fallback method
            def send_video_attachment(recipient_id, video_url):
                try:
                    import json

                    with open("config.json", "r") as f:
                        config = json.load(f)

                    PAGE_ACCESS_TOKEN = config["page_access_token"]
                    GRAPH_API_VERSION = config["graph_api_version"]

                    # Try upload method first
                    try:
                        upload_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/message_attachments"
                        upload_params = {"access_token": PAGE_ACCESS_TOKEN}
                        upload_data = {
                            "message": json.dumps(
                                {
                                    "attachment": {
                                        "type": "video",
                                        "payload": {"is_reusable": False},
                                    }
                                }
                            )
                        }

                        # Download video first
                        video_response = requests.get(video_url, timeout=30)
                        if video_response.status_code == 200:
                            files = {
                                "filedata": (
                                    "video.mp4",
                                    video_response.content,
                                    "video/mp4",
                                )
                            }
                            upload_response = requests.post(
                                upload_url,
                                params=upload_params,
                                data=upload_data,
                                files=files,
                                timeout=120,
                            )

                            if upload_response.status_code == 200:
                                upload_result = upload_response.json()
                                attachment_id = upload_result.get("attachment_id")

                                if attachment_id:
                                    # Send using attachment ID
                                    params = {"access_token": PAGE_ACCESS_TOKEN}
                                    headers = {"Content-Type": "application/json"}
                                    data = {
                                        "recipient": {"id": recipient_id},
                                        "message": {
                                            "attachment": {
                                                "type": "video",
                                                "payload": {
                                                    "attachment_id": attachment_id
                                                },
                                            }
                                        },
                                    }

                                    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"
                                    response = requests.post(
                                        url,
                                        params=params,
                                        headers=headers,
                                        json=data,
                                        timeout=60,
                                    )
                                    return response.json()
                    except Exception as upload_error:
                        pass

                    # Fallback to URL method
                    params = {"access_token": PAGE_ACCESS_TOKEN}
                    headers = {"Content-Type": "application/json"}
                    data = {
                        "recipient": {"id": recipient_id},
                        "message": {
                            "attachment": {
                                "type": "video",
                                "payload": {"url": video_url, "is_reusable": False},
                            }
                        },
                    }

                    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"
                    response = requests.post(
                        url, params=params, headers=headers, json=data, timeout=60
                    )
                    return response.json()

                except Exception as e:
                    return {"error": str(e)}

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
        info_message += "📹 Processing video..."

        send_message_func(sender_id, info_message)

        # Try different quality options
        video_urls_to_try = []
        if video_url_hd:
            video_urls_to_try.append(("HD", video_url_hd))
        if video_url_sd and video_url_sd != video_url_hd:
            video_urls_to_try.append(("SD", video_url_sd))
        if video_url_auto and video_url_auto not in [video_url_hd, video_url_sd]:
            video_urls_to_try.append(("Auto", video_url_auto))

        # Add all quality options as fallbacks
        for option in quality_options:
            if option["url"] not in [v[1] for v in video_urls_to_try]:
                video_urls_to_try.append((option["quality"], option["url"]))

        if video_urls_to_try:
            send_typing_indicator(sender_id, True)

            for quality_name, video_url in video_urls_to_try:
                send_message_func(
                    sender_id, f"📤 Uploading video ({quality_name} quality)..."
                )

                result = send_video_attachment(sender_id, video_url)

                if result and result.get("message_id"):
                    send_message_func(
                        sender_id,
                        f"✅ Video sent successfully ({quality_name} quality)!",
                    )
                    break
                elif result and "error" in result:
                    error_msg = result["error"]
                    if "too large" in error_msg.lower():
                        send_message_func(
                            sender_id,
                            f"⚠️ {quality_name} quality too large, trying next quality...",
                        )
                        continue
                    elif "timeout" in error_msg.lower():
                        send_message_func(
                            sender_id,
                            f"⏰ Upload timeout for {quality_name} quality, trying next...",
                        )
                        continue
                    elif len(video_urls_to_try) == 1:  # Only one URL to try
                        if "400" in str(error_msg):
                            send_message_func(
                                sender_id,
                                "❌ Video format not supported by Facebook. Try a different Facebook video.",
                            )
                        else:
                            send_message_func(
                                sender_id, f"❌ Failed to send video: {error_msg}"
                            )
                        break
                else:
                    if len(video_urls_to_try) == 1:  # Only one URL to try
                        send_message_func(
                            sender_id,
                            "❌ Failed to send video. The video might be private or unavailable.",
                        )
                        break
                    else:
                        send_message_func(
                            sender_id,
                            f"⚠️ {quality_name} quality failed, trying next...",
                        )
                        continue
            else:
                # All URLs failed
                send_message_func(
                    sender_id,
                    "❌ Failed to send video in any quality. The video might be private, too large, or in an unsupported format.",
                )
        else:
            send_message_func(sender_id, "❌ No video URL found for sending.")

    except Exception as e:
        send_message_func(sender_id, f"❌ An unexpected error occurred: {str(e)}")
    finally:
        send_typing_indicator(sender_id, False)
