import threading
import requests
import json
import logging
from datetime import datetime, timedelta

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

active_sessions = {}
PH_OFFSET = 8


def pad(n):
    return f"0{n}" if n < 10 else str(n)


def get_ph_time():
    if pytz:
        ph_tz = pytz.timezone("Asia/Manila")
        return datetime.now(ph_tz)
    else:
        return datetime.now() + timedelta(hours=PH_OFFSET)


def get_countdown(target):
    now = get_ph_time()
    if pytz and target.tzinfo is None:
        target = pytz.timezone("Asia/Manila").localize(target)
    elif not pytz and target.tzinfo is None:
        target = target

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

    next_egg = now.replace(second=0, microsecond=0)
    if now.minute < 30:
        next_egg = next_egg.replace(minute=30)
    else:
        next_egg = next_egg.replace(minute=0) + timedelta(hours=1)
    timers["egg"] = get_countdown(next_egg)

    next_5 = now.replace(second=0, microsecond=0)
    next_minute = ((now.minute + (1 if now.second > 0 else 0) + 4) // 5) * 5
    if next_minute >= 60:
        next_5 = next_5.replace(minute=0) + timedelta(hours=1)
    else:
        next_5 = next_5.replace(minute=next_minute)
    timers["gear"] = timers["seed"] = get_countdown(next_5)

    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    timers["honey"] = get_countdown(next_hour)

    total_hours = now.hour + now.minute / 60 + now.second / 3600
    next_7h = ((int(total_hours) // 7) + 1) * 7
    next_7 = now.replace(hour=next_7h % 24, minute=0, second=0, microsecond=0)
    if next_7h >= 24:
        next_7 = next_7 + timedelta(days=next_7h // 24)
    timers["cosmetics"] = get_countdown(next_7)

    return timers


def format_value(val):
    if val >= 1_000_000:
        return f"x{val / 1_000_000:.1f}M"
    elif val >= 1_000:
        return f"x{val / 1_000:.1f}K"
    else:
        return f"x{val}"


def format_list(arr):
    if not arr:
        return "None."

    result = []
    for item in arr:
        emoji = item.get("emoji", "")
        name = item.get("name", "")
        value = item.get("value", 0)
        emoji_part = f"{emoji} " if emoji else ""
        result.append(f"- {emoji_part}{name}: {format_value(value)}")

    return "\n".join(result)


def fetch_all_data(sender_id, send_message_func):
    try:
        stock_response = requests.get(
            "http://65.108.103.151:22377/api/stocks?type=all", timeout=10
        )
        weather_response = requests.get(
            "https://growagardenstock.com/api/stock/weather", timeout=10
        )

        if stock_response.status_code != 200 or weather_response.status_code != 200:
            logger.error(
                f"API error - Stock: {stock_response.status_code}, Weather: {weather_response.status_code}"
            )
            return

        stock_data = stock_response.json()
        weather_data = weather_response.json()

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
            return

        if combined_key == session.get("last_combined_key"):
            return

        session["last_combined_key"] = combined_key

        restocks = get_next_restocks()

        gear_list = format_list(stock_data.get("gearStock", []))
        seed_list = format_list(stock_data.get("seedsStock", []))
        egg_list = format_list(stock_data.get("eggStock", []))
        cosmetics_list = format_list(stock_data.get("cosmeticsStock", []))
        honey_list = format_list(stock_data.get("honeyStock", []))

        weather_icon = weather_data.get("icon", "🌦️")
        weather_current = weather_data.get("currentWeather", "Unknown")
        weather_description = weather_data.get("description", "No description")
        weather_effect = weather_data.get("effectDescription", "No effect")
        weather_bonus = weather_data.get("cropBonuses", "No bonus")
        weather_visual = weather_data.get("visualCue", "No visual cue")
        weather_rarity = weather_data.get("rarity", "Unknown")

        weather_details = (
            f"🌤️ Weather: {weather_icon} {weather_current}\n"
            f"📖 Description: {weather_description}\n"
            f"📌 Effect: {weather_effect}\n"
            f"🪄 Crop Bonus: {weather_bonus}\n"
            f"📢 Visual Cue: {weather_visual}\n"
            f"🌟 Rarity: {weather_rarity}"
        )

        message = (
            f"🌾 Grow A Garden — Tracker\n\n"
            f"🛠️ Gear:\n{gear_list}\n⏳ Restock in: {restocks['gear']}\n\n"
            f"🌱 Seeds:\n{seed_list}\n⏳ Restock in: {restocks['seed']}\n\n"
            f"🥚 Eggs:\n{egg_list}\n⏳ Restock in: {restocks['egg']}\n\n"
            f"🎨 Cosmetics:\n{cosmetics_list}\n⏳ Restock in: {restocks['cosmetics']}\n\n"
            f"🍯 Honey:\n{honey_list}\n⏳ Restock in: {restocks['honey']}\n\n"
            f"{weather_details}"
        )

        if message != session.get("last_message"):
            session["last_message"] = message
            send_message_func(sender_id, message)

        timer = threading.Timer(
            10.0, fetch_all_data, args=[sender_id, send_message_func]
        )
        timer.start()
        session["timer"] = timer

    except requests.RequestException as e:
        logger.error(f"Network error in gagstock for {sender_id}: {e}")
    except Exception as e:
        logger.error(f"Error in gagstock for {sender_id}: {e}")


def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    if not args:
        send_message_func(
            sender_id,
            "📌 Usage:\n• `gagstock on` to start tracking\n• `gagstock off` to stop tracking",
        )
        return

    action = args[0].lower()

    if action == "off":
        session = active_sessions.get(sender_id)
        if session:
            timer = session.get("timer")
            if timer:
                timer.cancel()
            del active_sessions[sender_id]
            send_message_func(sender_id, "🛑 Gagstock tracking stopped.")
        else:
            send_message_func(sender_id, "⚠️ You don't have an active gagstock session.")
        return

    if action != "on":
        send_message_func(
            sender_id,
            "📌 Usage:\n• `gagstock on` to start tracking\n• `gagstock off` to stop tracking",
        )
        return

    if sender_id in active_sessions:
        send_message_func(
            sender_id,
            "📡 You're already tracking Gagstock. Use `gagstock off` to stop.",
        )
        return

    send_message_func(
        sender_id,
        "✅ Gagstock tracking started! You'll be notified when stock or weather changes.",
    )

    active_sessions[sender_id] = {
        "timer": None,
        "last_combined_key": None,
        "last_message": "",
    }

    fetch_all_data(sender_id, send_message_func)
