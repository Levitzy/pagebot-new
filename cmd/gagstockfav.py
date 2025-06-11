import threading
import requests
import json
import logging
from datetime import datetime, timedelta
import time
import os
import pickle
from collections import defaultdict
import statistics
import hashlib

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

user_favorite_sessions = {}
user_tracked_items = {}
user_preferences = {}
user_favorite_stats = {}
user_notification_history = {}
user_custom_filters = {}
price_history = defaultdict(list)
user_last_command_time = {}
user_command_usage = defaultdict(int)
message_cache = {}

PH_OFFSET = 8
COMMAND_COOLDOWN = 3
SPAM_THRESHOLD = 5
CACHE_DURATION = 60
MAX_COMMANDS_PER_MINUTE = 8

TRACKED_ITEMS_FILE = "gagstock_tracked_items.pkl"
USER_PREFERENCES_FILE = "gagstock_user_preferences.pkl"
FAVORITE_STATS_FILE = "gagstockfav_stats.pkl"
NOTIFICATION_HISTORY_FILE = "gagstockfav_notifications.pkl"
CUSTOM_FILTERS_FILE = "gagstockfav_filters.pkl"
PRICE_HISTORY_FILE = "gagstock_price_history.pkl"


def load_all_data():
    global user_tracked_items, user_preferences, user_favorite_stats, user_notification_history, user_custom_filters, price_history

    files_to_load = [
        (TRACKED_ITEMS_FILE, "user_tracked_items"),
        (USER_PREFERENCES_FILE, "user_preferences"),
        (FAVORITE_STATS_FILE, "user_favorite_stats"),
        (NOTIFICATION_HISTORY_FILE, "user_notification_history"),
        (CUSTOM_FILTERS_FILE, "user_custom_filters"),
        (PRICE_HISTORY_FILE, "price_history"),
    ]

    for file_path, var_name in files_to_load:
        try:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    data = pickle.load(f)
                    globals()[var_name] = data
                logger.info(f"Loaded {var_name} from {file_path}")
            else:
                if var_name == "price_history":
                    globals()[var_name] = defaultdict(list)
                else:
                    globals()[var_name] = {}
                logger.info(f"No existing {file_path} found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            if var_name == "price_history":
                globals()[var_name] = defaultdict(list)
            else:
                globals()[var_name] = {}


def save_data(data_type):
    file_mapping = {
        "tracked_items": (TRACKED_ITEMS_FILE, user_tracked_items),
        "preferences": (USER_PREFERENCES_FILE, user_preferences),
        "favorite_stats": (FAVORITE_STATS_FILE, user_favorite_stats),
        "notifications": (NOTIFICATION_HISTORY_FILE, user_notification_history),
        "filters": (CUSTOM_FILTERS_FILE, user_custom_filters),
        "price_history": (PRICE_HISTORY_FILE, dict(price_history)),
    }

    try:
        file_path, data = file_mapping[data_type]
        with open(file_path, "wb") as f:
            pickle.dump(data, f)
        logger.debug(f"Saved {data_type} to {file_path}")
    except Exception as e:
        logger.error(f"Error saving {data_type}: {e}")


def check_spam_protection(sender_id):
    current_time = time.time()
    minute_window = int(current_time // 60)

    if sender_id not in user_command_usage:
        user_command_usage[sender_id] = {}

    if minute_window not in user_command_usage[sender_id]:
        user_command_usage[sender_id] = {minute_window: 1}
    else:
        user_command_usage[sender_id][minute_window] += 1

    old_windows = [w for w in user_command_usage[sender_id] if w < minute_window - 2]
    for w in old_windows:
        del user_command_usage[sender_id][w]

    if user_command_usage[sender_id][minute_window] > MAX_COMMANDS_PER_MINUTE:
        return (
            False,
            f"⚠️ Rate limit exceeded. Please wait before sending more commands. (Max {MAX_COMMANDS_PER_MINUTE}/minute)",
        )

    if sender_id in user_last_command_time:
        time_since_last = current_time - user_last_command_time[sender_id]
        if time_since_last < COMMAND_COOLDOWN:
            remaining = COMMAND_COOLDOWN - time_since_last
            return (
                False,
                f"⏳ Please wait {remaining:.1f} more seconds before using another command.",
            )

    user_last_command_time[sender_id] = current_time
    return True, None


def get_cached_message(cache_key):
    current_time = time.time()
    if cache_key in message_cache:
        cached_data = message_cache[cache_key]
        if current_time - cached_data["timestamp"] < CACHE_DURATION:
            return cached_data["message"]
        else:
            del message_cache[cache_key]
    return None


def cache_message(cache_key, message):
    message_cache[cache_key] = {"message": message, "timestamp": time.time()}


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

        current_minute = now.minute
        next_5_minute_mark = ((current_minute // 5) + 1) * 5
        next_5 = now.replace(second=0, microsecond=0)

        if next_5_minute_mark >= 60:
            next_5 = next_5.replace(minute=0) + timedelta(hours=1)
        else:
            next_5 = next_5.replace(minute=next_5_minute_mark)

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


def get_upcoming_restocks():
    now = get_ph_time()
    upcoming = []

    try:
        next_egg = now.replace(second=0, microsecond=0)
        if now.minute < 30:
            next_egg = next_egg.replace(minute=30)
        else:
            next_egg = next_egg.replace(minute=0) + timedelta(hours=1)

        time_to_egg = (next_egg - now).total_seconds()
        if time_to_egg <= 300:
            upcoming.append(("egg", get_countdown(next_egg)))

        current_minute = now.minute
        next_5_minute_mark = ((current_minute // 5) + 1) * 5
        next_5 = now.replace(second=0, microsecond=0)

        if next_5_minute_mark >= 60:
            next_5 = next_5.replace(minute=0) + timedelta(hours=1)
        else:
            next_5 = next_5.replace(minute=next_5_minute_mark)

        time_to_5min = (next_5 - now).total_seconds()
        if time_to_5min <= 300:
            upcoming.append(("gear", get_countdown(next_5)))
            upcoming.append(("seed", get_countdown(next_5)))

        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        time_to_hour = (next_hour - now).total_seconds()
        if time_to_hour <= 300:
            upcoming.append(("honey", get_countdown(next_hour)))

        current_hour = now.hour
        next_7h_mark = ((current_hour // 7) + 1) * 7

        if next_7h_mark >= 24:
            next_7 = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1, hours=next_7h_mark - 24
            )
        else:
            next_7 = now.replace(hour=next_7h_mark, minute=0, second=0, microsecond=0)

        time_to_7h = (next_7 - now).total_seconds()
        if time_to_7h <= 300:
            upcoming.append(("cosmetic", get_countdown(next_7)))

    except Exception as e:
        logger.error(f"Error calculating upcoming restocks: {e}")

    return upcoming


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


def get_category_emoji(category):
    category_emojis = {
        "gear": "🛠️",
        "seed": "🌱",
        "egg": "🥚",
        "honey": "🍯",
        "cosmetic": "🎨",
    }
    return category_emojis.get(category, "📦")


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


def get_user_preferences(sender_id):
    if sender_id not in user_preferences:
        user_preferences[sender_id] = {
            "smart_notifications": True,
            "value_threshold": 0,
            "priority_categories": [],
            "notification_cooldown": 300,
            "show_price_trends": True,
            "compact_notifications": False,
            "alert_sound": True,
            "daily_summary": False,
            "auto_remove_purchased": False,
        }
        save_data("preferences")
    return user_preferences[sender_id]


def get_user_stats(sender_id):
    if sender_id not in user_favorite_stats:
        user_favorite_stats[sender_id] = {
            "notifications_sent": 0,
            "items_found": 0,
            "total_value_found": 0,
            "favorite_categories": {},
            "sessions_started": 0,
            "last_notification": None,
            "best_find_value": 0,
            "best_find_item": None,
        }
        save_data("favorite_stats")
    return user_favorite_stats[sender_id]


def update_user_stats(sender_id, action, data=None):
    stats = get_user_stats(sender_id)

    if action == "notification_sent":
        stats["notifications_sent"] += 1
        stats["last_notification"] = get_ph_time().isoformat()
    elif action == "item_found":
        stats["items_found"] += 1
        if data and "value" in data:
            stats["total_value_found"] += data["value"]
            if data["value"] > stats["best_find_value"]:
                stats["best_find_value"] = data["value"]
                stats["best_find_item"] = data.get("name", "Unknown")
        if data and "category" in data:
            category = data["category"]
            stats["favorite_categories"][category] = (
                stats["favorite_categories"].get(category, 0) + 1
            )
    elif action == "session_started":
        stats["sessions_started"] += 1

    save_data("favorite_stats")


def get_price_trend(item_name, category):
    key = f"{category}/{item_name}"
    if key not in price_history or len(price_history[key]) < 2:
        return "📊 No trend data"

    recent_prices = [entry["value"] for entry in price_history[key][-10:]]
    if len(recent_prices) < 2:
        return "📊 Insufficient data"

    first_half = recent_prices[: len(recent_prices) // 2]
    second_half = recent_prices[len(recent_prices) // 2 :]

    avg_first = statistics.mean(first_half)
    avg_second = statistics.mean(second_half)

    if avg_second > avg_first * 1.1:
        return "📈 Rising"
    elif avg_second < avg_first * 0.9:
        return "📉 Falling"
    else:
        return "📊 Stable"


def add_notification_to_history(sender_id, item_data):
    if sender_id not in user_notification_history:
        user_notification_history[sender_id] = []

    notification = {
        "timestamp": get_ph_time().isoformat(),
        "item": item_data,
        "value": item_data.get("value", 0),
    }

    user_notification_history[sender_id].append(notification)

    if len(user_notification_history[sender_id]) > 100:
        user_notification_history[sender_id] = user_notification_history[sender_id][
            -100:
        ]

    save_data("notifications")


def should_send_notification(sender_id, item):
    prefs = get_user_preferences(sender_id)

    if item["value"] < prefs["value_threshold"]:
        return False

    if (
        prefs["priority_categories"]
        and item["category"] not in prefs["priority_categories"]
    ):
        return False

    if sender_id in user_notification_history:
        last_notifications = user_notification_history[sender_id][-5:]
        for notif in last_notifications:
            if (
                notif["item"]["display_name"] == item["display_name"]
                and notif["item"]["category"] == item["category"]
            ):
                notif_time = datetime.fromisoformat(notif["timestamp"])
                if (get_ph_time() - notif_time).total_seconds() < prefs[
                    "notification_cooldown"
                ]:
                    return False

    return True


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

                if should_send_notification(sender_id, item):
                    tracked_in_stock.append(item)
                    update_user_stats(
                        sender_id,
                        "item_found",
                        {
                            "value": item["value"],
                            "name": item["display_name"],
                            "category": item["category"],
                        },
                    )
                    add_notification_to_history(sender_id, item)
                break

    return tracked_in_stock


def get_smart_recommendations(sender_id, stock_data):
    if sender_id not in user_tracked_items:
        return []

    all_items = get_all_items_from_stock(stock_data)
    tracked_categories = set(item["category"] for item in user_tracked_items[sender_id])

    recommendations = []
    for item in all_items:
        if (
            item["category"] in tracked_categories
            and item["value"] >= 1000
            and not any(
                normalize_item_name(tracked["item_name"])
                == normalize_item_name(item["display_name"])
                for tracked in user_tracked_items[sender_id]
            )
        ):
            recommendations.append(item)

    return sorted(recommendations, key=lambda x: x["value"], reverse=True)[:3]


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

        prefs = get_user_preferences(sender_id)

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
                upcoming = get_upcoming_restocks()

                if prefs["compact_notifications"]:
                    message = (
                        f"⭐ {len(tracked_in_stock)} favorite item(s) in stock!\n\n"
                    )

                    for item in tracked_in_stock:
                        emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                        rarity = ""
                        if item["value"] >= 10000:
                            rarity = " 💎"
                        elif item["value"] >= 1000:
                            rarity = " ⭐"
                        elif item["value"] >= 100:
                            rarity = " 🔥"

                        trend = ""
                        if prefs["show_price_trends"]:
                            trend = f" | {get_price_trend(item['display_name'], item['category'])}"

                        message += f"🔔 {emoji_part}{item['display_name']}: {format_value(item['value'])}{rarity}{trend}\n"

                    message += f"\n📊 Total value: {format_value(sum(item['value'] for item in tracked_in_stock))}"

                    if upcoming:
                        message += "\n\n⚡ UPCOMING RESTOCKS (< 5 min):\n"
                        for category, countdown in upcoming:
                            emoji = get_category_emoji(category)
                            message += f"{emoji} {category.title()}: {countdown}\n"

                else:
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
                        restock_time = category_restocks.get(
                            item["category"], "Unknown"
                        )

                        rarity = ""
                        if item["value"] >= 10000:
                            rarity = " 💎 Ultra Rare"
                        elif item["value"] >= 1000:
                            rarity = " ⭐ Rare"
                        elif item["value"] >= 100:
                            rarity = " 🔥 Uncommon"

                        trend = ""
                        if prefs["show_price_trends"]:
                            trend = f" | {get_price_trend(item['display_name'], item['category'])}"

                        message += f"🔔 {emoji_part}{item['display_name']}: {format_value(item['value'])}{rarity}\n"
                        message += f"   📦 {item['category'].title()} | ⏳ Restock: {restock_time}{trend}\n\n"

                    total_value = sum(item["value"] for item in tracked_in_stock)
                    message += f"💰 Total value found: {format_value(total_value)}\n\n"

                    weather_icon = weather_data.get("icon", "🌦️")
                    weather_current = weather_data.get("currentWeather", "Unknown")
                    weather_effect = weather_data.get("effectDescription", "No effect")
                    weather_bonus = weather_data.get("cropBonuses", "No bonus")

                    message += f"🌤️ Weather: {weather_icon} {weather_current}\n"
                    message += f"📌 Effect: {weather_effect}\n"
                    message += f"🪄 Bonus: {weather_bonus}"

                    if upcoming:
                        message += "\n\n⚡ UPCOMING RESTOCKS (< 5 min):\n"
                        for category, countdown in upcoming:
                            emoji = get_category_emoji(category)
                            message += f"🔥 {emoji} {category.title()}: {countdown}\n"

                if prefs["smart_notifications"]:
                    recommendations = get_smart_recommendations(sender_id, stock_data)
                    if recommendations:
                        message += f"\n\n💡 Smart Recommendations:\n"
                        for rec in recommendations:
                            emoji_part = f"{rec['emoji']} " if rec["emoji"] else ""
                            message += f"• {emoji_part}{rec['display_name']}: {format_value(rec['value'])}\n"
                        message += "\n💭 Consider adding these valuable items to your favorites!"

                if message != session.get("last_message"):
                    session["last_message"] = message
                    try:
                        send_message_func(sender_id, message)
                        update_user_stats(sender_id, "notification_sent")
                        logger.info(f"Sent gagstockfav update to {sender_id}")
                    except Exception as e:
                        logger.error(
                            f"Failed to send favorite message to {sender_id}: {e}"
                        )

        if sender_id in user_favorite_sessions:
            timer = threading.Timer(
                8.0, fetch_favorite_data, args=[sender_id, send_message_func]
            )
            timer.daemon = True
            timer.start()
            user_favorite_sessions[sender_id]["timer"] = timer
            logger.debug(f"Scheduled next favorite fetch for {sender_id} in 8 seconds")

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

    spam_check, spam_message = check_spam_protection(sender_id)
    if not spam_check:
        send_message_func(sender_id, spam_message)
        return

    load_all_data()

    if not args:
        cache_key = f"favhelp_{sender_id}"
        cached_response = get_cached_message(cache_key)
        if cached_response:
            send_message_func(sender_id, cached_response)
            return

        stats = get_user_stats(sender_id)
        prefs = get_user_preferences(sender_id)
        tracked_count = len(user_tracked_items.get(sender_id, []))

        upcoming = get_upcoming_restocks()
        upcoming_text = ""
        if upcoming:
            upcoming_text = "\n\n⚡ UPCOMING RESTOCKS (< 5 min):\n"
            for category, countdown in upcoming:
                emoji = get_category_emoji(category)
                upcoming_text += f"{emoji} {category.title()}: {countdown}\n"

        help_message = (
            "⭐ Gagstockfav — Smart Favorites Tracker\n\n"
            "🎯 Favorites Tracking:\n"
            "• 'gagstockfav on' - Start tracking only your favorite items\n"
            "• 'gagstockfav off' - Stop favorites tracking\n"
            "• 'gagstockfav smart' - Toggle smart notifications\n"
            "• 'gagstockfav compact' - Toggle compact mode\n\n"
            "⚙️ Advanced Settings:\n"
            "• 'gagstockfav threshold value' - Set minimum value to notify\n"
            "• 'gagstockfav cooldown seconds' - Set notification cooldown\n"
            "• 'gagstockfav priority category1,category2' - Set priority categories\n"
            "• 'gagstockfav trends' - Toggle price trend display\n\n"
            "📊 Analytics & History:\n"
            "• 'gagstockfav stats' - View your tracking statistics\n"
            "• 'gagstockfav history' - Recent notification history\n"
            "• 'gagstockfav summary' - Daily summary of findings\n"
            "• 'gagstockfav settings' - View/change all preferences\n\n"
            "🔍 Quick Actions:\n"
            "• 'gagstockfav test' - Test with current stock\n"
            "• 'gagstockfav recommend' - Get smart recommendations\n"
            "• 'gagstockfav restock' - Next restock times\n\n"
            f"📊 Your Status:\n"
            f"⭐ Tracking: {tracked_count} favorite items\n"
            f"🔔 Notifications sent: {stats.get('notifications_sent', 0)}\n"
            f"💎 Best find: {stats.get('best_find_item', 'None')} ({format_value(stats.get('best_find_value', 0))})\n"
            f"🎯 Smart mode: {'ON' if prefs['smart_notifications'] else 'OFF'}\n"
            f"📊 Compact mode: {'ON' if prefs['compact_notifications'] else 'OFF'}\n\n"
            "💡 This tracks only items from your favorites list and notifies\n"
            "when they appear in stock. Independent from 'gagstock on/off'.\n\n"
            "🔔 First add items to favorites:\n"
            "• 'gagstock add category/item_name'\n"
            "• 'gagstock list' to see your favorites\n\n"
            f"📋 Categories: {', '.join(get_available_categories())}\n"
            "🔍 Examples:\n"
            "   • 'gagstock add gear/ancient_shovel'\n"
            "   • 'gagstockfav on' (tracks only favorites)\n"
            "   • 'gagstockfav threshold 1000' (only notify for items ≥1000 value)"
            f"{upcoming_text}"
        )

        cache_message(cache_key, help_message)
        send_message_func(sender_id, help_message)
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

        update_user_stats(sender_id, "session_started")
        prefs = get_user_preferences(sender_id)
        tracked_count = len(user_tracked_items[sender_id])
        tracked_list = []
        for item in user_tracked_items[sender_id]:
            tracked_list.append(f"{item['category']}/{item['item_name']}")

        upcoming = get_upcoming_restocks()
        upcoming_text = ""
        if upcoming:
            upcoming_text = f"\n\n⚡ UPCOMING RESTOCKS (< 5 min):\n"
            for category, countdown in upcoming:
                emoji = get_category_emoji(category)
                upcoming_text += f"{emoji} {category.title()}: {countdown}\n"

        send_message_func(
            sender_id,
            f"⭐ Gagstockfav started! Tracking {tracked_count} favorite items.\n"
            f"🔔 You'll be notified only when your favorite items are in stock.\n\n"
            f"📋 Tracking: {', '.join(tracked_list[:3])}{'...' if tracked_count > 3 else ''}\n\n"
            f"🎯 Smart notifications: {'ON' if prefs['smart_notifications'] else 'OFF'}\n"
            f"📊 Compact mode: {'ON' if prefs['compact_notifications'] else 'OFF'}\n"
            f"💰 Value threshold: {format_value(prefs['value_threshold'])}\n"
            f"⏰ Cooldown: {prefs['notification_cooldown']}s\n"
            f"⚡ Update frequency: Every 8 seconds\n\n"
            f"💡 Use 'gagstockfav settings' to customize your experience."
            f"{upcoming_text}",
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

    elif action == "restock":
        cache_key = f"fav_restock_{sender_id}"
        cached_response = get_cached_message(cache_key)
        if cached_response:
            send_message_func(sender_id, cached_response)
            return

        restocks = get_next_restocks()
        upcoming = get_upcoming_restocks()

        message = "⏰ Next Restock Times:\n\n"

        for category in get_available_categories():
            emoji = get_category_emoji(category)
            restock_time = restocks.get(category, "Unknown")
            message += f"{emoji} {category.title()}: {restock_time}\n"

        if upcoming:
            message += "\n⚡ UPCOMING RESTOCKS (< 5 min):\n"
            for category, countdown in upcoming:
                emoji = get_category_emoji(category)
                message += f"🔥 {emoji} {category.title()}: {countdown}\n"

        message += (
            "\n💡 Restock Schedule:\n"
            "🥚 Eggs: Every 30 minutes\n"
            "🛠️ Gear & 🌱 Seeds: Every 5 minutes\n"
            "🍯 Honey: Every hour\n"
            "🎨 Cosmetics: Every 7 hours\n\n"
            "🔔 Use 'gagstockfav on' to get notified when your favorites are in stock!"
        )

        cache_message(cache_key, message)
        send_message_func(sender_id, message)
        return

    elif action == "smart":
        prefs = get_user_preferences(sender_id)
        prefs["smart_notifications"] = not prefs["smart_notifications"]
        save_data("preferences")

        status = "ON" if prefs["smart_notifications"] else "OFF"
        send_message_func(
            sender_id,
            f"🎯 Smart notifications: {status}\n"
            "💡 Smart mode provides item recommendations and enhanced analytics.",
        )
        return

    elif action == "compact":
        prefs = get_user_preferences(sender_id)
        prefs["compact_notifications"] = not prefs["compact_notifications"]
        save_data("preferences")

        status = "ON" if prefs["compact_notifications"] else "OFF"
        send_message_func(
            sender_id,
            f"📊 Compact notifications: {status}\n"
            "💡 Compact mode shows shorter, summarized notifications.",
        )
        return

    elif action == "trends":
        prefs = get_user_preferences(sender_id)
        prefs["show_price_trends"] = not prefs["show_price_trends"]
        save_data("preferences")

        status = "ON" if prefs["show_price_trends"] else "OFF"
        send_message_func(
            sender_id,
            f"📈 Price trends in notifications: {status}\n"
            "💡 Shows 📈📉📊 indicators for price movement patterns.",
        )
        return

    elif action == "threshold":
        if len(args) < 2:
            prefs = get_user_preferences(sender_id)
            send_message_func(
                sender_id,
                f"💰 Value Threshold Settings:\n\n"
                f"Current threshold: {format_value(prefs['value_threshold'])}\n\n"
                "💡 Usage: 'gagstockfav threshold value'\n"
                "🔍 Examples:\n"
                "   • 'gagstockfav threshold 0' (notify for all items)\n"
                "   • 'gagstockfav threshold 1000' (only notify for items ≥1000)\n"
                "   • 'gagstockfav threshold 5000' (only high-value items)\n\n"
                "This filters notifications to only show items above the specified value.",
            )
            return

        try:
            threshold = int(args[1])
            if threshold < 0:
                send_message_func(sender_id, "❌ Threshold must be 0 or positive")
                return
        except ValueError:
            send_message_func(sender_id, "❌ Threshold must be a number")
            return

        prefs = get_user_preferences(sender_id)
        prefs["value_threshold"] = threshold
        save_data("preferences")

        send_message_func(
            sender_id,
            f"💰 Value threshold set to: {format_value(threshold)}\n"
            "🔔 You'll only be notified for items with value ≥ this amount.",
        )
        return

    elif action == "cooldown":
        if len(args) < 2:
            prefs = get_user_preferences(sender_id)
            send_message_func(
                sender_id,
                f"⏰ Notification Cooldown Settings:\n\n"
                f"Current cooldown: {prefs['notification_cooldown']} seconds\n\n"
                "💡 Usage: 'gagstockfav cooldown seconds'\n"
                "🔍 Examples:\n"
                "   • 'gagstockfav cooldown 60' (1 minute)\n"
                "   • 'gagstockfav cooldown 300' (5 minutes)\n"
                "   • 'gagstockfav cooldown 900' (15 minutes)\n\n"
                "This prevents spam by limiting how often you get notified for the same item.",
            )
            return

        try:
            cooldown = int(args[1])
            if cooldown < 0:
                send_message_func(sender_id, "❌ Cooldown must be 0 or positive")
                return
        except ValueError:
            send_message_func(sender_id, "❌ Cooldown must be a number")
            return

        prefs = get_user_preferences(sender_id)
        prefs["notification_cooldown"] = cooldown
        save_data("preferences")

        minutes = cooldown // 60
        seconds = cooldown % 60
        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        send_message_func(
            sender_id,
            f"⏰ Notification cooldown set to: {time_str}\n"
            "🔔 Same items won't notify again within this timeframe.",
        )
        return

    elif action == "priority":
        if len(args) < 2:
            prefs = get_user_preferences(sender_id)
            current_priorities = prefs["priority_categories"]

            send_message_func(
                sender_id,
                f"🎯 Priority Categories Settings:\n\n"
                f"Current priorities: {', '.join(current_priorities) if current_priorities else 'All categories'}\n\n"
                "💡 Usage: 'gagstockfav priority category1,category2'\n"
                "💡 Use 'gagstockfav priority all' to reset\n\n"
                "🔍 Examples:\n"
                "   • 'gagstockfav priority gear,egg' (only gear and eggs)\n"
                "   • 'gagstockfav priority cosmetic' (only cosmetics)\n"
                "   • 'gagstockfav priority all' (all categories)\n\n"
                f"📋 Available: {', '.join(get_available_categories())}\n\n"
                "This limits notifications to only your priority categories.",
            )
            return

        priority_input = args[1].lower()
        if priority_input == "all":
            priorities = []
        else:
            priorities = [cat.strip() for cat in priority_input.split(",")]
            invalid_cats = [
                cat for cat in priorities if cat not in get_available_categories()
            ]
            if invalid_cats:
                send_message_func(
                    sender_id,
                    f"❌ Invalid categories: {', '.join(invalid_cats)}\n"
                    f"📋 Valid categories: {', '.join(get_available_categories())}",
                )
                return

        prefs = get_user_preferences(sender_id)
        prefs["priority_categories"] = priorities
        save_data("preferences")

        if priorities:
            send_message_func(
                sender_id,
                f"🎯 Priority categories set to: {', '.join(priorities)}\n"
                "🔔 You'll only get notifications for items in these categories.",
            )
        else:
            send_message_func(
                sender_id,
                "🎯 Priority categories reset - you'll get notifications for all categories.",
            )
        return

    elif action == "stats":
        stats = get_user_stats(sender_id)
        prefs = get_user_preferences(sender_id)
        tracked_count = len(user_tracked_items.get(sender_id, []))

        last_notification = stats.get("last_notification")
        if last_notification:
            try:
                last_notif_dt = datetime.fromisoformat(last_notification)
                last_notif_str = last_notif_dt.strftime("%Y-%m-%d %H:%M")
            except:
                last_notif_str = "Unknown"
        else:
            last_notif_str = "Never"

        avg_value = 0
        if stats["items_found"] > 0:
            avg_value = stats["total_value_found"] / stats["items_found"]

        favorite_category = "None"
        if stats["favorite_categories"]:
            favorite_category = max(
                stats["favorite_categories"], key=stats["favorite_categories"].get
            )

        command_usage_today = user_command_usage.get(sender_id, {})
        current_minute_window = int(time.time() // 60)
        today_usage = sum(
            count
            for window, count in command_usage_today.items()
            if window >= current_minute_window - 1440
        )

        send_message_func(
            sender_id,
            f"📊 Your Gagstockfav Statistics:\n\n"
            f"⭐ Items being tracked: {tracked_count}\n"
            f"🔔 Notifications sent: {stats['notifications_sent']}\n"
            f"📈 Commands today: {today_usage}\n"
            f"🎯 Items found in stock: {stats['items_found']}\n"
            f"💰 Total value found: {format_value(stats['total_value_found'])}\n"
            f"📈 Average item value: {format_value(avg_value)}\n"
            f"💎 Best find: {stats.get('best_find_item', 'None')} ({format_value(stats['best_find_value'])})\n"
            f"📡 Sessions started: {stats['sessions_started']}\n"
            f"❤️ Favorite category: {favorite_category}\n"
            f"🕐 Last notification: {last_notif_str}\n\n"
            f"⚙️ Current Settings:\n"
            f"💰 Value threshold: {format_value(prefs['value_threshold'])}\n"
            f"⏰ Cooldown: {prefs['notification_cooldown']}s\n"
            f"🎯 Smart mode: {'ON' if prefs['smart_notifications'] else 'OFF'}\n"
            f"📊 Compact mode: {'ON' if prefs['compact_notifications'] else 'OFF'}",
        )
        return

    elif action == "history":
        if (
            sender_id not in user_notification_history
            or not user_notification_history[sender_id]
        ):
            send_message_func(
                sender_id,
                "📊 No notification history yet.\n\n"
                "💡 Start tracking with 'gagstockfav on' to build your history!",
            )
            return

        history = user_notification_history[sender_id]
        recent_history = history[-10:]

        message = "📊 Recent Notification History:\n\n"

        total_value = 0
        for i, notification in enumerate(reversed(recent_history), 1):
            item = notification["item"]
            timestamp = datetime.fromisoformat(notification["timestamp"])
            time_str = timestamp.strftime("%m-%d %H:%M")

            emoji_part = f"{item['emoji']} " if item.get("emoji") else ""
            category_emoji = get_category_emoji(item["category"])

            total_value += item["value"]

            message += f"{i}. {time_str} | {category_emoji} {emoji_part}{item['display_name']}: {format_value(item['value'])}\n"

        message += f"\n📊 Last 10 notifications summary:\n"
        message += f"💰 Total value: {format_value(total_value)}\n"
        message += (
            f"📈 Average value: {format_value(total_value / len(recent_history))}\n"
        )
        message += f"🔔 Total notifications: {len(history)}"

        send_message_func(sender_id, message)
        return

    elif action == "summary":
        if (
            sender_id not in user_notification_history
            or not user_notification_history[sender_id]
        ):
            send_message_func(
                sender_id,
                "📊 No data for summary yet.\n\n"
                "💡 Start tracking to generate daily summaries!",
            )
            return

        now = get_ph_time()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        today_notifications = []
        for notification in user_notification_history[sender_id]:
            notif_time = datetime.fromisoformat(notification["timestamp"])
            if notif_time >= today_start:
                today_notifications.append(notification)

        if not today_notifications:
            send_message_func(
                sender_id,
                f"📊 Daily Summary for {now.strftime('%Y-%m-%d')}:\n\n"
                "🔔 No items found today.\n"
                "💡 Keep your favorites list updated for better results!",
            )
            return

        total_value = sum(notif["item"]["value"] for notif in today_notifications)
        categories = {}
        best_find = max(today_notifications, key=lambda x: x["item"]["value"])

        for notification in today_notifications:
            category = notification["item"]["category"]
            categories[category] = categories.get(category, 0) + 1

        message = f"📊 Daily Summary for {now.strftime('%Y-%m-%d')}:\n\n"
        message += f"🔔 Items found: {len(today_notifications)}\n"
        message += f"💰 Total value: {format_value(total_value)}\n"
        message += f"📈 Average value: {format_value(total_value / len(today_notifications))}\n"
        message += f"💎 Best find: {best_find['item']['display_name']} ({format_value(best_find['item']['value'])})\n\n"

        message += "📋 By category:\n"
        for category, count in categories.items():
            emoji = get_category_emoji(category)
            message += f"{emoji} {category.title()}: {count} item(s)\n"

        send_message_func(sender_id, message)
        return

    elif action == "settings":
        prefs = get_user_preferences(sender_id)
        priority_str = (
            ", ".join(prefs["priority_categories"])
            if prefs["priority_categories"]
            else "All"
        )
        cooldown_min = prefs["notification_cooldown"] // 60
        cooldown_sec = prefs["notification_cooldown"] % 60
        cooldown_str = (
            f"{cooldown_min}m {cooldown_sec}s"
            if cooldown_min > 0
            else f"{cooldown_sec}s"
        )

        send_message_func(
            sender_id,
            "⚙️ Your Gagstockfav Settings:\n\n"
            f"🎯 Smart notifications: {'ON' if prefs['smart_notifications'] else 'OFF'}\n"
            f"📊 Compact notifications: {'ON' if prefs['compact_notifications'] else 'OFF'}\n"
            f"📈 Show price trends: {'ON' if prefs['show_price_trends'] else 'OFF'}\n"
            f"💰 Value threshold: {format_value(prefs['value_threshold'])}\n"
            f"⏰ Notification cooldown: {cooldown_str}\n"
            f"🎯 Priority categories: {priority_str}\n"
            f"🔔 Alert sound: {'ON' if prefs['alert_sound'] else 'OFF'}\n"
            f"📅 Daily summary: {'ON' if prefs['daily_summary'] else 'OFF'}\n\n"
            "💡 Commands to change settings:\n"
            "• 'gagstockfav smart' - Toggle smart notifications\n"
            "• 'gagstockfav compact' - Toggle compact mode\n"
            "• 'gagstockfav trends' - Toggle price trends\n"
            "• 'gagstockfav threshold value' - Set value threshold\n"
            "• 'gagstockfav cooldown seconds' - Set cooldown time\n"
            "• 'gagstockfav priority categories' - Set priority categories",
        )
        return

    elif action == "test":
        if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
            send_message_func(
                sender_id,
                "⚠️ You need to add favorite items first to test.\n"
                "💡 Use 'gagstock add category/item_name' to add items.",
            )
            return

        cache_key = f"favtest_{sender_id}"
        cached_response = get_cached_message(cache_key)
        if cached_response:
            send_message_func(sender_id, cached_response)
            return

        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )

            if stock_response.status_code == 200:
                stock_data = stock_response.json()
                tracked_in_stock = check_tracked_items_in_stock(sender_id, stock_data)

                if tracked_in_stock:
                    message = f"🧪 Test Results - Found {len(tracked_in_stock)} favorite item(s):\n\n"
                    for item in tracked_in_stock:
                        emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                        trend = get_price_trend(item["display_name"], item["category"])
                        message += f"✅ {emoji_part}{item['display_name']}: {format_value(item['value'])} | {trend}\n"

                    total_value = sum(item["value"] for item in tracked_in_stock)
                    message += (
                        f"\n💰 Total value available: {format_value(total_value)}"
                    )
                else:
                    message = "🧪 Test Results:\n\n❌ None of your favorite items are currently in stock.\n💡 Keep tracking - items restock regularly!"

                cache_message(cache_key, message)
                send_message_func(sender_id, message)
            else:
                send_message_func(
                    sender_id, "❌ Failed to fetch stock data for testing."
                )
        except Exception as e:
            logger.error(f"Error in test command: {e}")
            send_message_func(sender_id, "❌ Error occurred during test.")
        return

    elif action == "recommend":
        cache_key = f"favrecommend_{sender_id}"
        cached_response = get_cached_message(cache_key)
        if cached_response:
            send_message_func(sender_id, cached_response)
            return

        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )

            if stock_response.status_code == 200:
                stock_data = stock_response.json()
                recommendations = get_smart_recommendations(sender_id, stock_data)

                if recommendations:
                    message = "💡 Smart Recommendations based on your preferences:\n\n"
                    for i, item in enumerate(recommendations, 1):
                        emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                        category_emoji = get_category_emoji(item["category"])
                        trend = get_price_trend(item["display_name"], item["category"])

                        rarity = ""
                        if item["value"] >= 10000:
                            rarity = " 💎"
                        elif item["value"] >= 1000:
                            rarity = " ⭐"
                        elif item["value"] >= 100:
                            rarity = " 🔥"

                        message += f"{i}. {category_emoji} {emoji_part}{item['display_name']}\n"
                        message += (
                            f"   💰 {format_value(item['value'])}{rarity} | {trend}\n\n"
                        )

                    message += "💡 Add to favorites: 'gagstock add category/item_name'"
                else:
                    message = "💡 No smart recommendations available right now.\n\n"
                    if (
                        sender_id not in user_tracked_items
                        or not user_tracked_items[sender_id]
                    ):
                        message += "Add some favorite items first to get better recommendations!"
                    else:
                        message += "Try expanding your favorite categories for more recommendations."

                cache_message(cache_key, message)
                send_message_func(sender_id, message)
            else:
                send_message_func(
                    sender_id, "❌ Failed to fetch stock data for recommendations."
                )
        except Exception as e:
            logger.error(f"Error in recommend command: {e}")
            send_message_func(
                sender_id, "❌ Error occurred while getting recommendations."
            )
        return

    else:
        send_message_func(
            sender_id,
            "❌ Unknown gagstockfav command.\n\n"
            "🔍 Popular commands:\n"
            "• 'gagstockfav on/off' - Start/stop tracking\n"
            "• 'gagstockfav settings' - View all settings\n"
            "• 'gagstockfav stats' - View your statistics\n"
            "• 'gagstockfav test' - Test with current stock\n"
            "• 'gagstockfav restock' - Next restock times\n\n"
            "💡 Use 'gagstockfav' without arguments for full help",
        )
