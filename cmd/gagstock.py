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


def save_tracked_items_to_file():
    try:
        with open(TRACKED_ITEMS_FILE, "wb") as f:
            pickle.dump(user_tracked_items, f)
        logger.debug(f"Saved tracked items for {len(user_tracked_items)} users")
    except Exception as e:
        logger.error(f"Error saving tracked items: {e}")


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


def format_list(arr):
    if not arr:
        return "None."

    result = []
    for item in arr:
        try:
            emoji = item.get("emoji", "")
            name = item.get("name", "Unknown")
            value = item.get("value", 0)
            emoji_part = f"{emoji} " if emoji else ""
            result.append(f"- {emoji_part}{name}: {format_value(value)}")
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
                f"✅ Added '{item['item_name']}' to tracking list!\n{category_emoji} Category: {item['category'].title()}"
            )
        else:
            message_parts.append(f"✅ Added {added_count} items to tracking list:")
            for item in valid_items:
                category_emoji = get_category_emoji(item["category"])
                message_parts.append(
                    f"{category_emoji} {item['category']}/{item['item_name']}"
                )

        message_parts.append("🔔 You'll be notified when these items appear in stock.")

        if sender_id in active_sessions:
            session_type = (
                "tracked items only"
                if active_sessions[sender_id].get("tracked_only", False)
                else "all stocks"
            )
            message_parts.append(f"📡 Current tracking mode: {session_type}")
            if not active_sessions[sender_id].get("tracked_only", False):
                message_parts.append(
                    "💡 Use 'gagstock off' then track items to switch to item-only mode"
                )

    if duplicate_items:
        message_parts.append(f"⚠️ Already tracking: {', '.join(duplicate_items)}")

    return True, "\n".join(message_parts)


def remove_tracked_item(sender_id, item_string):
    if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
        return False, "❌ You don't have any tracked items to remove."

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
            save_tracked_items_to_file()
            logger.info(
                f"Removed tracked item for {sender_id}: {removed_item['category']}/{removed_item['item_name']}"
            )
            return (
                True,
                f"✅ Removed '{removed_item['category']}/{removed_item['item_name']}' from tracking list.",
            )

    return False, f"❌ '{category}/{item_name}' not found in your tracking list."


def list_tracked_items(sender_id):
    if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
        return (
            "❌ You don't have any tracked items.\n"
            "💡 Add items with: 'gagstock category/item_name'\n"
            f"📋 Categories: {', '.join(get_available_categories())}"
        )

    tracked_by_category = {}
    for item in user_tracked_items[sender_id]:
        category = item["category"]
        if category not in tracked_by_category:
            tracked_by_category[category] = []
        tracked_by_category[category].append(item["item_name"])

    message = "🔔 Your Tracked Items:\n\n"

    for category in get_available_categories():
        if category in tracked_by_category:
            emoji = get_category_emoji(category)
            message += f"{emoji} {category.title()}:\n"
            for item in tracked_by_category[category]:
                message += f"   • {item}\n"
            message += "\n"

    session_status = ""
    if sender_id in active_sessions:
        session_type = (
            "tracked items only"
            if active_sessions[sender_id].get("tracked_only", False)
            else "all stocks"
        )
        session_status = f"📡 Currently tracking: {session_type}\n"
    else:
        session_status = "📴 Tracking: OFF\n"

    message += f"📊 Total: {len(user_tracked_items[sender_id])} tracked item(s)\n"
    message += session_status
    message += "💡 Remove with: 'gagstock remove category/item_name'"
    return message


def clear_tracked_items(sender_id):
    if sender_id not in user_tracked_items or not user_tracked_items[sender_id]:
        return "❌ You don't have any tracked items to clear."

    count = len(user_tracked_items[sender_id])
    user_tracked_items[sender_id] = []
    save_tracked_items_to_file()
    logger.info(f"Cleared {count} tracked items for {sender_id}")
    return f"✅ Cleared {count} tracked item(s) successfully."


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


def cleanup_session(sender_id):
    if sender_id in active_sessions:
        session = active_sessions[sender_id]
        timer = session.get("timer")
        if timer:
            timer.cancel()
        del active_sessions[sender_id]
        logger.info(f"Cleaned up gagstock session for {sender_id}")


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

        if combined_key == session.get("last_combined_key"):
            logger.debug(f"No changes detected for {sender_id}, scheduling next check")
        else:
            logger.info(f"Data changed for {sender_id}, sending update")
            session["last_combined_key"] = combined_key

            should_notify = False

            if session.get("tracked_only", False):
                tracked_in_stock = check_tracked_items_in_stock(sender_id, stock_data)
                if tracked_in_stock:
                    should_notify = True
                    restocks = get_next_restocks()

                    message = "🔔 Your tracked items are in stock!\n\n"

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
                        message += f"🔔 {emoji_part}{item['display_name']}: {format_value(item['value'])}\n"
                        message += f"   📦 Category: {item['category'].title()} | ⏳ Restock in: {restock_time}\n\n"

                    weather_icon = weather_data.get("icon", "🌦️")
                    weather_current = weather_data.get("currentWeather", "Unknown")
                    weather_description = weather_data.get(
                        "description", "No description"
                    )
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
            else:
                should_notify = True
                restocks = get_next_restocks()

                gear_list = format_list(stock_data.get("gear", []))
                seed_list = format_list(stock_data.get("seed", []))
                egg_list = format_list(stock_data.get("egg", []))
                cosmetic_list = format_list(stock_data.get("cosmetic", []))
                honey_list = format_list(stock_data.get("honey", []))

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
                    f"🎨 Cosmetic:\n{cosmetic_list}\n⏳ Restock in: {restocks['cosmetic']}\n\n"
                    f"🍯 Honey:\n{honey_list}\n⏳ Restock in: {restocks['honey']}\n\n"
                    f"{weather_details}"
                )

            if should_notify and message != session.get("last_message"):
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

    load_tracked_items()

    if not args:
        send_message_func(
            sender_id,
            "📌 Gagstock Commands:\n\n"
            "📊 Tracking:\n"
            "• 'gagstock on' - Track all stock changes\n"
            "• 'gagstock off' - Stop stock tracking\n\n"
            "🔔 Item Notifications:\n"
            "• 'gagstock category/item_name' - Track specific item\n"
            "• 'gagstock cat1/item1|cat2/item2' - Track multiple items\n"
            "• 'gagstock add category/item_name' - Add item to tracking\n"
            "• 'gagstock remove category/item_name' - Remove tracked item\n"
            "• 'gagstock list' - Show tracked items\n"
            "• 'gagstock clear' - Clear all tracked items\n\n"
            "🔍 Stock Information:\n"
            "• 'gagstock stock' - Show current stock by category\n"
            "• 'gagstock search [item_name]' - Search for items\n\n"
            f"📋 Categories: {', '.join(get_available_categories())}\n"
            "💡 Examples:\n"
            "   • 'gagstock gear/ancient_shovel'\n"
            "   • 'gagstock egg/legendary_egg|gear/shovel'\n"
            "   • 'gagstock add honey/royal_jelly'",
        )
        return

    action = args[0].lower()

    if action == "off":
        if sender_id in active_sessions:
            session_type = (
                "tracked items only"
                if active_sessions[sender_id].get("tracked_only", False)
                else "all stocks"
            )
            cleanup_session(sender_id)
            send_message_func(
                sender_id, f"🛑 Gagstock tracking stopped ({session_type})."
            )
        else:
            send_message_func(sender_id, "⚠️ You don't have an active gagstock session.")
        return

    elif action == "on":
        if sender_id in active_sessions:
            current_mode = (
                "tracked items only"
                if active_sessions[sender_id].get("tracked_only", False)
                else "all stocks"
            )
            send_message_func(
                sender_id,
                f"📡 You're already tracking ({current_mode}).\n"
                "💡 Use 'gagstock off' to stop current tracking first.",
            )
            return

        send_message_func(
            sender_id,
            "✅ Gagstock tracking started!\n"
            "🔔 You'll be notified when stock or weather changes.\n\n"
            "💡 For item-specific tracking, use: 'gagstock category/item_name'",
        )

        active_sessions[sender_id] = {
            "timer": None,
            "last_combined_key": None,
            "last_message": "",
            "tracked_only": False,
        }

        logger.info(f"Started full gagstock session for {sender_id}")
        fetch_all_data(sender_id, send_message_func)
        return

    elif action == "stock":
        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "http://65.108.103.151:22377/api/stocks?type=all",
                timeout=15,
                headers=headers,
            )

            if stock_response.status_code == 200:
                stock_data = stock_response.json()
                restocks = get_next_restocks()

                categories = {
                    "gear": stock_data.get("gearStock", []),
                    "seed": stock_data.get("seedsStock", []),
                    "egg": stock_data.get("eggStock", []),
                    "honey": stock_data.get("honeyStock", []),
                    "cosmetic": stock_data.get("cosmeticStock", []),
                }

                message = "📦 Current Stock:\n\n"

                for category, items in categories.items():
                    emoji = get_category_emoji(category)
                    restock_time = restocks.get(category, "Unknown")

                    message += f"{emoji} {category.title()} (⏳ {restock_time}):\n"

                    if items:
                        for item in items:
                            emoji_part = (
                                f"{item.get('emoji', '')} " if item.get("emoji") else ""
                            )
                            name = item.get("name", "Unknown")
                            value = format_value(item.get("value", 0))
                            message += f"   • {emoji_part}{name}: {value}\n"
                    else:
                        message += "   • No items in stock\n"

                    message += "\n"

                message += "💡 Track items: 'gagstock category/item_name'"
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
                "⚠️ Please specify an item name to search for.\n💡 Example: 'gagstock search ancient shovel'",
            )
            return

        item_name = " ".join(args[1:])
        try:
            headers = {"User-Agent": "GagStock-Bot/1.0"}
            stock_response = requests.get(
                "http://65.108.103.151:22377/api/stocks?type=all",
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

                if found_items:
                    if len(found_items) == 1:
                        item = found_items[0]
                        emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                        category_emoji = get_category_emoji(item["category"])
                        send_message_func(
                            sender_id,
                            f"🔍 Found: {emoji_part}{item['display_name']}\n"
                            f"{category_emoji} Category: {item['category'].title()}\n"
                            f"💰 Value: {format_value(item['value'])}\n\n"
                            f"💡 Track this item: 'gagstock {item['category']}/{item['display_name']}'",
                        )
                    else:
                        message = f"🔍 Found {len(found_items)} items matching '{item_name}':\n\n"
                        for item in found_items:
                            emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                            category_emoji = get_category_emoji(item["category"])
                            message += f"{category_emoji} {emoji_part}{item['display_name']} ({item['category']}) - {format_value(item['value'])}\n"

                        message += f"\n💡 Track any item: 'gagstock category/item_name'"
                        send_message_func(sender_id, message)
                else:
                    send_message_func(
                        sender_id,
                        f"❌ Item '{item_name}' not found in current stock.\n"
                        f"💡 Try a different spelling or check 'gagstock stock' for available items.",
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
                "⚠️ Please specify items to track.\n\n"
                "💡 Format Options:\n"
                "   • 'gagstock add category/item_name'\n"
                "   • 'gagstock add cat1/item1|cat2/item2'\n\n"
                f"📋 Categories: {', '.join(get_available_categories())}\n\n"
                "🔍 Examples:\n"
                "   • 'gagstock add gear/ancient_shovel'\n"
                "   • 'gagstock add egg/legendary|honey/royal_jelly'",
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
                "⚠️ Please specify an item to remove from tracking.\n"
                "💡 Format: 'gagstock remove category/item_name'\n"
                "📋 Example: 'gagstock remove gear/ancient_shovel'",
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
            if success:
                if sender_id in active_sessions:
                    send_message_func(sender_id, message)
                else:
                    if (
                        sender_id in user_tracked_items
                        and user_tracked_items[sender_id]
                    ):
                        send_message_func(
                            sender_id,
                            f"{message}\n\n🔔 Starting item-specific tracking...",
                        )

                        active_sessions[sender_id] = {
                            "timer": None,
                            "last_combined_key": None,
                            "last_message": "",
                            "tracked_only": True,
                        }

                        logger.info(
                            f"Started tracked-items-only gagstock session for {sender_id}"
                        )
                        fetch_all_data(sender_id, send_message_func)
                    else:
                        send_message_func(sender_id, message)
            else:
                send_message_func(sender_id, message)
        else:
            send_message_func(
                sender_id,
                f"❌ Unknown command: '{action}'\n"
                "💡 Use 'gagstock' without arguments to see all available commands.",
            )
