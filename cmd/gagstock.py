import threading
import requests
import json
import logging
from datetime import datetime, timedelta
import time
import os
import pickle

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

active_sessions = {}
last_sent_cache = {}
PH_OFFSET = 8


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


def add_emoji(name):
    emojis = {
        "Common Egg": "🥚",
        "Uncommon Egg": "🐣",
        "Rare Egg": "🍳",
        "Legendary Egg": "🪺",
        "Mythical Egg": "🥚",
        "Bug Egg": "🪲",
        "Watering Can": "🚿",
        "Trowel": "🛠️",
        "Recall Wrench": "🔧",
        "Basic Sprinkler": "💧",
        "Advanced Sprinkler": "💦",
        "Godly Sprinkler": "⛲",
        "Lightning Rod": "⚡",
        "Master Sprinkler": "🌊",
        "Favorite Tool": "❤️",
        "Harvest Tool": "🌾",
        "Carrot": "🥕",
        "Strawberry": "🍓",
        "Blueberry": "🫐",
        "Orange Tulip": "🌷",
        "Tomato": "🍅",
        "Corn": "🌽",
        "Daffodil": "🌼",
        "Watermelon": "🍉",
        "Pumpkin": "🎃",
        "Apple": "🍎",
        "Bamboo": "🎍",
        "Coconut": "🥥",
        "Cactus": "🌵",
        "Dragon Fruit": "🍈",
        "Mango": "🥭",
        "Grape": "🍇",
        "Mushroom": "🍄",
        "Pepper": "🌶️",
        "Cacao": "🍫",
        "Beanstalk": "🌱",
    }
    emoji = emojis.get(name, "")
    return f"{emoji} {name}" if emoji else name


def normalize_stock_data(stock_data):
    def transform(arr):
        return [{"name": item["name"], "value": item["value"]} for item in arr]

    return {
        "gearStock": transform(stock_data.get("gearStock", [])),
        "seedsStock": transform(stock_data.get("seedsStock", [])),
        "eggStock": transform(stock_data.get("eggStock", [])),
        "honeyStock": transform(stock_data.get("honeyStock", [])),
        "cosmeticsStock": transform(stock_data.get("cosmeticsStock", [])),
    }


def format_weather_data(weather_data):
    active_weathers = []

    for weather_type, data in weather_data.items():
        if data.get("active", False):
            active_weathers.append(f"{weather_type.title()}: Active")
        else:
            active_weathers.append(f"{weather_type.title()}: Inactive")

    if not active_weathers:
        return "🌤️ Weather: No active weather events"

    weather_status = " | ".join(active_weathers)
    return f"🌤️ Weather: {weather_status}"


def cleanup_session(sender_id):
    if sender_id in active_sessions:
        session = active_sessions[sender_id]
        timer = session.get("timer")
        if timer:
            timer.cancel()
        del active_sessions[sender_id]
        if sender_id in last_sent_cache:
            del last_sent_cache[sender_id]
        logger.info(f"Cleaned up gagstock session for {sender_id}")


def fetch_with_timeout(url, timeout=9):
    try:
        headers = {"User-Agent": "GagStock-Bot/1.0"}
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        raise


def fetch_and_notify(sender_id, send_message_func, filters=None):
    if sender_id not in active_sessions:
        logger.info(f"Session {sender_id} no longer active, stopping fetch_and_notify")
        return False

    try:
        logger.debug(f"Fetching data for gagstock session {sender_id}")

        try:
            stock_response = fetch_with_timeout(
                "https://vmi2625091.contaboserver.net/api/stocks"
            )
            weather_response = fetch_with_timeout(
                "https://vmi2625091.contaboserver.net/api/weather"
            )
        except requests.exceptions.RequestException:
            return False

        try:
            stock_data = stock_response.json()
            weather_data = weather_response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return False

        normalized = normalize_stock_data(stock_data)
        current_stock_only = {
            "gear": normalized["gearStock"],
            "seeds": normalized["seedsStock"],
            "egg": normalized["eggStock"],
            "honey": normalized["honeyStock"],
            "cosmetics": normalized["cosmeticsStock"],
        }

        current_key = json.dumps(current_stock_only, sort_keys=True)
        last_sent = last_sent_cache.get(sender_id)

        if last_sent == current_key:
            return False

        last_sent_cache[sender_id] = current_key

        restocks = get_next_restocks()
        updated_at_ph = get_ph_time().strftime("%I:%M:%S %p, %d %b %Y")

        def format_list(arr):
            return "\n".join(
                [
                    f"- {add_emoji(item['name'])}: {format_value(item['value'])}"
                    for item in arr
                ]
            )

        weather_details = format_weather_data(weather_data)
        weather_details += f"\n📅 Updated at (Philippines): {updated_at_ph}"

        categories = [
            {
                "label": "🛠️ 𝗚𝗲𝗮𝗿",
                "items": stock_data.get("gearStock", []),
                "restock": restocks["gear"],
            },
            {
                "label": "🌱 𝗦𝗲𝗲𝗱𝘀",
                "items": stock_data.get("seedsStock", []),
                "restock": restocks["seed"],
            },
            {
                "label": "🥚 𝗘𝗴𝗴𝘀",
                "items": stock_data.get("eggStock", []),
                "restock": restocks["egg"],
            },
            {
                "label": "🎨 𝗖𝗼𝘀𝗺𝗲𝘁𝗶𝗰𝘀",
                "items": stock_data.get("cosmeticsStock", []),
                "restock": restocks["cosmetics"],
            },
            {
                "label": "🍯 𝗛𝗼𝗻𝗲𝘆",
                "items": stock_data.get("honeyStock", []),
                "restock": restocks["honey"],
            },
        ]

        filtered_content = ""
        for category in categories:
            label, items, restock = (
                category["label"],
                category["items"],
                category["restock"],
            )

            if filters:
                filtered_items = [
                    item
                    for item in items
                    if any(f.lower() in item["name"].lower() for f in filters)
                ]
            else:
                filtered_items = items

            if filtered_items:
                filtered_content += f"{label}:\n{format_list(filtered_items)}\n⏳ Restock in: {restock}\n\n"

        if not filtered_content.strip():
            return False

        message = f"🌾 𝗚𝗿𝗼𝘄 𝗔 𝗚𝗮𝗿𝗱𝗲𝗻 — 𝗧𝗿𝗮𝗰𝗸𝗲𝗿\n\n{filtered_content}{weather_details}"

        try:
            send_message_func(sender_id, message)
            logger.info(f"Sent gagstock update to {sender_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {sender_id}: {e}")
            return False

    except Exception as e:
        logger.error(f"Unexpected error in gagstock for {sender_id}: {e}")
        return False


def schedule_next_fetch(sender_id, send_message_func, filters=None):
    if sender_id not in active_sessions:
        return

    now = get_ph_time()
    next_time = now.replace(second=30, microsecond=0)
    mins = now.minute
    next_min = mins - (mins % 5) + 5
    next_time = next_time.replace(minute=next_min)

    if next_time <= now:
        next_time = next_time + timedelta(minutes=5)

    timeout = (next_time - now).total_seconds()

    def run_and_schedule():
        if sender_id in active_sessions:
            fetch_and_notify(sender_id, send_message_func, filters)
            timer = threading.Timer(300.0, run_and_schedule)
            timer.daemon = True
            timer.start()
            active_sessions[sender_id]["timer"] = timer

    timer = threading.Timer(timeout, run_and_schedule)
    timer.daemon = True
    timer.start()
    active_sessions[sender_id] = {"timer": timer}


def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    if not args:
        send_message_func(
            sender_id,
            "📌 Usage:\n• gagstock on\n• gagstock on Sunflower | Watering Can\n• gagstock off",
        )
        return

    action = args[0].lower()
    filters = None

    if len(args) > 1:
        filter_string = " ".join(args[1:])
        filters = [f.strip() for f in filter_string.split("|") if f.strip()]

    if action == "off":
        if sender_id in active_sessions:
            cleanup_session(sender_id)
            send_message_func(sender_id, "🛑 Gagstock tracking stopped.")
        else:
            send_message_func(sender_id, "⚠️ You don't have an active gagstock session.")
        return

    if action != "on":
        send_message_func(
            sender_id,
            "📌 Usage:\n• gagstock on\n• gagstock on Sunflower | Watering Can\n• gagstock off",
        )
        return

    if sender_id in active_sessions:
        send_message_func(
            sender_id, "📡 You're already tracking Gagstock. Use gagstock off to stop."
        )
        return

    send_message_func(
        sender_id,
        "✅ Gagstock tracking started! You'll be notified when stock or weather changes.",
    )

    logger.info(f"Started gagstock session for {sender_id}")

    fetch_and_notify(sender_id, send_message_func, filters)
    schedule_next_fetch(sender_id, send_message_func, filters)
