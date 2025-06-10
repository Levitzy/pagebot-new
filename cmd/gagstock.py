import threading
import requests
import json
import logging
from datetime import datetime, timedelta
import time
import os
import pickle
from collections import defaultdict, Counter
import statistics

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

active_sessions = {}
user_tracked_items = {}
user_price_alerts = {}
user_stats = {}
user_preferences = {}
price_history = defaultdict(list)
stock_analytics = defaultdict(
    lambda: {"last_seen": None, "frequency": 0, "avg_price": 0}
)

PH_OFFSET = 8
TRACKED_ITEMS_FILE = "gagstock_tracked_items.pkl"
PRICE_ALERTS_FILE = "gagstock_price_alerts.pkl"
USER_STATS_FILE = "gagstock_user_stats.pkl"
PRICE_HISTORY_FILE = "gagstock_price_history.pkl"
USER_PREFERENCES_FILE = "gagstock_user_preferences.pkl"


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


def save_tracked_items_to_file():
    try:
        with open(TRACKED_ITEMS_FILE, "wb") as f:
            pickle.dump(user_tracked_items, f)
        logger.debug(f"Saved tracked items for {len(user_tracked_items)} users")
    except Exception as e:
        logger.error(f"Error saving tracked items: {e}")


def load_user_preferences():
    global user_preferences
    try:
        if os.path.exists(USER_PREFERENCES_FILE):
            with open(USER_PREFERENCES_FILE, "rb") as f:
                user_preferences = pickle.load(f)
            logger.info(f"Loaded preferences for {len(user_preferences)} users")
        else:
            user_preferences = {}
            logger.info("No existing preferences file found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading preferences: {e}")
        user_preferences = {}


def save_user_preferences():
    try:
        with open(USER_PREFERENCES_FILE, "wb") as f:
            pickle.dump(user_preferences, f)
        logger.debug(f"Saved preferences for {len(user_preferences)} users")
    except Exception as e:
        logger.error(f"Error saving preferences: {e}")


def load_all_data():
    global user_tracked_items, user_price_alerts, user_stats, price_history, user_preferences

    load_tracked_items()
    load_user_preferences()

    try:
        if os.path.exists(PRICE_ALERTS_FILE):
            with open(PRICE_ALERTS_FILE, "rb") as f:
                user_price_alerts = pickle.load(f)
        else:
            user_price_alerts = {}
    except Exception as e:
        logger.error(f"Error loading price alerts: {e}")
        user_price_alerts = {}

    try:
        if os.path.exists(USER_STATS_FILE):
            with open(USER_STATS_FILE, "rb") as f:
                user_stats = pickle.load(f)
        else:
            user_stats = {}
    except Exception as e:
        logger.error(f"Error loading user stats: {e}")
        user_stats = {}

    try:
        if os.path.exists(PRICE_HISTORY_FILE):
            with open(PRICE_HISTORY_FILE, "rb") as f:
                price_history_data = pickle.load(f)
                price_history.update(price_history_data)
        else:
            price_history.clear()
    except Exception as e:
        logger.error(f"Error loading price history: {e}")
        price_history.clear()


def save_data(data_type):
    file_mapping = {
        "tracked_items": (TRACKED_ITEMS_FILE, user_tracked_items),
        "price_alerts": (PRICE_ALERTS_FILE, user_price_alerts),
        "stats": (USER_STATS_FILE, user_stats),
        "price_history": (PRICE_HISTORY_FILE, dict(price_history)),
        "preferences": (USER_PREFERENCES_FILE, user_preferences),
    }

    try:
        file_path, data = file_mapping[data_type]
        with open(file_path, "wb") as f:
            pickle.dump(data, f)
        logger.debug(f"Saved {data_type} to {file_path}")
    except Exception as e:
        logger.error(f"Error saving {data_type}: {e}")


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


def format_list(arr, show_rarity=False):
    if not arr:
        return "None."

    result = []
    for item in arr:
        try:
            emoji = item.get("emoji", "")
            name = item.get("name", "Unknown")
            value = item.get("value", 0)
            emoji_part = f"{emoji} " if emoji else ""

            rarity_indicator = ""
            if show_rarity and value > 0:
                if value >= 10000:
                    rarity_indicator = " 💎"
                elif value >= 1000:
                    rarity_indicator = " ⭐"
                elif value >= 100:
                    rarity_indicator = " 🔥"

            result.append(
                f"- {emoji_part}{name}: {format_value(value)}{rarity_indicator}"
            )
        except Exception as e:
            logger.warning(f"Error formatting item {item}: {e}")
            continue

    return "\n".join(result) if result else "None."


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


def update_price_history(item_name, category, value):
    key = f"{category}/{item_name}"
    now = get_ph_time()
    price_history[key].append({"timestamp": now.isoformat(), "value": value})

    if len(price_history[key]) > 100:
        price_history[key] = price_history[key][-100:]

    save_data("price_history")


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


def update_user_stats(sender_id, action):
    if sender_id not in user_stats:
        user_stats[sender_id] = {
            "commands_used": 0,
            "items_tracked": 0,
            "sessions_started": 0,
            "last_active": None,
            "favorite_category": None,
        }

    user_stats[sender_id]["commands_used"] += 1
    user_stats[sender_id]["last_active"] = get_ph_time().isoformat()

    if action == "track_item":
        user_stats[sender_id]["items_tracked"] += 1
    elif action == "start_session":
        user_stats[sender_id]["sessions_started"] += 1

    save_data("stats")


def get_user_preferences(sender_id):
    global user_preferences

    if user_preferences is None:
        user_preferences = {}

    if sender_id not in user_preferences:
        user_preferences[sender_id] = {
            "notifications": True,
            "show_rarity": True,
            "compact_mode": False,
            "price_alerts": True,
            "auto_track_expensive": False,
        }
        try:
            save_user_preferences()
        except Exception as e:
            logger.error(f"Error saving initial preferences for {sender_id}: {e}")

    return user_preferences[sender_id]


def set_user_preference(sender_id, key, value):
    global user_preferences

    if user_preferences is None:
        user_preferences = {}

    if sender_id not in user_preferences:
        get_user_preferences(sender_id)

    user_preferences[sender_id][key] = value

    try:
        save_user_preferences()
        return True
    except Exception as e:
        logger.error(f"Error saving preference {key} for {sender_id}: {e}")
        return False


def add_price_alert(sender_id, category, item_name, condition, value):
    if sender_id not in user_price_alerts:
        user_price_alerts[sender_id] = []

    alert = {
        "category": category,
        "item_name": item_name,
        "condition": condition,
        "value": value,
        "created": get_ph_time().isoformat(),
    }

    user_price_alerts[sender_id].append(alert)
    save_data("price_alerts")
    return True


def check_price_alerts(sender_id, stock_data):
    if sender_id not in user_price_alerts:
        return []

    triggered_alerts = []
    all_items = get_all_items_from_stock(stock_data)

    for alert in user_price_alerts[sender_id]:
        for item in all_items:
            if (
                normalize_item_name(item["display_name"])
                == normalize_item_name(alert["item_name"])
                and item["category"] == alert["category"]
            ):

                item_value = item["value"]
                alert_value = alert["value"]
                condition = alert["condition"]

                if (
                    (condition == "above" and item_value > alert_value)
                    or (condition == "below" and item_value < alert_value)
                    or (condition == "equals" and item_value == alert_value)
                ):

                    triggered_alerts.append({"alert": alert, "item": item})

    return triggered_alerts


def parse_tracked_items(items_string):
    items = []
    if "|" in items_string:
        parts = items_string.split("|")
    else:
        parts = [items_string]

    for part in parts:
        part = part.strip()
        if "/" in part:
            category, item_name = part.split("/", 1)
            category = category.lower().strip()
            item_name = item_name.strip()

            if category in get_available_categories():
                items.append({"category": category, "item_name": item_name})

    return items


def save_tracked_items(sender_id, items):
    global user_tracked_items

    if sender_id not in user_tracked_items:
        user_tracked_items[sender_id] = []

    added_count = 0
    for item in items:
        existing_item = next(
            (
                x
                for x in user_tracked_items[sender_id]
                if x["category"] == item["category"]
                and normalize_item_name(x["item_name"])
                == normalize_item_name(item["item_name"])
            ),
            None,
        )

        if not existing_item:
            user_tracked_items[sender_id].append(item)
            added_count += 1
            update_user_stats(sender_id, "track_item")
            logger.info(
                f"Added tracked item for {sender_id}: {item['category']}/{item['item_name']}"
            )

    save_tracked_items_to_file()
    return added_count


def add_tracked_items(sender_id, items_string):
    items = parse_tracked_items(items_string)

    if not items:
        return (
            False,
            "❌ Invalid format. Use: category/item_name or category/item1|category/item2",
        )

    valid_items = []
    invalid_categories = []
    duplicate_items = []

    if sender_id not in user_tracked_items:
        user_tracked_items[sender_id] = []

    for item in items:
        if item["category"] not in get_available_categories():
            invalid_categories.append(item["category"])
        else:
            existing_item = next(
                (
                    x
                    for x in user_tracked_items[sender_id]
                    if x["category"] == item["category"]
                    and normalize_item_name(x["item_name"])
                    == normalize_item_name(item["item_name"])
                ),
                None,
            )

            if existing_item:
                duplicate_items.append(f"{item['category']}/{item['item_name']}")
            else:
                valid_items.append(item)

    if invalid_categories:
        return (
            False,
            f"❌ Invalid categories: {', '.join(invalid_categories)}\n📋 Valid categories: {', '.join(get_available_categories())}",
        )

    if not valid_items and duplicate_items:
        return False, f"❌ Items already tracked: {', '.join(duplicate_items)}"

    added_count = save_tracked_items(sender_id, valid_items)

    message_parts = []

    if added_count > 0:
        if added_count == 1:
            item = valid_items[0]
            category_emoji = get_category_emoji(item["category"])
            message_parts.append(
                f"✅ Added '{item['item_name']}' to favorites list!\n{category_emoji} Category: {item['category'].title()}"
            )
        else:
            message_parts.append(f"✅ Added {added_count} items to favorites list:")
            for item in valid_items:
                category_emoji = get_category_emoji(item["category"])
                message_parts.append(
                    f"{category_emoji} {item['category']}/{item['item_name']}"
                )

        message_parts.append(
            "🔔 Use 'gagstockfav on' to get notified when these items are in stock."
        )

    if duplicate_items:
        message_parts.append(f"⚠️ Already tracking: {', '.join(duplicate_items)}")

    return True, "\n".join(message_parts)


def remove_tracked_item(sender_id, item_string):
    if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
        return False, "❌ You don't have any favorite items to remove."

    if "/" not in item_string:
        return False, "❌ Please use format: category/item_name"

    category, item_name = item_string.split("/", 1)
    category = category.lower().strip()
    item_name = item_name.strip()

    item_name_normalized = normalize_item_name(item_name)

    for i, tracked_item in enumerate(user_tracked_items[sender_id]):
        if (
            tracked_item["category"] == category
            and normalize_item_name(tracked_item["item_name"]) == item_name_normalized
        ):
            removed_item = user_tracked_items[sender_id].pop(i)
            save_data("tracked_items")
            logger.info(
                f"Removed tracked item for {sender_id}: {removed_item['category']}/{removed_item['item_name']}"
            )
            return (
                True,
                f"✅ Removed '{removed_item['category']}/{removed_item['item_name']}' from favorites list.",
            )

    return False, f"❌ '{category}/{item_name}' not found in your favorites list."


def list_tracked_items(sender_id):
    if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
        return (
            "❌ You don't have any favorite items.\n"
            "💡 Add items with: 'gagstock category/item_name'\n"
            f"📋 Categories: {', '.join(get_available_categories())}"
        )

    tracked_by_category = {}
    for item in user_tracked_items[sender_id]:
        category = item["category"]
        if category not in tracked_by_category:
            tracked_by_category[category] = []
        tracked_by_category[category].append(item["item_name"])

    message = "⭐ Your Favorite Items:\n\n"

    for category in get_available_categories():
        if category in tracked_by_category:
            emoji = get_category_emoji(category)
            message += f"{emoji} {category.title()}:\n"
            for item in tracked_by_category[category]:
                message += f"   • {item}\n"
            message += "\n"

    session_status = ""
    if sender_id in active_sessions:
        session_status = f"📡 Gagstock: ON (all stocks)\n"
    else:
        session_status = "📴 Gagstock: OFF\n"

    alerts_count = len(user_price_alerts.get(sender_id, []))
    stats = user_stats.get(sender_id, {})

    message += f"📊 Total: {len(user_tracked_items[sender_id])} favorite item(s)\n"
    message += f"🚨 Price alerts: {alerts_count}\n"
    message += f"📈 Commands used: {stats.get('commands_used', 0)}\n"
    message += session_status
    message += "💡 Remove with: 'gagstock remove category/item_name'\n"
    message += "💡 Track favorites: 'gagstockfav on'\n"
    message += "💡 Set price alert: 'gagstock alert category/item above/below value'"
    return message


def clear_tracked_items(sender_id):
    if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
        return "❌ You don't have any favorite items to clear."

    count = len(user_tracked_items[sender_id])
    user_tracked_items[sender_id] = []
    save_data("tracked_items")
    logger.info(f"Cleared {count} tracked items for {sender_id}")
    return f"✅ Cleared {count} favorite item(s) successfully."


def cleanup_session(sender_id):
    if sender_id in active_sessions:
        session = active_sessions[sender_id]
        timer = session.get("timer")
        if timer:
            timer.cancel()
        del active_sessions[sender_id]
        logger.info(f"Cleaned up gagstock session for {sender_id}")


def get_market_summary(stock_data):
    all_items = get_all_items_from_stock(stock_data)
    if not all_items:
        return "📊 Market Summary: No data available"

    values = [item["value"] for item in all_items if item["value"] > 0]
    if not values:
        return "📊 Market Summary: No valuable items in stock"

    total_items = len(all_items)
    avg_value = statistics.mean(values)
    max_item = max(all_items, key=lambda x: x["value"])
    min_item = min(
        [item for item in all_items if item["value"] > 0], key=lambda x: x["value"]
    )

    category_counts = Counter(item["category"] for item in all_items)
    most_stocked = category_counts.most_common(1)[0]

    summary = (
        f"📊 Market Summary:\n"
        f"📦 Total items: {total_items}\n"
        f"💰 Avg value: {format_value(avg_value)}\n"
        f"💎 Most valuable: {max_item['display_name']} ({format_value(max_item['value'])})\n"
        f"💵 Cheapest: {min_item['display_name']} ({format_value(min_item['value'])})\n"
        f"📈 Most stocked: {most_stocked[0]} ({most_stocked[1]} items)"
    )

    return summary


def fetch_all_data(sender_id, send_message_func):
    if sender_id not in active_sessions:
        logger.info(f"Session {sender_id} no longer active, stopping fetch_all_data")
        return

    try:
        logger.debug(f"Fetching data for gagstock session {sender_id}")

        headers = {"User-Agent": "GagStock-Bot/1.0"}

        try:
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Stock API request failed: {e}")
            raise

        try:
            weather_response = requests.get(
                "https://growagardenstock.com/api/stock/weather",
                timeout=15,
                headers=headers,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Weather API request failed: {e}")
            raise

        if stock_response.status_code != 200:
            logger.error(
                f"Stock API error: {stock_response.status_code} - {stock_response.text}"
            )
            raise requests.RequestException(
                f"Stock API returned {stock_response.status_code}"
            )

        if weather_response.status_code != 200:
            logger.error(
                f"Weather API error: {weather_response.status_code} - {weather_response.text}"
            )
            raise requests.RequestException(
                f"Weather API returned {weather_response.status_code}"
            )

        try:
            stock_data = stock_response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse stock data JSON: {e}")
            raise

        try:
            weather_data = weather_response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse weather data JSON: {e}")
            raise

        for item in get_all_items_from_stock(stock_data):
            update_price_history(item["display_name"], item["category"], item["value"])

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

        session = active_sessions.get(sender_id)
        if not session:
            logger.info(f"Session {sender_id} was removed during fetch")
            return

        user_prefs = get_user_preferences(sender_id)

        if combined_key == session.get("last_combined_key"):
            logger.debug(f"No changes detected for {sender_id}, scheduling next check")
        else:
            logger.info(f"Data changed for {sender_id}, sending update")
            session["last_combined_key"] = combined_key

            restocks = get_next_restocks()

            gear_list = format_list(
                stock_data.get("gear", []), user_prefs["show_rarity"]
            )
            seed_list = format_list(
                stock_data.get("seed", []), user_prefs["show_rarity"]
            )
            egg_list = format_list(stock_data.get("egg", []), user_prefs["show_rarity"])
            cosmetic_list = format_list(
                stock_data.get("cosmetic", []), user_prefs["show_rarity"]
            )
            honey_list = format_list(
                stock_data.get("honey", []), user_prefs["show_rarity"]
            )

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

            if user_prefs["compact_mode"]:
                message = (
                    f"🌾 GAG Stock Update\n\n"
                    f"🛠️ Gear ({restocks['gear']}): {len(stock_data.get('gear', []))} items\n"
                    f"🌱 Seeds ({restocks['seed']}): {len(stock_data.get('seed', []))} items\n"
                    f"🥚 Eggs ({restocks['egg']}): {len(stock_data.get('egg', []))} items\n"
                    f"🎨 Cosmetic ({restocks['cosmetic']}): {len(stock_data.get('cosmetic', []))} items\n"
                    f"🍯 Honey ({restocks['honey']}): {len(stock_data.get('honey', []))} items\n\n"
                    f"{weather_details}\n\n"
                    f"{get_market_summary(stock_data)}"
                )
            else:
                message = (
                    f"🌾 Grow A Garden — Full Stock Tracker\n\n"
                    f"🛠️ Gear:\n{gear_list}\n⏳ Restock in: {restocks['gear']}\n\n"
                    f"🌱 Seeds:\n{seed_list}\n⏳ Restock in: {restocks['seed']}\n\n"
                    f"🥚 Eggs:\n{egg_list}\n⏳ Restock in: {restocks['egg']}\n\n"
                    f"🎨 Cosmetic:\n{cosmetic_list}\n⏳ Restock in: {restocks['cosmetic']}\n\n"
                    f"🍯 Honey:\n{honey_list}\n⏳ Restock in: {restocks['honey']}\n\n"
                    f"{weather_details}\n\n"
                    f"{get_market_summary(stock_data)}"
                )

            triggered_alerts = check_price_alerts(sender_id, stock_data)
            if triggered_alerts and user_prefs["price_alerts"]:
                alert_msg = "\n\n🚨 PRICE ALERTS:\n"
                for alert_data in triggered_alerts:
                    alert = alert_data["alert"]
                    item = alert_data["item"]
                    alert_msg += f"• {item['display_name']}: {format_value(item['value'])} ({alert['condition']} {format_value(alert['value'])})\n"
                message += alert_msg

            if message != session.get("last_message"):
                session["last_message"] = message
                try:
                    send_message_func(sender_id, message)
                    logger.info(f"Sent gagstock update to {sender_id}")
                except Exception as e:
                    logger.error(f"Failed to send message to {sender_id}: {e}")

        if sender_id in active_sessions:
            timer = threading.Timer(
                10.0, fetch_all_data, args=[sender_id, send_message_func]
            )
            timer.daemon = True
            timer.start()
            active_sessions[sender_id]["timer"] = timer
            logger.debug(f"Scheduled next fetch for {sender_id} in 10 seconds")

    except requests.Timeout:
        logger.error(f"Timeout fetching data for {sender_id}")
        if sender_id in active_sessions:
            timer = threading.Timer(
                30.0, fetch_all_data, args=[sender_id, send_message_func]
            )
            timer.daemon = True
            timer.start()
            active_sessions[sender_id]["timer"] = timer

    except requests.RequestException as e:
        logger.error(f"Network error in gagstock for {sender_id}: {e}")
        if sender_id in active_sessions:
            try:
                send_message_func(
                    sender_id,
                    "⚠️ Stock API temporarily unavailable\nRetrying in 30 seconds...",
                )
            except:
                pass
            timer = threading.Timer(
                30.0, fetch_all_data, args=[sender_id, send_message_func]
            )
            timer.daemon = True
            timer.start()
            active_sessions[sender_id]["timer"] = timer

    except Exception as e:
        logger.error(f"Unexpected error in gagstock for {sender_id}: {e}")
        if sender_id in active_sessions:
            try:
                send_message_func(
                    sender_id,
                    "❌ Unexpected error occurred\nStopping tracker. Use 'gagstock on' to restart.",
                )
            except:
                pass
        cleanup_session(sender_id)


def execute(sender_id, args, context):
    send_message_func = context["send_message"]

    # Initialize data first
    try:
        load_all_data()
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        # Continue with empty data structures
        global user_tracked_items, user_price_alerts, user_stats, price_history, user_preferences
        if "user_tracked_items" not in globals():
            user_tracked_items = {}
        if "user_price_alerts" not in globals():
            user_price_alerts = {}
        if "user_stats" not in globals():
            user_stats = {}
        if "price_history" not in globals():
            price_history = defaultdict(list)
        if "user_preferences" not in globals():
            user_preferences = {}

    update_user_stats(sender_id, "command")

    if not args:
        stats = user_stats.get(sender_id, {})
        tracked_count = len(user_tracked_items.get(sender_id, []))
        alerts_count = len(user_price_alerts.get(sender_id, []))

        send_message_func(
            sender_id,
            "🌾 Gagstock — Advanced Stock Tracker\n\n"
            "📊 Full Stock Tracking:\n"
            "• 'gagstock on' - Track ALL stock changes\n"
            "• 'gagstock off' - Stop full stock tracking\n"
            "• 'gagstock compact' - Toggle compact mode\n\n"
            "⭐ Favorites Management:\n"
            "• 'gagstock category/item_name' - Add item to favorites\n"
            "• 'gagstock cat1/item1|cat2/item2' - Add multiple items\n"
            "• 'gagstock add category/item_name' - Add item to favorites\n"
            "• 'gagstock remove category/item_name' - Remove from favorites\n"
            "• 'gagstock list' - Show your favorite items\n"
            "• 'gagstock clear' - Clear all favorite items\n\n"
            "🚨 Price Alerts:\n"
            "• 'gagstock alert category/item above/below value' - Set price alert\n"
            "• 'gagstock alerts' - View your price alerts\n"
            "• 'gagstock removealert ID' - Remove price alert\n\n"
            "🔍 Stock Information:\n"
            "• 'gagstock stock' - Show current stock by category\n"
            "• 'gagstock search [item_name]' - Search for items\n"
            "• 'gagstock trends category/item' - Show price trends\n"
            "• 'gagstock market' - Market analysis\n"
            "• 'gagstock top' - Most valuable items\n\n"
            "⚙️ Settings:\n"
            "• 'gagstock settings' - View/change preferences\n"
            "• 'gagstock stats' - Your usage statistics\n\n"
            f"📊 Your Stats: {tracked_count} favorites | {alerts_count} alerts | {stats.get('commands_used', 0)} commands used\n\n"
            f"📋 Categories: {', '.join(get_available_categories())}\n"
            "💡 Examples:\n"
            "   • 'gagstock gear/ancient_shovel' (adds to favorites)\n"
            "   • 'gagstock alert egg/legendary above 5000' (price alert)\n"
            "   • 'gagstock on' (tracks ALL items)\n"
            "   • 'gagstockfav on' (tracks only your favorites)",
        )
        return

    action = args[0].lower()

    if action == "off":
        if sender_id in active_sessions:
            cleanup_session(sender_id)
            send_message_func(sender_id, "🛑 Gagstock tracking stopped (all stocks).")
        else:
            send_message_func(sender_id, "⚠️ You don't have an active gagstock session.")
        return

    elif action == "on":
        if sender_id in active_sessions:
            send_message_func(
                sender_id,
                "📡 Gagstock is already tracking all stocks!\n"
                "💡 Use 'gagstock off' to stop first.",
            )
            return

        update_user_stats(sender_id, "start_session")
        prefs = get_user_preferences(sender_id)

        send_message_func(
            sender_id,
            "✅ Gagstock started! Tracking ALL stock changes.\n"
            "🔔 You'll be notified when any stock or weather changes.\n"
            f"📊 Mode: {'Compact' if prefs['compact_mode'] else 'Detailed'}\n"
            f"🎯 Rarity indicators: {'ON' if prefs['show_rarity'] else 'OFF'}\n"
            f"🚨 Price alerts: {'ON' if prefs['price_alerts'] else 'OFF'}\n\n"
            "💡 For favorites-only tracking, use: 'gagstockfav on'\n"
            "⚙️ Change settings with: 'gagstock settings'",
        )

        active_sessions[sender_id] = {
            "timer": None,
            "last_combined_key": None,
            "last_message": "",
        }

        logger.info(f"Started full gagstock session for {sender_id}")
        fetch_all_data(sender_id, send_message_func)
        return

    elif action == "compact":
        try:
            logger.info(f"Compact command called by {sender_id}")

            # Ensure preferences are loaded
            load_user_preferences()

            # Get current preferences
            prefs = get_user_preferences(sender_id)
            logger.info(
                f"Current compact mode for {sender_id}: {prefs.get('compact_mode', False)}"
            )

            # Toggle compact mode
            new_compact_mode = not prefs.get("compact_mode", False)

            # Save the new preference
            if set_user_preference(sender_id, "compact_mode", new_compact_mode):
                mode = "Compact" if new_compact_mode else "Detailed"
                send_message_func(
                    sender_id,
                    f"⚙️ Display mode switched to: {mode}\n"
                    "💡 This affects how stock updates are shown when tracking is active.",
                )
                logger.info(
                    f"Successfully changed compact mode for {sender_id} to {new_compact_mode}"
                )
            else:
                send_message_func(
                    sender_id,
                    "⚠️ Setting saved but may not persist. Display mode changed for this session.",
                )
        except Exception as e:
            logger.error(
                f"Error in compact command for {sender_id}: {str(e)}", exc_info=True
            )
            send_message_func(
                sender_id,
                f"❌ Error: {str(e)}\n"
                "💡 Try using 'gagstock settings' to check if preferences are working.",
            )
        return

    elif action == "settings":
        try:
            load_all_data()
            prefs = get_user_preferences(sender_id)
            send_message_func(
                sender_id,
                "⚙️ Your Gagstock Settings:\n\n"
                f"📊 Compact mode: {'ON' if prefs['compact_mode'] else 'OFF'}\n"
                f"🎯 Show rarity: {'ON' if prefs['show_rarity'] else 'OFF'}\n"
                f"🔔 Notifications: {'ON' if prefs['notifications'] else 'OFF'}\n"
                f"🚨 Price alerts: {'ON' if prefs['price_alerts'] else 'OFF'}\n"
                f"💎 Auto-track expensive: {'ON' if prefs['auto_track_expensive'] else 'OFF'}\n\n"
                "💡 Commands to change settings:\n"
                "• 'gagstock compact' - Toggle compact mode\n"
                "• 'gagstock rarity' - Toggle rarity indicators\n"
                "• 'gagstock notifications' - Toggle notifications\n"
                "• 'gagstock alertsetting' - Toggle price alert notifications",
            )
        except Exception as e:
            logger.error(f"Error in settings command for {sender_id}: {e}")
            send_message_func(
                sender_id, "❌ Error occurred while loading settings. Please try again."
            )
        return

    elif action == "rarity":
        try:
            load_all_data()
            prefs = get_user_preferences(sender_id)
            prefs["show_rarity"] = not prefs["show_rarity"]
            user_preferences[sender_id] = prefs
            save_data("preferences")

            status = "ON" if prefs["show_rarity"] else "OFF"
            send_message_func(
                sender_id,
                f"🎯 Rarity indicators: {status}\n"
                "💡 This shows 💎/⭐/🔥 icons next to valuable items.",
            )
        except Exception as e:
            logger.error(f"Error in rarity command for {sender_id}: {e}")
            send_message_func(
                sender_id,
                "❌ Error occurred while changing rarity setting. Please try again.",
            )
        return

    elif action == "notifications":
        try:
            load_all_data()
            prefs = get_user_preferences(sender_id)
            prefs["notifications"] = not prefs["notifications"]
            user_preferences[sender_id] = prefs
            save_data("preferences")

            status = "ON" if prefs["notifications"] else "OFF"
            send_message_func(sender_id, f"🔔 Notifications: {status}")
        except Exception as e:
            logger.error(f"Error in notifications command for {sender_id}: {e}")
            send_message_func(
                sender_id,
                "❌ Error occurred while changing notification setting. Please try again.",
            )
        return

    elif action == "alertsetting":
        try:
            load_all_data()
            prefs = get_user_preferences(sender_id)
            prefs["price_alerts"] = not prefs["price_alerts"]
            user_preferences[sender_id] = prefs
            save_data("preferences")

            status = "ON" if prefs["price_alerts"] else "OFF"
            send_message_func(sender_id, f"🚨 Price alert notifications: {status}")
        except Exception as e:
            logger.error(f"Error in alertsetting command for {sender_id}: {e}")
            send_message_func(
                sender_id,
                "❌ Error occurred while changing alert setting. Please try again.",
            )
        return

    elif action == "stats":
        stats = user_stats.get(sender_id, {})
        tracked_count = len(user_tracked_items.get(sender_id, []))
        alerts_count = len(user_price_alerts.get(sender_id, []))

        last_active = stats.get("last_active")
        if last_active:
            try:
                last_active_dt = datetime.fromisoformat(last_active)
                last_active_str = last_active_dt.strftime("%Y-%m-%d %H:%M")
            except:
                last_active_str = "Unknown"
        else:
            last_active_str = "Never"

        send_message_func(
            sender_id,
            f"📊 Your Gagstock Statistics:\n\n"
            f"🎯 Commands used: {stats.get('commands_used', 0)}\n"
            f"⭐ Items tracked: {tracked_count}\n"
            f"🚨 Price alerts: {alerts_count}\n"
            f"📡 Sessions started: {stats.get('sessions_started', 0)}\n"
            f"🕐 Last active: {last_active_str}\n"
            f"❤️ Favorite category: {stats.get('favorite_category', 'None')}\n\n"
            "💡 Keep using Gagstock to unlock more features!",
        )
        return

    elif action == "alert":
        if len(args) < 3:
            send_message_func(
                sender_id,
                "🚨 Price Alert Setup:\n\n"
                "💡 Format: 'gagstock alert category/item condition value'\n\n"
                "📋 Conditions:\n"
                "• above - Alert when price goes above value\n"
                "• below - Alert when price drops below value\n"
                "• equals - Alert when price equals value\n\n"
                "🔍 Examples:\n"
                "• 'gagstock alert gear/ancient_shovel above 1000'\n"
                "• 'gagstock alert egg/legendary below 500'\n"
                "• 'gagstock alert honey/royal_jelly equals 750'",
            )
            return

        if "/" not in args[1]:
            send_message_func(sender_id, "❌ Use format: category/item_name")
            return

        category, item_name = args[1].split("/", 1)
        category = category.lower().strip()
        condition = args[2].lower().strip()

        try:
            value = int(args[3]) if len(args) > 3 else 0
        except ValueError:
            send_message_func(sender_id, "❌ Alert value must be a number")
            return

        if category not in get_available_categories():
            send_message_func(
                sender_id,
                f"❌ Invalid category: {category}\n📋 Valid categories: {', '.join(get_available_categories())}",
            )
            return

        if condition not in ["above", "below", "equals"]:
            send_message_func(
                sender_id, "❌ Condition must be: above, below, or equals"
            )
            return

        if add_price_alert(sender_id, category, item_name, condition, value):
            emoji = get_category_emoji(category)
            send_message_func(
                sender_id,
                f"🚨 Price alert created!\n"
                f"{emoji} Item: {category}/{item_name}\n"
                f"📊 Condition: {condition} {format_value(value)}\n"
                f"🔔 You'll be notified when this condition is met.\n\n"
                f"💡 View all alerts: 'gagstock alerts'",
            )
        return

    elif action == "alerts":
        if sender_id not in user_price_alerts or not user_price_alerts[sender_id]:
            send_message_func(
                sender_id,
                "🚨 You don't have any price alerts set.\n\n"
                "💡 Create one with: 'gagstock alert category/item above/below value'\n"
                "🔍 Example: 'gagstock alert gear/ancient_shovel above 1000'",
            )
            return

        message = "🚨 Your Price Alerts:\n\n"
        for i, alert in enumerate(user_price_alerts[sender_id]):
            emoji = get_category_emoji(alert["category"])
            message += f"{i+1}. {emoji} {alert['category']}/{alert['item_name']}\n"
            message += f"   📊 {alert['condition']} {format_value(alert['value'])}\n\n"

        message += f"📊 Total: {len(user_price_alerts[sender_id])} alert(s)\n"
        message += "💡 Remove with: 'gagstock removealert ID'"
        send_message_func(sender_id, message)
        return

    elif action == "removealert":
        if len(args) < 2:
            send_message_func(sender_id, "💡 Usage: 'gagstock removealert ID'")
            return

        try:
            alert_id = int(args[1]) - 1
        except ValueError:
            send_message_func(sender_id, "❌ Alert ID must be a number")
            return

        if (
            sender_id not in user_price_alerts
            or not user_price_alerts[sender_id]
            or alert_id < 0
            or alert_id >= len(user_price_alerts[sender_id])
        ):
            send_message_func(sender_id, "❌ Invalid alert ID")
            return

        removed_alert = user_price_alerts[sender_id].pop(alert_id)
        save_data("price_alerts")

        send_message_func(
            sender_id,
            f"✅ Removed price alert:\n"
            f"{get_category_emoji(removed_alert['category'])} {removed_alert['category']}/{removed_alert['item_name']} "
            f"{removed_alert['condition']} {format_value(removed_alert['value'])}",
        )
        return

    elif action == "trends":
        if len(args) < 2:
            send_message_func(
                sender_id,
                "📈 Price Trends:\n\n"
                "💡 Usage: 'gagstock trends category/item_name'\n"
                "🔍 Example: 'gagstock trends gear/ancient_shovel'\n\n"
                "This shows recent price movement patterns.",
            )
            return

        if "/" not in args[1]:
            send_message_func(sender_id, "❌ Use format: category/item_name")
            return

        category, item_name = args[1].split("/", 1)
        category = category.lower().strip()

        trend = get_price_trend(item_name, category)
        key = f"{category}/{item_name}"

        if key in price_history and price_history[key]:
            recent_prices = [entry["value"] for entry in price_history[key][-10:]]
            if recent_prices:
                min_price = min(recent_prices)
                max_price = max(recent_prices)
                avg_price = statistics.mean(recent_prices)

                send_message_func(
                    sender_id,
                    f"📈 Price Trends for {category}/{item_name}:\n\n"
                    f"📊 Trend: {trend}\n"
                    f"💰 Current avg: {format_value(avg_price)}\n"
                    f"📉 Recent low: {format_value(min_price)}\n"
                    f"📈 Recent high: {format_value(max_price)}\n"
                    f"📋 Data points: {len(price_history[key])}\n\n"
                    f"💡 Set price alert: 'gagstock alert {category}/{item_name} above/below value'",
                )
            else:
                send_message_func(
                    sender_id, f"📊 No price data available for {category}/{item_name}"
                )
        else:
            send_message_func(
                sender_id, f"📊 No price history found for {category}/{item_name}"
            )
        return

    elif action == "market":
        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )

            if stock_response.status_code == 200:
                stock_data = stock_response.json()
                market_summary = get_market_summary(stock_data)

                all_items = get_all_items_from_stock(stock_data)
                category_analysis = {}

                for category in get_available_categories():
                    cat_items = [
                        item for item in all_items if item["category"] == category
                    ]
                    if cat_items:
                        values = [
                            item["value"] for item in cat_items if item["value"] > 0
                        ]
                        if values:
                            category_analysis[category] = {
                                "count": len(cat_items),
                                "avg_value": statistics.mean(values),
                                "max_value": max(values),
                                "total_value": sum(values),
                            }

                message = f"{market_summary}\n\n📊 Category Analysis:\n\n"

                for category, data in category_analysis.items():
                    emoji = get_category_emoji(category)
                    message += f"{emoji} {category.title()}:\n"
                    message += f"   📦 Items: {data['count']}\n"
                    message += f"   💰 Avg: {format_value(data['avg_value'])}\n"
                    message += f"   💎 Max: {format_value(data['max_value'])}\n"
                    message += f"   💵 Total: {format_value(data['total_value'])}\n\n"

                send_message_func(sender_id, message)
            else:
                send_message_func(sender_id, "❌ Failed to fetch market data")
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            send_message_func(
                sender_id, "❌ Error occurred while fetching market data."
            )
        return

    elif action == "top":
        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )

            if stock_response.status_code == 200:
                stock_data = stock_response.json()
                all_items = get_all_items_from_stock(stock_data)

                valuable_items = [item for item in all_items if item["value"] > 0]
                valuable_items.sort(key=lambda x: x["value"], reverse=True)

                top_10 = valuable_items[:10]

                message = "💎 Top 10 Most Valuable Items:\n\n"
                for i, item in enumerate(top_10, 1):
                    emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                    category_emoji = get_category_emoji(item["category"])
                    trend = get_price_trend(item["display_name"], item["category"])

                    message += f"{i}. {emoji_part}{item['display_name']}\n"
                    message += f"   {category_emoji} {item['category']} | {format_value(item['value'])} | {trend}\n\n"

                message += "💡 Add to favorites: 'gagstock category/item_name'\n"
                message += (
                    "🚨 Set price alert: 'gagstock alert category/item below value'"
                )
                send_message_func(sender_id, message)
            else:
                send_message_func(sender_id, "❌ Failed to fetch stock data")
        except Exception as e:
            logger.error(f"Error fetching top items: {e}")
            send_message_func(sender_id, "❌ Error occurred while fetching top items.")
        return

    elif action == "stock":
        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )

            if stock_response.status_code == 200:
                stock_data = stock_response.json()
                restocks = get_next_restocks()
                prefs = get_user_preferences(sender_id)

                categories = {
                    "gear": stock_data.get("gear", []),
                    "seed": stock_data.get("seed", []),
                    "egg": stock_data.get("egg", []),
                    "honey": stock_data.get("honey", []),
                    "cosmetic": stock_data.get("cosmetic", []),
                }

                message = "📦 Current Stock:\n\n"

                for category, items in categories.items():
                    emoji = get_category_emoji(category)
                    restock_time = restocks.get(category, "Unknown")
                    total_value = sum(item.get("value", 0) for item in items)

                    message += f"{emoji} {category.title()} (⏳ {restock_time}) - Total: {format_value(total_value)}:\n"

                    if items:
                        sorted_items = sorted(
                            items, key=lambda x: x.get("value", 0), reverse=True
                        )
                        for item in sorted_items:
                            emoji_part = (
                                f"{item.get('emoji', '')} " if item.get("emoji") else ""
                            )
                            name = item.get("name", "Unknown")
                            value = format_value(item.get("value", 0))

                            rarity_indicator = ""
                            if prefs["show_rarity"] and item.get("value", 0) > 0:
                                if item["value"] >= 10000:
                                    rarity_indicator = " 💎"
                                elif item["value"] >= 1000:
                                    rarity_indicator = " ⭐"
                                elif item["value"] >= 100:
                                    rarity_indicator = " 🔥"

                            trend = get_price_trend(name, category)
                            message += f"   • {emoji_part}{name}: {value}{rarity_indicator} {trend}\n"
                    else:
                        message += "   • No items in stock\n"

                    message += "\n"

                message += f"{get_market_summary(stock_data)}\n\n"
                message += "💡 Add to favorites: 'gagstock category/item_name'\n"
                message += "🚨 Set price alert: 'gagstock alert category/item above/below value'"
                send_message_func(sender_id, message)
            else:
                send_message_func(
                    sender_id,
                    f"❌ Failed to fetch current stock data. (Status: {stock_response.status_code})",
                )
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching stock data: {e}")
            send_message_func(
                sender_id,
                "❌ Network error occurred while fetching stock data. Please try again later.",
            )
        except Exception as e:
            logger.error(f"Error fetching stock data: {e}")
            send_message_func(sender_id, "❌ Error occurred while fetching stock data.")
        return

    elif action == "search":
        if len(args) < 2:
            send_message_func(
                sender_id,
                "🔍 Smart Search:\n\n"
                "💡 Usage: 'gagstock search item_name'\n"
                "🔍 Examples:\n"
                "• 'gagstock search ancient shovel'\n"
                "• 'gagstock search legendary'\n"
                "• 'gagstock search royal'\n\n"
                "✨ Advanced search features:\n"
                "• Shows price trends\n"
                "• Displays rarity indicators\n"
                "• Quick add to favorites",
            )
            return

        item_name = " ".join(args[1:])
        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "https://vmi2625091.contaboserver.net/api/stocks",
                timeout=15,
                headers=headers,
            )

            if stock_response.status_code == 200:
                stock_data = stock_response.json()
                all_items = get_all_items_from_stock(stock_data)
                item_name_lower = item_name.lower()
                found_items = []

                for item in all_items:
                    if (
                        item_name_lower in item["name"]
                        or item["name"] in item_name_lower
                    ):
                        found_items.append(item)

                found_items.sort(key=lambda x: x["value"], reverse=True)

                if found_items:
                    if len(found_items) == 1:
                        item = found_items[0]
                        emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                        category_emoji = get_category_emoji(item["category"])
                        trend = get_price_trend(item["display_name"], item["category"])

                        rarity = ""
                        if item["value"] >= 10000:
                            rarity = " 💎 Ultra Rare"
                        elif item["value"] >= 1000:
                            rarity = " ⭐ Rare"
                        elif item["value"] >= 100:
                            rarity = " 🔥 Uncommon"

                        send_message_func(
                            sender_id,
                            f"🔍 Found: {emoji_part}{item['display_name']}\n"
                            f"{category_emoji} Category: {item['category'].title()}\n"
                            f"💰 Value: {format_value(item['value'])}{rarity}\n"
                            f"📈 Trend: {trend}\n\n"
                            f"💡 Add to favorites: 'gagstock {item['category']}/{item['display_name']}'\n"
                            f"🚨 Set price alert: 'gagstock alert {item['category']}/{item['display_name']} above/below value'",
                        )
                    else:
                        message = f"🔍 Found {len(found_items)} items matching '{item_name}':\n\n"
                        for i, item in enumerate(found_items[:15], 1):
                            emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                            category_emoji = get_category_emoji(item["category"])
                            trend = get_price_trend(
                                item["display_name"], item["category"]
                            )

                            rarity = ""
                            if item["value"] >= 10000:
                                rarity = " 💎"
                            elif item["value"] >= 1000:
                                rarity = " ⭐"
                            elif item["value"] >= 100:
                                rarity = " 🔥"

                            message += f"{i}. {category_emoji} {emoji_part}{item['display_name']}\n"
                            message += f"   💰 {format_value(item['value'])}{rarity} | {trend}\n\n"

                        if len(found_items) > 15:
                            message += f"... and {len(found_items) - 15} more items\n\n"

                        message += "💡 Add any item: 'gagstock category/item_name'\n"
                        message += "🚨 Set price alerts for valuable items!"
                        send_message_func(sender_id, message)
                else:
                    send_message_func(
                        sender_id,
                        f"❌ Item '{item_name}' not found in current stock.\n"
                        f"💡 Try a different spelling or check 'gagstock stock' for available items.\n"
                        f"🔍 You can also try 'gagstock top' to see the most valuable items.",
                    )
            else:
                send_message_func(
                    sender_id,
                    f"❌ Failed to fetch stock data for search. (Status: {stock_response.status_code})",
                )
        except Exception as e:
            logger.error(f"Error searching for item: {e}")
            send_message_func(sender_id, "❌ Error occurred while searching.")
        return

    elif action == "add":
        if len(args) < 2:
            send_message_func(
                sender_id,
                "⭐ Add Items to Favorites:\n\n"
                "💡 Format Options:\n"
                "   • 'gagstock add category/item_name'\n"
                "   • 'gagstock add cat1/item1|cat2/item2'\n\n"
                f"📋 Categories: {', '.join(get_available_categories())}\n\n"
                "🔍 Examples:\n"
                "   • 'gagstock add gear/ancient_shovel'\n"
                "   • 'gagstock add egg/legendary|honey/royal_jelly'\n\n"
                "✨ Pro tip: Use 'gagstock search' to find exact item names!",
            )
            return

        items_string = " ".join(args[1:])
        success, message = add_tracked_items(sender_id, items_string)
        send_message_func(sender_id, message)
        return

    elif action == "remove":
        if len(args) < 2:
            send_message_func(
                sender_id,
                "🗑️ Remove Items from Favorites:\n\n"
                "💡 Format: 'gagstock remove category/item_name'\n"
                "📋 Example: 'gagstock remove gear/ancient_shovel'\n\n"
                "🔍 View your favorites: 'gagstock list'",
            )
            return

        item_string = " ".join(args[1:])
        success, message = remove_tracked_item(sender_id, item_string)
        send_message_func(sender_id, message)
        return

    elif action == "list":
        message = list_tracked_items(sender_id)
        send_message_func(sender_id, message)
        return

    elif action == "clear":
        message = clear_tracked_items(sender_id)
        send_message_func(sender_id, message)
        return

    else:
        if "/" in action:
            items_string = " ".join(args)
            success, message = add_tracked_items(sender_id, items_string)
            send_message_func(sender_id, message)
        else:
            send_message_func(
                sender_id,
                f"❌ Unknown command: '{action}'\n"
                "💡 Use 'gagstock' without arguments to see all available commands.\n"
                "🔍 Popular commands:\n"
                "• 'gagstock on' - Start tracking\n"
                "• 'gagstock search item_name' - Find items\n"
                "• 'gagstock top' - Most valuable items",
            )
