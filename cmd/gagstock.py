import threading
import requests
import json
import logging
from datetime import datetime, timedelta
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from functions.sendTemplate import send_button_template
    from functions.sendMessage import send_message

    TEMPLATE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Template functions not available: {e}")
    TEMPLATE_AVAILABLE = False

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

active_sessions = {}
PH_OFFSET = 8

# Message length limits
MAX_MESSAGE_LENGTH = 1800  # Leave buffer for safety
MAX_BUTTON_MESSAGE_LENGTH = 600  # Button templates have stricter limits


def pad(n):
    return f"0{n}" if n < 10 else str(n)


def get_ph_time():
    if pytz:
        ph_tz = pytz.timezone("Asia/Manila")
        return datetime.now(ph_tz)
    else:
        utc_now = datetime.utcnow()
        return utc_now + timedelta(hours=PH_OFFSET)


def get_countdown(target):
    now = get_ph_time()

    if pytz and target.tzinfo is None:
        target = pytz.timezone("Asia/Manila").localize(target)
    elif not pytz and target.tzinfo is None:
        pass

    if hasattr(target, "tzinfo") and target.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=target.tzinfo)
    elif hasattr(now, "tzinfo") and now.tzinfo is not None and target.tzinfo is None:
        target = target.replace(tzinfo=now.tzinfo)

    time_left = target - now
    if time_left.total_seconds() <= 0:
        return "00h 00m 00s"

    total_seconds = int(time_left.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{pad(hours)}h {pad(minutes)}m {pad(seconds)}s"


def get_next_restocks():
    now = get_ph_time()
    timers = {}

    try:
        next_egg = now.replace(second=0, microsecond=0)
        if now.minute < 30:
            next_egg = next_egg.replace(minute=30)
        else:
            next_egg = next_egg.replace(minute=0) + timedelta(hours=1)
        timers["egg"] = get_countdown(next_egg)

        next_5 = now.replace(second=0, microsecond=0)
        current_minute = now.minute + (1 if now.second > 0 else 0)
        next_minute = ((current_minute + 4) // 5) * 5

        if next_minute >= 60:
            next_5 = next_5.replace(minute=0) + timedelta(hours=1)
        else:
            next_5 = next_5.replace(minute=next_minute)

        timers["gear"] = timers["seed"] = get_countdown(next_5)

        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        timers["honey"] = get_countdown(next_hour)

        current_hour = now.hour
        next_7h_mark = ((current_hour // 7) + 1) * 7

        if next_7h_mark >= 24:
            next_7 = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1, hours=next_7h_mark - 24
            )
        else:
            next_7 = now.replace(hour=next_7h_mark, minute=0, second=0, microsecond=0)

        timers["cosmetics"] = get_countdown(next_7)

    except Exception as e:
        logger.error(f"Error calculating restocks: {e}")
        timers = {
            "egg": "Error",
            "gear": "Error",
            "seed": "Error",
            "honey": "Error",
            "cosmetics": "Error",
        }

    return timers


def format_value(val):
    try:
        val = int(val) if isinstance(val, (str, float)) else val
        if val >= 1_000_000:
            return f"x{val / 1_000_000:.1f}M"
        elif val >= 1_000:
            return f"x{val / 1_000:.1f}K"
        else:
            return f"x{val}"
    except (ValueError, TypeError):
        return f"x{val}"


def format_list_compact(arr, max_items=5):
    """
    Format list in a more compact way with item limit
    """
    if not arr:
        return "None"

    result = []
    items_shown = 0

    for item in arr:
        if items_shown >= max_items:
            remaining = len(arr) - items_shown
            result.append(f"... +{remaining} more")
            break

        try:
            emoji = item.get("emoji", "")
            name = item.get("name", "Unknown")
            value = item.get("value", 0)

            # Shorten long names
            if len(name) > 15:
                name = name[:12] + "..."

            formatted = f"{emoji}{name}: {format_value(value)}"
            result.append(formatted)
            items_shown += 1

        except Exception as e:
            logger.warning(f"Error formatting item {item}: {e}")
            continue

    return " | ".join(result) if result else "None"


def cleanup_session(sender_id):
    if sender_id in active_sessions:
        session = active_sessions[sender_id]
        timer = session.get("timer")
        if timer:
            timer.cancel()
        del active_sessions[sender_id]
        logger.info(f"Cleaned up gagstock session for {sender_id}")


def send_multiple_messages(
    sender_id, messages, send_message_func, use_buttons_on_last=True
):
    """
    Send multiple messages, with buttons on the last one
    """
    success_count = 0

    for i, message in enumerate(messages):
        is_last_message = i == len(messages) - 1

        try:
            if is_last_message and use_buttons_on_last and TEMPLATE_AVAILABLE:
                # Add buttons to the last message
                buttons = [
                    {
                        "type": "postback",
                        "title": "🔄 Refresh",
                        "payload": f"gagstock_refresh_{sender_id}",
                    },
                    {
                        "type": "postback",
                        "title": "🛑 Stop",
                        "payload": f"gagstock_stop_{sender_id}",
                    },
                ]

                result = send_button_template(sender_id, message, buttons)
                if result:
                    success_count += 1
                    logger.info(
                        f"Sent message {i+1}/{len(messages)} with buttons to {sender_id}"
                    )
                else:
                    # Fallback to text
                    send_message_func(sender_id, message)
                    success_count += 1
                    logger.info(
                        f"Sent message {i+1}/{len(messages)} as text (button fallback) to {sender_id}"
                    )
            else:
                # Regular text message
                send_message_func(sender_id, message)
                success_count += 1
                logger.info(f"Sent message {i+1}/{len(messages)} to {sender_id}")

            # Small delay between messages
            if i < len(messages) - 1:
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Failed to send message {i+1} to {sender_id}: {e}")

    return success_count == len(messages)


def fetch_stock_data():
    headers = {"User-Agent": "GagStock-Bot/1.0"}

    try:
        stock_response = requests.get(
            "http://65.108.103.151:22377/api/stocks?type=all",
            timeout=15,
            headers=headers,
        )

        weather_response = requests.get(
            "https://growagardenstock.com/api/stock/weather",
            timeout=15,
            headers=headers,
        )

        if stock_response.status_code != 200:
            logger.error(f"Stock API error: {stock_response.status_code}")
            return None, None

        if weather_response.status_code != 200:
            logger.error(f"Weather API error: {weather_response.status_code}")
            return None, None

        return stock_response.json(), weather_response.json()

    except Exception as e:
        logger.error(f"Error fetching stock data: {e}")
        return None, None


def format_stock_messages(stock_data, weather_data, is_manual_refresh=False):
    """
    Format stock data into multiple messages to avoid length limits
    """
    restocks = get_next_restocks()

    # Format stock data with limits
    gear_list = format_list_compact(stock_data.get("gearStock", []), max_items=8)
    seed_list = format_list_compact(stock_data.get("seedsStock", []), max_items=8)
    egg_list = format_list_compact(stock_data.get("eggStock", []), max_items=8)
    cosmetics_list = format_list_compact(
        stock_data.get("cosmeticsStock", []), max_items=6
    )
    honey_list = format_list_compact(stock_data.get("honeyStock", []), max_items=6)

    refresh_indicator = " 🔄" if is_manual_refresh else ""

    # Message 1: Header + Gear & Seeds
    message1 = (
        f"🌾 Grow A Garden — Tracker{refresh_indicator}\n\n"
        f"🛠️ Gear (⏳ {restocks['gear']}):\n{gear_list}\n\n"
        f"🌱 Seeds (⏳ {restocks['seed']}):\n{seed_list}"
    )

    # Message 2: Eggs, Cosmetics & Honey
    message2 = (
        f"🥚 Eggs (⏳ {restocks['egg']}):\n{egg_list}\n\n"
        f"🎨 Cosmetics (⏳ {restocks['cosmetics']}):\n{cosmetics_list}\n\n"
        f"🍯 Honey (⏳ {restocks['honey']}):\n{honey_list}"
    )

    # Message 3: Weather (with buttons)
    weather_icon = weather_data.get("icon", "🌦️")
    weather_current = weather_data.get("currentWeather", "Unknown")
    weather_description = weather_data.get("description", "")
    weather_effect = weather_data.get("effectDescription", "")
    weather_bonus = weather_data.get("cropBonuses", "")
    weather_rarity = weather_data.get("rarity", "Unknown")

    message3 = f"🌤️ Weather: {weather_icon} {weather_current}"

    if weather_description and len(weather_description) < 100:
        message3 += f"\n📖 {weather_description}"
    if weather_effect and len(weather_effect) < 100:
        message3 += f"\n📌 {weather_effect}"
    if weather_bonus and len(weather_bonus) < 100:
        message3 += f"\n🪄 {weather_bonus}"
    if weather_rarity:
        message3 += f"\n🌟 Rarity: {weather_rarity}"

    messages = [message1, message2, message3]

    # Check if any message is too long and truncate if needed
    for i, msg in enumerate(messages):
        if len(msg) > MAX_MESSAGE_LENGTH:
            messages[i] = msg[: MAX_MESSAGE_LENGTH - 3] + "..."
            logger.warning(f"Message {i+1} was truncated due to length")

    return messages


def fetch_all_data(sender_id, send_message_func, force_update=False):
    if sender_id not in active_sessions:
        logger.info(f"Session {sender_id} no longer active, stopping fetch_all_data")
        return

    try:
        logger.debug(
            f"Fetching data for gagstock session {sender_id} (force: {force_update})"
        )

        stock_data, weather_data = fetch_stock_data()

        if not stock_data or not weather_data:
            logger.error(f"Failed to fetch data for {sender_id}")
            if sender_id in active_sessions:
                timer = threading.Timer(
                    30.0, fetch_all_data, args=[sender_id, send_message_func, False]
                )
                timer.daemon = True
                timer.start()
                active_sessions[sender_id]["timer"] = timer
            return

        combined_key = json.dumps(
            {
                "gearStock": stock_data.get("gearStock", []),
                "seedsStock": stock_data.get("seedsStock", []),
                "eggStock": stock_data.get("eggStock", []),
                "honeyStock": stock_data.get("honeyStock", []),
                "cosmeticsStock": stock_data.get("cosmeticsStock", []),
                "weatherUpdatedAt": weather_data.get("updatedAt", ""),
                "weatherCurrent": weather_data.get("currentWeather", ""),
            },
            sort_keys=True,
        )

        session = active_sessions.get(sender_id)
        if not session:
            logger.info(f"Session {sender_id} was removed during fetch")
            return

        should_send = (
            combined_key != session.get("last_combined_key")
            or force_update
            or not session.get("last_message")
        )

        if should_send:
            logger.info(f"Sending update to {sender_id} (force: {force_update})")
            session["last_combined_key"] = combined_key

            messages = format_stock_messages(stock_data, weather_data, force_update)

            if send_multiple_messages(sender_id, messages, send_message_func):
                session["last_message"] = (
                    combined_key  # Store key instead of full message
                )
                logger.info(
                    f"Successfully sent {len(messages)} messages to {sender_id}"
                )
            else:
                logger.error(f"Failed to send some messages to {sender_id}")
        else:
            logger.debug(f"No changes detected for {sender_id}, scheduling next check")

        if sender_id in active_sessions:
            timer = threading.Timer(
                10.0, fetch_all_data, args=[sender_id, send_message_func, False]
            )
            timer.daemon = True
            timer.start()
            active_sessions[sender_id]["timer"] = timer
            logger.debug(f"Scheduled next fetch for {sender_id} in 10 seconds")

    except Exception as e:
        logger.error(f"Unexpected error in gagstock for {sender_id}: {e}")
        if sender_id in active_sessions:
            timer = threading.Timer(
                20.0, fetch_all_data, args=[sender_id, send_message_func, False]
            )
            timer.daemon = True
            timer.start()
            active_sessions[sender_id]["timer"] = timer


def handle_refresh(sender_id, send_message_func):
    if sender_id not in active_sessions:
        send_message_func(
            sender_id,
            "⚠️ No active gagstock session found. Use `gagstock on` to start tracking.",
        )
        return

    logger.info(f"Manual refresh requested by {sender_id}")
    fetch_all_data(sender_id, send_message_func, force_update=True)


def handle_stop(sender_id, send_message_func):
    if sender_id in active_sessions:
        cleanup_session(sender_id)
        send_message_func(sender_id, "🛑 Gagstock tracking stopped.")
    else:
        send_message_func(sender_id, "⚠️ You don't have an active gagstock session.")


def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    if not args:
        send_message_func(
            sender_id,
            "📌 Gagstock Usage:\n• `gagstock on` - Start tracking\n• `gagstock off` - Stop tracking\n• `gagstock refresh` - Manual refresh\n• Use buttons for quick actions!",
        )
        return

    action = args[0].lower()

    if action == "off" or action == "stop":
        handle_stop(sender_id, send_message_func)
        return

    if action == "refresh":
        handle_refresh(sender_id, send_message_func)
        return

    if action != "on":
        send_message_func(
            sender_id,
            "📌 Gagstock Usage:\n• `gagstock on` - Start tracking\n• `gagstock off` - Stop tracking\n• `gagstock refresh` - Manual refresh",
        )
        return

    if sender_id in active_sessions:
        send_message_func(
            sender_id,
            "📡 You're already tracking Gagstock. Use the 🔄 button or `gagstock refresh` to get latest data!",
        )
        return

    active_sessions[sender_id] = {
        "timer": None,
        "last_combined_key": None,
        "last_message": "",
    }

    logger.info(f"Started gagstock session for {sender_id}")
    send_message_func(
        sender_id, "✅ Gagstock tracking started! Getting initial data..."
    )

    fetch_all_data(sender_id, send_message_func, force_update=True)
