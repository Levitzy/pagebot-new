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

user_favorite_sessions = {}
user_tracked_items = {}
PH_OFFSET = 8
TRACKED_ITEMS_FILE = "gagstock_tracked_items.pkl"


def load_tracked_items():
    global user_tracked_items
    try:
        if os.path.exists(TRACKED_ITEMS_FILE):
            with open(TRACKED_ITEMS_FILE, "rb") as f:
                user_tracked_items = pickle.load(f)
            logger.info(f"Loaded tracked items for {len(user_tracked_items)} users")
        else:
            user_tracked_items = {}
            logger.info("No existing tracked items file found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading tracked items: {e}")
        user_tracked_items = {}


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

        timers["cosmetic"] = get_countdown(next_7)

    except Exception as e:
        logger.error(f"Error calculating restocks: {e}")
        timers = {
            "egg": "Error",
            "gear": "Error",
            "seed": "Error",
            "honey": "Error",
            "cosmetic": "Error",
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


def get_available_categories():
    return ["gear", "seed", "egg", "honey", "cosmetic"]


def get_all_items_from_stock(stock_data):
    all_items = []
    categories = {
        "gear": stock_data.get("gear", []),
        "seed": stock_data.get("seed", []),
        "egg": stock_data.get("egg", []),
        "honey": stock_data.get("honey", []),
        "cosmetic": stock_data.get("costmetic", []),
    }

    for category, items in categories.items():
        for item in items:
            all_items.append(
                {
                    "name": item.get("name", "").lower(),
                    "display_name": item.get("name", "Unknown"),
                    "emoji": item.get("emoji", ""),
                    "value": item.get("value", 0),
                    "category": category,
                }
            )

    return all_items


def normalize_item_name(name):
    return name.lower().strip().replace("_", " ").replace("-", " ")


def check_tracked_items_in_stock(sender_id, stock_data):
    if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
        return []

    tracked_in_stock = []
    all_items = get_all_items_from_stock(stock_data)

    for tracked_item in user_tracked_items[sender_id]:
        for item in all_items:
            item_normalized = normalize_item_name(item["display_name"])
            tracked_normalized = normalize_item_name(tracked_item["item_name"])

            if (
                tracked_normalized == item_normalized
                or tracked_normalized in item_normalized
                or item_normalized in tracked_normalized
            ) and item["category"] == tracked_item["category"]:
                tracked_in_stock.append(item)
                break

    return tracked_in_stock


def cleanup_favorite_session(sender_id):
    if sender_id in user_favorite_sessions:
        session = user_favorite_sessions[sender_id]
        timer = session.get("timer")
        if timer:
            timer.cancel()
        del user_favorite_sessions[sender_id]
        logger.info(f"Cleaned up gagstockfav session for {sender_id}")


def fetch_favorite_data(sender_id, send_message_func):
    if sender_id not in user_favorite_sessions:
        logger.info(
            f"Favorite session {sender_id} no longer active, stopping fetch_favorite_data"
        )
        return

    try:
        logger.debug(f"Fetching data for gagstockfav session {sender_id}")

        headers = {"User-Agent": "GagStock-Bot/1.0"}

        try:
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Stock API request failed for favorites: {e}")
            raise

        try:
            weather_response = requests.get(
                "https://growagardenstock.com/api/stock/weather",
                timeout=15,
                headers=headers,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Weather API request failed for favorites: {e}")
            raise

        if stock_response.status_code != 200:
            logger.error(
                f"Stock API error for favorites: {stock_response.status_code} - {stock_response.text}"
            )
            raise requests.RequestException(
                f"Stock API returned {stock_response.status_code}"
            )

        if weather_response.status_code != 200:
            logger.error(
                f"Weather API error for favorites: {weather_response.status_code} - {weather_response.text}"
            )
            raise requests.RequestException(
                f"Weather API returned {weather_response.status_code}"
            )

        try:
            stock_data = stock_response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse stock data JSON for favorites: {e}")
            raise

        try:
            weather_data = weather_response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse weather data JSON for favorites: {e}")
            raise

        combined_key = json.dumps(
            {
                "gear": stock_data.get("gear", []),
                "seed": stock_data.get("seed", []),
                "egg": stock_data.get("egg", []),
                "honey": stock_data.get("honey", []),
                "cosmetic": stock_data.get("cosmetic", []),
                "weatherUpdatedAt": weather_data.get("updatedAt", ""),
                "weatherCurrent": weather_data.get("currentWeather", ""),
            },
            sort_keys=True,
        )

        session = user_favorite_sessions.get(sender_id)
        if not session:
            logger.info(f"Favorite session {sender_id} was removed during fetch")
            return

        if combined_key == session.get("last_combined_key"):
            logger.debug(
                f"No changes detected for favorites {sender_id}, scheduling next check"
            )
        else:
            logger.info(
                f"Data changed for favorites {sender_id}, checking tracked items"
            )
            session["last_combined_key"] = combined_key

            tracked_in_stock = check_tracked_items_in_stock(sender_id, stock_data)
            if tracked_in_stock:
                restocks = get_next_restocks()

                message = "⭐ Your favorite items are in stock!\n\n"

                category_restocks = {
                    "gear": restocks["gear"],
                    "seed": restocks["seed"],
                    "egg": restocks["egg"],
                    "honey": restocks["honey"],
                    "cosmetic": restocks["cosmetic"],
                }

                for item in tracked_in_stock:
                    emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                    restock_time = category_restocks.get(item["category"], "Unknown")
                    message += f"🔔 {emoji_part}{item['display_name']}: {format_value(item['value'])}\n"
                    message += f"   📦 Category: {item['category'].title()} | ⏳ Restock in: {restock_time}\n\n"

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

                message += weather_details

                if message != session.get("last_message"):
                    session["last_message"] = message
                    try:
                        send_message_func(sender_id, message)
                        logger.info(f"Sent gagstockfav update to {sender_id}")
                    except Exception as e:
                        logger.error(
                            f"Failed to send favorite message to {sender_id}: {e}"
                        )

        if sender_id in user_favorite_sessions:
            timer = threading.Timer(
                10.0, fetch_favorite_data, args=[sender_id, send_message_func]
            )
            timer.daemon = True
            timer.start()
            user_favorite_sessions[sender_id]["timer"] = timer
            logger.debug(f"Scheduled next favorite fetch for {sender_id} in 10 seconds")

    except requests.Timeout:
        logger.error(f"Timeout fetching favorite data for {sender_id}")
        if sender_id in user_favorite_sessions:
            timer = threading.Timer(
                30.0, fetch_favorite_data, args=[sender_id, send_message_func]
            )
            timer.daemon = True
            timer.start()
            user_favorite_sessions[sender_id]["timer"] = timer

    except requests.RequestException as e:
        logger.error(f"Network error in gagstockfav for {sender_id}: {e}")
        if sender_id in user_favorite_sessions:
            try:
                send_message_func(
                    sender_id,
                    "⚠️ Stock API temporarily unavailable for favorites\nRetrying in 30 seconds...",
                )
            except:
                pass
            timer = threading.Timer(
                30.0, fetch_favorite_data, args=[sender_id, send_message_func]
            )
            timer.daemon = True
            timer.start()
            user_favorite_sessions[sender_id]["timer"] = timer

    except Exception as e:
        logger.error(f"Unexpected error in gagstockfav for {sender_id}: {e}")
        if sender_id in user_favorite_sessions:
            try:
                send_message_func(
                    sender_id,
                    "❌ Unexpected error occurred in favorites\nStopping tracker. Use 'gagstockfav on' to restart.",
                )
            except:
                pass
        cleanup_favorite_session(sender_id)


def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    load_tracked_items()

    if not args:
        send_message_func(
            sender_id,
            "📌 Gagstockfav Commands:\n\n"
            "⭐ Favorites Tracking:\n"
            "• 'gagstockfav on' - Start tracking only your favorite items\n"
            "• 'gagstockfav off' - Stop favorites tracking\n\n"
            "💡 This tracks only items from your favorites list and notifies\n"
            "when they appear in stock. Independent from 'gagstock on/off'.\n\n"
            "🔔 First add items to favorites:\n"
            "• 'gagstock add category/item_name'\n"
            "• 'gagstock list' to see your favorites\n\n"
            f"📋 Categories: {', '.join(get_available_categories())}\n"
            "🔍 Examples:\n"
            "   • 'gagstock add gear/ancient_shovel'\n"
            "   • 'gagstockfav on' (tracks only favorites)",
        )
        return

    action = args[0].lower()

    if action == "on":
        if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
            send_message_func(
                sender_id,
                "⚠️ You need to add some favorite items first!\n\n"
                "💡 Use 'gagstock add category/item_name' to add items.\n"
                f"📋 Categories: {', '.join(get_available_categories())}\n\n"
                "🔍 Examples:\n"
                "   • 'gagstock add gear/ancient_shovel'\n"
                "   • 'gagstock add egg/legendary_egg'\n\n"
                "Then use 'gagstockfav on' to track only those items.",
            )
            return

        if sender_id in user_favorite_sessions:
            send_message_func(
                sender_id,
                "📡 Gagstockfav is already running!\n"
                "💡 Use 'gagstockfav off' to stop first.",
            )
            return

        tracked_count = len(user_tracked_items[sender_id])
        tracked_list = []
        for item in user_tracked_items[sender_id]:
            tracked_list.append(f"{item['category']}/{item['item_name']}")

        send_message_func(
            sender_id,
            f"⭐ Gagstockfav started! Tracking {tracked_count} favorite items.\n"
            f"🔔 You'll be notified only when your favorite items are in stock.\n\n"
            f"📋 Tracking: {', '.join(tracked_list[:3])}{'...' if tracked_count > 3 else ''}\n\n"
            f"💡 Use 'gagstock list' to see all favorite items.",
        )

        user_favorite_sessions[sender_id] = {
            "timer": None,
            "last_combined_key": None,
            "last_message": "",
        }

        logger.info(f"Started gagstockfav session for {sender_id}")
        fetch_favorite_data(sender_id, send_message_func)
        return

    elif action == "off":
        if sender_id in user_favorite_sessions:
            cleanup_favorite_session(sender_id)
            send_message_func(sender_id, "🛑 Gagstockfav stopped.")
        else:
            send_message_func(sender_id, "⚠️ Gagstockfav is not running.")
        return

    else:
        send_message_func(
            sender_id,
            "❌ Unknown gagstockfav command.\n"
            "💡 Use 'gagstockfav on' or 'gagstockfav off'\n"
            "💡 Use 'gagstockfav' without arguments for help",
        )
