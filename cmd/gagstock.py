import threading
import requests
import json
import logging
from datetime import datetime, timedelta
import time

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)

active_sessions = {}
user_favorites = {}
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


def find_item_by_name(item_name, stock_data):
    all_items = get_all_items_from_stock(stock_data)
    item_name_lower = item_name.lower()

    for item in all_items:
        if item_name_lower in item["name"] or item["name"] in item_name_lower:
            return item
    return None


def normalize_item_name(name):
    return name.lower().strip().replace("_", " ").replace("-", " ")


def find_item_by_fuzzy_name(item_name, stock_data):
    all_items = get_all_items_from_stock(stock_data)
    item_name_normalized = normalize_item_name(item_name)

    for item in all_items:
        if item_name_normalized == normalize_item_name(item["display_name"]):
            return item

    for item in all_items:
        item_normalized = normalize_item_name(item["display_name"])
        if (
            item_name_normalized in item_normalized
            or item_normalized in item_name_normalized
        ):
            return item

    return None


def check_favorites_in_stock(sender_id, stock_data):
    if sender_id not in user_favorites or not user_favorites[sender_id]:
        return []

    favorites_in_stock = []
    all_items = get_all_items_from_stock(stock_data)

    for favorite_item, favorite_category in user_favorites[sender_id].items():
        for item in all_items:
            item_normalized = normalize_item_name(item["display_name"])
            favorite_normalized = normalize_item_name(favorite_item)

            if (
                favorite_normalized == item_normalized
                or favorite_normalized in item_normalized
                or item_normalized in favorite_normalized
            ) and item["category"] == favorite_category:
                favorites_in_stock.append(item)
                break

    return favorites_in_stock


def add_favorite(sender_id, item_input, stock_data):
    if sender_id not in user_favorites:
        user_favorites[sender_id] = {}

    if "/" in item_input:
        parts = item_input.split("/", 1)
        if len(parts) == 2:
            category = parts[0].lower().strip()
            item_name = parts[1].strip()

            valid_categories = get_available_categories()
            if category not in valid_categories:
                return (
                    False,
                    f"❌ Invalid category '{category}'.\n"
                    f"📋 Valid categories: {', '.join(valid_categories)}\n"
                    f"💡 Use format: category/item_name (e.g., gear/ancient_shovel)",
                )

            for existing_item, existing_category in user_favorites[sender_id].items():
                if normalize_item_name(existing_item) == normalize_item_name(item_name):
                    return (
                        False,
                        f"❌ '{existing_item}' is already in your favorites!\n"
                        f"📦 Current category: {existing_category}\n"
                        f"💡 Use 'gagstock favorite remove {existing_item}' to remove it first",
                    )

            item = find_item_by_fuzzy_name(item_name, stock_data)
            if item and item["category"] != category:
                return (
                    False,
                    f"⚠️ '{item_name}' found in '{item['category']}' category, not '{category}'.\n"
                    f"💡 Use: {item['category']}/{item['display_name']}",
                )

            user_favorites[sender_id][item_name] = category

            if item:
                emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                return (
                    True,
                    f"✅ Added '{emoji_part}{item['display_name']}' to your favorites!\n"
                    f"📦 Category: {category.title()}\n"
                    f"🔔 You'll be notified when this item appears in stock.",
                )
            else:
                category_emoji = get_category_emoji(category)
                return (
                    True,
                    f"✅ Added '{item_name}' to your favorites!\n"
                    f"{category_emoji} Category: {category.title()}\n"
                    f"💡 This item will be tracked when it appears in stock.\n"
                    f"🔔 You'll be notified when it becomes available.",
                )
        else:
            return (
                False,
                f"❌ Invalid format. Use: category/item_name\n"
                f"📋 Categories: {', '.join(get_available_categories())}\n"
                f"💡 Example: gear/ancient_shovel",
            )
    else:
        item = find_item_by_fuzzy_name(item_input, stock_data)
        if not item:
            return (
                False,
                f"❌ Item '{item_input}' not found in current stock.\n"
                f"💡 Use format: category/item_name\n"
                f"📋 Categories: {', '.join(get_available_categories())}\n"
                f"🔍 Example: gear/{item_input.replace(' ', '_')}",
            )

        for existing_item, existing_category in user_favorites[sender_id].items():
            if normalize_item_name(existing_item) == normalize_item_name(
                item["display_name"]
            ):
                return (
                    False,
                    f"❌ '{existing_item}' is already in your favorites!\n"
                    f"📦 Category: {existing_category}\n"
                    f"💡 Use 'gagstock favorite remove {existing_item}' to remove it",
                )

        user_favorites[sender_id][item["display_name"]] = item["category"]
        emoji_part = f"{item['emoji']} " if item["emoji"] else ""
        category_emoji = get_category_emoji(item["category"])
        return (
            True,
            f"✅ Added '{emoji_part}{item['display_name']}' to your favorites!\n"
            f"{category_emoji} Category: {item['category'].title()}\n"
            f"🔔 You'll be notified when this item restocks.",
        )


def remove_favorite(sender_id, item_name):
    if sender_id not in user_favorites or not user_favorites[sender_id]:
        return False, "❌ You don't have any favorites to remove."

    item_name_normalized = normalize_item_name(item_name)
    removed_item = None

    for favorite_item, category in list(user_favorites[sender_id].items()):
        favorite_normalized = normalize_item_name(favorite_item)
        if (
            favorite_normalized == item_name_normalized
            or item_name_normalized in favorite_normalized
            or favorite_normalized in item_name_normalized
        ):
            del user_favorites[sender_id][favorite_item]
            removed_item = favorite_item
            break

    if removed_item:
        return True, f"✅ Removed '{removed_item}' from your favorites."
    else:
        return False, f"❌ '{item_name}' not found in your favorites."


def list_favorites(sender_id):
    if sender_id not in user_favorites or not user_favorites[sender_id]:
        return (
            "❌ You don't have any favorites set.\n"
            f"💡 Add favorites with: 'gagstock favorite add category/item_name'\n"
            f"📋 Categories: {', '.join(get_available_categories())}"
        )

    favorites_by_category = {}
    for item_name, category in user_favorites[sender_id].items():
        if category not in favorites_by_category:
            favorites_by_category[category] = []
        favorites_by_category[category].append(item_name)

    message = "⭐ Your Favorites:\n\n"

    for category in get_available_categories():
        if category in favorites_by_category:
            emoji = get_category_emoji(category)
            message += f"{emoji} {category.title()}:\n"
            for item in favorites_by_category[category]:
                message += f"   • {item}\n"
            message += "\n"

    message += f"📊 Total: {len(user_favorites[sender_id])} favorite(s)\n"
    message += f"💡 Remove with: 'gagstock favorite remove item_name'"
    return message


def clear_favorites(sender_id):
    if sender_id not in user_favorites or not user_favorites[sender_id]:
        return "❌ You don't have any favorites to clear."

    count = len(user_favorites[sender_id])
    user_favorites[sender_id] = {}
    return f"✅ Cleared {count} favorite(s) successfully."


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

            if session.get("favorites_only", False):
                favorites_in_stock = check_favorites_in_stock(sender_id, stock_data)
                if favorites_in_stock:
                    should_notify = True
                    restocks = get_next_restocks()

                    message = "⭐ Your favorite items are in stock!\n\n"

                    category_restocks = {
                        "gear": restocks["gear"],
                        "seed": restocks["seed"],
                        "egg": restocks["egg"],
                        "honey": restocks["honey"],
                        "cosmetic": restocks["cosmetic"],
                    }

                    for item in favorites_in_stock:
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

    if not args:
        send_message_func(
            sender_id,
            "📌 Gagstock Commands:\n\n"
            "📊 Tracking:\n"
            "• 'gagstock on' - Track all stock changes\n"
            "• 'gagstock off' - Stop all stock tracking\n"
            "• 'gagstock favorites on' - Track only favorite items\n"
            "• 'gagstock favorites off' - Stop favorites tracking\n\n"
            "⭐ Favorites Management:\n"
            "• 'gagstock favorite add category/item_name' - Add favorite item\n"
            "• 'gagstock favorite add item_name' - Add from current stock\n"
            "• 'gagstock favorite remove [item_name]' - Remove favorite\n"
            "• 'gagstock favorite list' - Show your favorites\n"
            "• 'gagstock favorite clear' - Clear all favorites\n\n"
            "🔍 Stock Information:\n"
            "• 'gagstock stock' - Show current stock by category\n"
            "• 'gagstock search [item_name]' - Search for items\n\n"
            f"📋 Categories: {', '.join(get_available_categories())}\n"
            "💡 Example: 'gagstock favorite add gear/ancient_shovel'",
        )
        return

    action = args[0].lower()

    if action == "off":
        if sender_id in active_sessions:
            session_type = (
                "favorites"
                if active_sessions[sender_id].get("favorites_only", False)
                else "all stocks"
            )
            cleanup_session(sender_id)
            send_message_func(
                sender_id, f"🛑 Gagstock tracking stopped ({session_type})."
            )
        else:
            send_message_func(sender_id, "⚠️ You don't have an active gagstock session.")
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

                message += (
                    "💡 Add to favorites: 'gagstock favorite add category/item_name'"
                )
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
                item = find_item_by_fuzzy_name(item_name, stock_data)

                if item:
                    emoji_part = f"{item['emoji']} " if item["emoji"] else ""
                    category_emoji = get_category_emoji(item["category"])
                    send_message_func(
                        sender_id,
                        f"🔍 Found: {emoji_part}{item['display_name']}\n"
                        f"{category_emoji} Category: {item['category'].title()}\n"
                        f"💰 Value: {format_value(item['value'])}\n\n"
                        f"💡 Add to favorites: 'gagstock favorite add {item['category']}/{item['display_name']}'",
                    )
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

    elif action == "favorite":
        if len(args) < 2:
            send_message_func(
                sender_id,
                "📌 Favorite Management Commands:\n\n"
                "• 'gagstock favorite add category/item_name' - Add specific item\n"
                "• 'gagstock favorite add item_name' - Add from current stock\n"
                "• 'gagstock favorite remove [item_name]' - Remove from favorites\n"
                "• 'gagstock favorite list' - Show your favorites\n"
                "• 'gagstock favorite clear' - Clear all favorites\n\n"
                f"📋 Categories: {', '.join(get_available_categories())}\n\n"
                "💡 Examples:\n"
                "   • 'gagstock favorite add egg/legendary_egg'\n"
                "   • 'gagstock favorite add ancient seed' (from current stock)",
            )
            return

        fav_action = args[1].lower()

        if fav_action == "add":
            if len(args) < 3:
                send_message_func(
                    sender_id,
                    "⚠️ Please specify an item to add to favorites.\n\n"
                    "💡 Format Options:\n"
                    "   • 'gagstock favorite add category/item_name'\n"
                    "   • 'gagstock favorite add item_name' (from current stock)\n\n"
                    f"📋 Categories: {', '.join(get_available_categories())}\n\n"
                    "🔍 Examples:\n"
                    "   • 'gagstock favorite add gear/ancient_shovel'\n"
                    "   • 'gagstock favorite add honey/royal_jelly'",
                )
                return

            item_name = " ".join(args[2:])
            try:
                headers = {"User-Agent": "GagStock-Bot/1.0"}
                stock_response = requests.get(
                    "http://65.108.103.151:22377/api/stocks?type=all",
                    timeout=15,
                    headers=headers,
                )

                if stock_response.status_code == 200:
                    stock_data = stock_response.json()
                    success, message = add_favorite(sender_id, item_name, stock_data)
                    send_message_func(sender_id, message)
                else:
                    send_message_func(
                        sender_id,
                        f"❌ Failed to fetch stock data. (Status: {stock_response.status_code})",
                    )
            except Exception as e:
                logger.error(f"Error adding favorite: {e}")
                send_message_func(sender_id, "❌ Error occurred while adding favorite.")
            return

        elif fav_action == "remove":
            if len(args) < 3:
                send_message_func(
                    sender_id,
                    "⚠️ Please specify an item name to remove from favorites.\n"
                    "💡 Example: 'gagstock favorite remove ancient_shovel'",
                )
                return

            item_name = " ".join(args[2:])
            success, message = remove_favorite(sender_id, item_name)
            send_message_func(sender_id, message)
            return

        elif fav_action == "list":
            message = list_favorites(sender_id)
            send_message_func(sender_id, message)
            return

        elif fav_action == "clear":
            message = clear_favorites(sender_id)
            send_message_func(sender_id, message)
            return

        else:
            send_message_func(
                sender_id,
                "❌ Unknown favorite command.\n"
                f"💡 Use: 'add', 'remove', 'list', or 'clear'",
            )
        return

    elif action == "favorites":
        if len(args) < 2:
            send_message_func(
                sender_id,
                "📌 Favorites Tracking Commands:\n\n"
                "🔔 Tracking:\n"
                "• 'gagstock favorites on' - Start tracking only favorite items\n"
                "• 'gagstock favorites off' - Stop favorites tracking\n\n"
                "⭐ Management:\n"
                "• 'gagstock favorite add category/item_name' - Add to favorites\n"
                "• 'gagstock favorite add item_name' - Add from current stock\n"
                "• 'gagstock favorite remove [item_name]' - Remove from favorites\n"
                "• 'gagstock favorite list' - Show your favorites\n"
                "• 'gagstock favorite clear' - Clear all favorites\n\n"
                f"📋 Categories: {', '.join(get_available_categories())}\n"
                "💡 Example: 'gagstock favorite add cosmetic/rainbow_hat'",
            )
            return

        fav_action = args[1].lower()

        if fav_action == "on":
            if sender_id not in user_favorites or not user_favorites[sender_id]:
                send_message_func(
                    sender_id,
                    "⚠️ You need to add some favorites first!\n\n"
                    "💡 Use 'gagstock favorite add category/item_name' to add items to your favorites.\n"
                    f"📋 Categories: {', '.join(get_available_categories())}\n\n"
                    "🔍 Examples:\n"
                    "   • 'gagstock favorite add gear/ancient_shovel'\n"
                    "   • 'gagstock favorite add egg/legendary_egg'",
                )
                return

            if sender_id in active_sessions:
                current_mode = (
                    "favorites"
                    if active_sessions[sender_id].get("favorites_only", False)
                    else "all stocks"
                )
                send_message_func(
                    sender_id,
                    f"📡 You're already tracking ({current_mode}).\n"
                    "💡 Use 'gagstock off' to stop current tracking first.",
                )
                return

            favorites_list = ", ".join(user_favorites[sender_id].keys())
            send_message_func(
                sender_id,
                f"⭐ Favorites tracking started!\n"
                f"🔔 You'll be notified when your favorite items are in stock.\n\n"
                f"📋 Current favorites: {favorites_list}\n\n"
                f"💡 Add more with: 'gagstock favorite add category/item_name'",
            )

            active_sessions[sender_id] = {
                "timer": None,
                "last_combined_key": None,
                "last_message": "",
                "favorites_only": True,
            }

            logger.info(f"Started favorites-only gagstock session for {sender_id}")
            fetch_all_data(sender_id, send_message_func)
            return

        elif fav_action == "off":
            if sender_id in active_sessions and active_sessions[sender_id].get(
                "favorites_only", False
            ):
                cleanup_session(sender_id)
                send_message_func(sender_id, "🛑 Favorites tracking stopped.")
            else:
                send_message_func(
                    sender_id, "⚠️ You don't have an active favorites tracking session."
                )
            return

        else:
            send_message_func(
                sender_id, "❌ Unknown favorites command.\n" "💡 Use 'on' or 'off'"
            )
        return

    elif action == "on":
        if sender_id in active_sessions:
            current_mode = (
                "favorites"
                if active_sessions[sender_id].get("favorites_only", False)
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
            "💡 For favorites-only tracking, use: 'gagstock favorites on'",
        )

        active_sessions[sender_id] = {
            "timer": None,
            "last_combined_key": None,
            "last_message": "",
            "favorites_only": False,
        }

        logger.info(f"Started full gagstock session for {sender_id}")
        fetch_all_data(sender_id, send_message_func)
        return

    else:
        send_message_func(
            sender_id,
            f"❌ Unknown command: '{action}'\n"
            "💡 Use 'gagstock' without arguments to see all available commands.",
        )
