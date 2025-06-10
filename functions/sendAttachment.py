import requests
import json
import logging
import os
import tempfile
import time
from urllib.parse import urlparse, parse_qs
import mimetypes

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]
PAGE_ID = config.get("page_id", "612984285242194")

MAX_VIDEO_SIZE = 25 * 1024 * 1024  # 25MB limit for Facebook videos
CHUNK_SIZE = 8192
TIMEOUT_DOWNLOAD = 60
TIMEOUT_UPLOAD = 180


def clean_video_url_for_download(url):
    """Clean video URL for direct download"""
    if not url:
        return url

    # Remove Facebook-specific problematic parameters
    problematic_params = [
        "oh=",
        "oe=",
        "__cft__=",
        "ccb=",
        "_nc_ht=",
        "_nc_cat=",
        "_nc_ohc=",
        "efg=",
        "_nc_sid=",
        "_nc_eui2=",
        "stp=",
        "tp=",
        "__gda__=",
        "expire=",
        "x-expires=",
        "x-signature=",
        "signature=",
        "token=",
        "_nc_ad=",
        "z-m",
    ]

    try:
        parsed = urlparse(url)
        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)

            # Keep only safe parameters
            safe_params = {}
            for key, values in query_params.items():
                keep_param = True
                for bad_param in problematic_params:
                    if bad_param in key.lower():
                        keep_param = False
                        break

                if keep_param and values:
                    safe_params[key] = values[0]

            if safe_params:
                query_string = "&".join([f"{k}={v}" for k, v in safe_params.items()])
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_string}"
            else:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except:
        pass

    return url


def download_video_content(video_url, max_retries=3):
    """Download video content with better headers and retry logic"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "video/webm,video/ogg,video/*;q=0.9,application/octet-stream;q=0.7,audio/*;q=0.6,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "identity",
        "Range": "bytes=0-",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "video",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }

    for attempt in range(max_retries):
        try:
            logger.info(
                f"Downloading video attempt {attempt + 1}: {video_url[:100]}..."
            )

            # Clean URL before download
            clean_url = clean_video_url_for_download(video_url)

            # First, check if we can access the video
            head_response = requests.head(
                clean_url, headers=headers, timeout=15, allow_redirects=True
            )

            if head_response.status_code not in [200, 206, 302, 301]:
                logger.warning(
                    f"Head request failed with status {head_response.status_code}"
                )
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff
                    continue
                return (
                    None,
                    f"Video not accessible (status: {head_response.status_code})",
                )

            # Check content length
            content_length = head_response.headers.get("content-length")
            if content_length and int(content_length) > MAX_VIDEO_SIZE:
                return (
                    None,
                    f"Video too large: {int(content_length)} bytes (max: {MAX_VIDEO_SIZE})",
                )

            # Download the video
            response = requests.get(
                clean_url,
                headers=headers,
                stream=True,
                timeout=TIMEOUT_DOWNLOAD,
                allow_redirects=True,
            )
            response.raise_for_status()

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            downloaded_size = 0

            try:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        temp_file.write(chunk)
                        downloaded_size += len(chunk)

                        if downloaded_size > MAX_VIDEO_SIZE:
                            temp_file.close()
                            os.unlink(temp_file.name)
                            return None, "Video too large during download"

                temp_file.close()

                if downloaded_size == 0:
                    os.unlink(temp_file.name)
                    return None, "Downloaded file is empty"

                logger.info(f"Successfully downloaded video: {downloaded_size} bytes")
                return temp_file.name, None

            except Exception as e:
                temp_file.close()
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                raise e

        except requests.exceptions.Timeout:
            logger.warning(f"Download timeout on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            return None, "Download timeout"

        except requests.exceptions.RequestException as e:
            logger.warning(f"Download failed on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            return None, f"Download error: {str(e)}"

        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            return None, f"Unexpected error: {str(e)}"

    return None, "All download attempts failed"


def upload_video_to_facebook(temp_file_path):
    """Upload video file to Facebook and return attachment ID"""
    try:
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/message_attachments"

        params = {"access_token": PAGE_ACCESS_TOKEN}

        data = {
            "message": json.dumps(
                {"attachment": {"type": "video", "payload": {"is_reusable": False}}}
            )
        }

        # Detect file type
        content_type, _ = mimetypes.guess_type(temp_file_path)
        if not content_type or not content_type.startswith("video/"):
            content_type = "video/mp4"

        with open(temp_file_path, "rb") as video_file:
            files = {"filedata": ("video.mp4", video_file, content_type)}

            logger.info("Uploading video to Facebook...")
            response = requests.post(
                url, params=params, data=data, files=files, timeout=TIMEOUT_UPLOAD
            )

        if response.status_code == 200:
            result = response.json()
            attachment_id = result.get("attachment_id")

            if attachment_id:
                logger.info(
                    f"Video uploaded successfully, attachment_id: {attachment_id}"
                )
                return attachment_id, None
            else:
                logger.error(f"No attachment_id in response: {result}")
                return None, "Upload successful but no attachment ID returned"
        else:
            logger.error(f"Upload failed: {response.status_code} - {response.text}")
            return None, f"Upload failed: {response.status_code}"

    except requests.exceptions.Timeout:
        return None, "Upload timeout"
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return None, f"Upload error: {str(e)}"


def send_video_by_attachment_id(recipient_id, attachment_id):
    """Send video using Facebook attachment ID"""
    try:
        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "video",
                    "payload": {"attachment_id": attachment_id},
                }
            },
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Video sent successfully using attachment ID")
            return result
        else:
            logger.error(
                f"Failed to send video: {response.status_code} - {response.text}"
            )
            return {"error": f"Send failed: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error sending video by attachment ID: {str(e)}")
        return {"error": f"Send error: {str(e)}"}


def send_video_by_url_fallback(recipient_id, video_url):
    """Fallback method: send video by URL (often fails but worth trying)"""
    try:
        # Clean URL for Facebook compatibility
        clean_url = clean_video_url_for_download(video_url)

        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "video",
                    "payload": {"url": clean_url, "is_reusable": False},
                }
            },
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            logger.info("Video sent successfully by URL")
            return result
        else:
            logger.error(f"URL method failed: {response.status_code} - {response.text}")
            return {"error": f"URL send failed: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error sending video by URL: {str(e)}")
        return {"error": f"URL send error: {str(e)}"}


def send_video_attachment(recipient_id, video_url, use_upload=True):
    """Main function to send video with comprehensive fallback methods"""
    if not video_url:
        return {"error": "No video URL provided"}

    if str(recipient_id) == str(PAGE_ID):
        logger.debug("Skipping video send to page ID (echo message)")
        return {"error": "Cannot send to page ID"}

    logger.info(f"Attempting to send video to {recipient_id}")
    logger.debug(f"Video URL: {video_url[:100]}...")

    if use_upload:
        # Method 1: Download and upload (most reliable)
        temp_file_path, download_error = download_video_content(video_url)

        if temp_file_path:
            try:
                # Upload to Facebook
                attachment_id, upload_error = upload_video_to_facebook(temp_file_path)

                if attachment_id:
                    # Send using attachment ID
                    result = send_video_by_attachment_id(recipient_id, attachment_id)
                    os.unlink(temp_file_path)  # Clean up

                    if result and "error" not in result:
                        return result
                    else:
                        logger.warning(
                            "Attachment ID method failed, trying URL fallback"
                        )
                else:
                    logger.warning(f"Upload failed: {upload_error}")

            except Exception as e:
                logger.error(f"Upload process failed: {str(e)}")
            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
        else:
            logger.warning(f"Download failed: {download_error}")

    # Method 2: Send by URL (fallback)
    logger.info("Trying URL method as fallback...")
    url_result = send_video_by_url_fallback(recipient_id, video_url)

    if url_result and "error" not in url_result:
        return url_result

    # If all methods failed
    if use_upload:
        return {
            "error": "Both upload and URL methods failed. Video might be too large, private, or in unsupported format."
        }
    else:
        return url_result


def send_image_attachment(recipient_id, image_url):
    """Send image attachment"""
    try:
        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {"url": image_url, "is_reusable": False},
                }
            },
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Successfully sent image to {recipient_id}")
            return result
        else:
            logger.error(
                f"Failed to send image: {response.status_code} - {response.text}"
            )
            return {"error": f"Image send failed: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error sending image: {str(e)}")
        return {"error": f"Image send error: {str(e)}"}


def send_audio_attachment(recipient_id, audio_url):
    """Send audio attachment"""
    try:
        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "audio",
                    "payload": {"url": audio_url, "is_reusable": False},
                }
            },
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Successfully sent audio to {recipient_id}")
            return result
        else:
            logger.error(
                f"Failed to send audio: {response.status_code} - {response.text}"
            )
            return {"error": f"Audio send failed: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error sending audio: {str(e)}")
        return {"error": f"Audio send error: {str(e)}"}


def send_file_attachment(recipient_id, file_url):
    """Send file attachment"""
    try:
        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "file",
                    "payload": {"url": file_url, "is_reusable": False},
                }
            },
        }

        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"

        response = requests.post(
            url, params=params, headers=headers, json=data, timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Successfully sent file to {recipient_id}")
            return result
        else:
            logger.error(
                f"Failed to send file: {response.status_code} - {response.text}"
            )
            return {"error": f"File send failed: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error sending file: {str(e)}")
        return {"error": f"File send error: {str(e)}"}


def detect_attachment_type(url):
    """Detect attachment type based on URL"""
    url_lower = url.lower()

    video_indicators = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"]
    image_indicators = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]
    audio_indicators = [".mp3", ".wav", ".aac", ".ogg", ".m4a"]

    # Check file extension
    for ext in video_indicators:
        if ext in url_lower:
            return "video"

    for ext in image_indicators:
        if ext in url_lower:
            return "image"

    for ext in audio_indicators:
        if ext in url_lower:
            return "audio"

    # Check domain patterns
    if any(
        domain in url_lower for domain in ["tiktok", "facebook", "instagram", "youtube"]
    ):
        return "video"

    return "file"


def send_attachment(recipient_id, attachment_url, attachment_type=None):
    """Universal attachment sender with auto-detection"""
    if not attachment_url:
        return {"error": "No attachment URL provided"}

    if not attachment_type:
        attachment_type = detect_attachment_type(attachment_url)

    logger.info(f"Sending {attachment_type} attachment to {recipient_id}")

    if attachment_type == "video":
        return send_video_attachment(recipient_id, attachment_url)
    elif attachment_type == "image":
        return send_image_attachment(recipient_id, attachment_url)
    elif attachment_type == "audio":
        return send_audio_attachment(recipient_id, attachment_url)
    else:
        return send_file_attachment(recipient_id, attachment_url)
