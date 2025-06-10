import requests
import json
import logging
import os
import tempfile
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

with open("config.json", "r") as f:
    config = json.load(f)

PAGE_ACCESS_TOKEN = config["page_access_token"]
GRAPH_API_VERSION = config["graph_api_version"]
PAGE_ID = config.get("page_id", "612984285242194")

MAX_VIDEO_SIZE = 25 * 1024 * 1024  # 25MB limit for Facebook videos
SUPPORTED_VIDEO_FORMATS = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".gif", ".webp"]


def get_file_size_from_url(url):
    """Get file size from URL without downloading the entire file"""
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            content_length = response.headers.get("content-length")
            if content_length:
                return int(content_length)
    except Exception as e:
        logger.warning(f"Could not get file size from URL: {e}")
    return None


def download_file_with_progress(url, max_size=MAX_VIDEO_SIZE):
    """Download file with size checking and progress tracking"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()

        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_size:
            logger.warning(
                f"File too large: {int(content_length)} bytes (max: {max_size})"
            )
            return None, "File too large"

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        downloaded_size = 0

        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
                downloaded_size += len(chunk)

                if downloaded_size > max_size:
                    temp_file.close()
                    os.unlink(temp_file.name)
                    logger.warning(
                        f"File too large during download: {downloaded_size} bytes"
                    )
                    return None, "File too large"

        temp_file.close()
        logger.info(f"Successfully downloaded file: {downloaded_size} bytes")
        return temp_file.name, None

    except requests.exceptions.Timeout:
        return None, "Download timeout"
    except requests.exceptions.RequestException as e:
        return None, f"Download error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected download error: {str(e)}"


def send_video_attachment_by_upload(recipient_id, video_url):
    """Send video by downloading and uploading to Facebook"""
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN not configured")
        return None

    if str(recipient_id) == str(PAGE_ID):
        logger.debug("Skipping video send to page ID (echo message)")
        return None

    logger.info(f"Attempting to send video to {recipient_id}: {video_url}")

    # Download the video file
    temp_file_path, error = download_file_with_progress(video_url)
    if error:
        logger.error(f"Failed to download video: {error}")
        return {"error": error}

    try:
        # Upload video to Facebook
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/message_attachments"

        params = {"access_token": PAGE_ACCESS_TOKEN}

        data = {
            "message": json.dumps(
                {"attachment": {"type": "video", "payload": {"is_reusable": False}}}
            )
        }

        with open(temp_file_path, "rb") as video_file:
            files = {"filedata": ("video.mp4", video_file, "video/mp4")}

            logger.info(f"Uploading video to Facebook for recipient {recipient_id}")
            response = requests.post(
                url, params=params, data=data, files=files, timeout=120
            )

        # Clean up temp file
        os.unlink(temp_file_path)

        if response.status_code == 200:
            upload_result = response.json()
            attachment_id = upload_result.get("attachment_id")

            if attachment_id:
                # Send the uploaded video
                return send_uploaded_attachment(recipient_id, attachment_id, "video")
            else:
                logger.error(f"No attachment_id in upload response: {upload_result}")
                return {"error": "Failed to get attachment ID"}
        else:
            logger.error(
                f"Video upload failed: {response.status_code} - {response.text}"
            )
            return {"error": f"Upload failed: {response.status_code}"}

    except Exception as e:
        if "temp_file_path" in locals() and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        logger.error(f"Error uploading video: {str(e)}")
        return {"error": f"Upload error: {str(e)}"}


def send_uploaded_attachment(recipient_id, attachment_id, attachment_type):
    """Send an already uploaded attachment using its ID"""
    try:
        params = {"access_token": PAGE_ACCESS_TOKEN}
        headers = {"Content-Type": "application/json"}
        data = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": attachment_type,
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
            logger.info(f"Successfully sent {attachment_type} to {recipient_id}")
            return result
        else:
            logger.error(
                f"Failed to send {attachment_type}: {response.status_code} - {response.text}"
            )
            return {"error": f"Send failed: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error sending {attachment_type}: {str(e)}")
        return {"error": f"Send error: {str(e)}"}


def send_video_attachment_by_url(recipient_id, video_url):
    """Send video by URL (fallback method)"""
    try:
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

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Successfully sent video by URL to {recipient_id}")
            return result
        else:
            logger.error(
                f"Failed to send video by URL: {response.status_code} - {response.text}"
            )
            return {"error": f"URL send failed: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error sending video by URL: {str(e)}")
        return {"error": f"URL send error: {str(e)}"}


def send_video_attachment(recipient_id, video_url, use_upload=True):
    """Main function to send video attachment with fallback methods"""
    if not video_url:
        return {"error": "No video URL provided"}

    logger.info(f"Sending video to {recipient_id}, upload method: {use_upload}")

    # Check file size first
    file_size = get_file_size_from_url(video_url)
    if file_size and file_size > MAX_VIDEO_SIZE:
        logger.warning(f"Video too large: {file_size} bytes (max: {MAX_VIDEO_SIZE})")
        return {"error": "Video file too large"}

    if use_upload:
        # Try upload method first
        result = send_video_attachment_by_upload(recipient_id, video_url)
        if result and "error" not in result:
            return result

        logger.warning("Upload method failed, trying URL method")

    # Fallback to URL method
    return send_video_attachment_by_url(recipient_id, video_url)


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


def detect_attachment_type(url):
    """Detect attachment type based on URL"""
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()

    for ext in SUPPORTED_VIDEO_FORMATS:
        if path.endswith(ext):
            return "video"

    for ext in SUPPORTED_IMAGE_FORMATS:
        if path.endswith(ext):
            return "image"

    # Default to video for social media URLs
    if any(
        domain in url.lower()
        for domain in ["tiktok", "facebook", "instagram", "youtube"]
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
