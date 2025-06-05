import os
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json
import re # For parsing reminder time
import random # For games and coinflip

# --- Bot Setup ---
# Define Intents: Crucial for your bot to receive events from Discord.
# You MUST enable these in your Discord Developer Portal under your bot's settings.
# 1. PRESENCE INTENT
# 2. SERVER MEMBERS INTENT
# 3. MESSAGE CONTENT INTENT
intents = discord.Intents.default()
intents.members = True          # Required for moderation commands (ban, kick, mute, unmute)
intents.message_content = True  # Required for reading command messages (e.g., !stock, !clear)
intents.presences = True        # Useful for member presence updates, if you expand functionality

bot = commands.Bot(command_prefix=("!", ":"), intents=intents)
bot.remove_command('help') # This line removes the default help command

# --- Global Variables for Autostock and New Features ---
AUTOSTOCK_ENABLED = False
LAST_STOCK_DATA = None # Will store the full dictionary response
STOCK_API_URL = "https://growagardenapi.vercel.app/api/stock/GetStock"
RESTOCK_TIME_API_URL = "https://growagardenapi.vercel.app/api/stock/Restock-Time"
WEATHER_API_URL = "https://growagardenapi.vercel.app/api/GetWeather" # This is assumed to be the in-game weather API

# AUTOSTOCK_CHANNEL_ID will be set dynamically when the !autostock on command is used.
AUTOSTOCK_CHANNEL_ID = None
# GARDEN_SHOWCASE_CHANNEL_ID needs to be set to an actual channel ID where you want garden showcases to be posted
GARDEN_SHOWCASE_CHANNEL_ID = 1379734424895361054 # Channel for !showgardens (e.g., 123456789012345678) - REPLACE WITH ACTUAL ID

STOCK_LOGS = [] # Stores a history of stock changes (currently seeds only)

# Bot start time for uptime command
BOT_START_TIME = datetime.utcnow()

# --- Game States ---
active_c4_games = {} # {channel_id: Connect4Game instance}
active_tictactoe_games = {} # {channel_id: TicTacToeGame instance}

# --- DM Notification Specifics ---
DM_NOTIFY_ROLE_ID = 1302076375922118696  # The specific role ID for DM notifications
DM_BYPASS_ROLE_ID = 1379754489724145684 # New role ID that can bypass DM notification command requirements
DM_NOTIFICATION_LOG_CHANNEL_ID = 1379734424895361054 # Channel to log stock changes for DM notifications

# DM_NOTIFIED_USERS now stores a dictionary of preferences per user:
# {user_id: {"seeds": True/False, "gear": True/False}}
DM_NOTIFIED_USERS = {}

# Define which items to monitor for DM notifications, by category
# Each entry now includes a 'type' key for internal tracking and display in DMs
DM_MONITORED_CATEGORIES = {
    "seedsStock": {"type": "seeds", "items": ["Beanstalk Seed", "Pepper Seed", "Mushroom Seed"]},
    "gearStock": {"type": "gear", "items": ["Master Sprinkler", "Lightning Rod"]}
}
# Stores the last known status of monitored items for DM notifications, per category
LAST_KNOWN_DM_ITEM_STATUS = {category: set() for category in DM_MONITORED_CATEGORIES.keys()}

DM_USERS_FILE = 'dm_users.json' # File to persist DM_NOTIFIED_USERS

# --- New Feature Data Storage ---
GAME_STATS_FILE = 'game_stats.json'
game_stats = {} # {user_id: {"c4_wins": X, "c4_losses": Y, "c4_draws": Z, "ttt_wins": X, ...}}

ACHIEVEMENTS_FILE = 'achievements.json'
achievements = {} # {user_id: ["achievement_id_1", "achievement_id_2"]}

NOTIFY_ITEMS_FILE = 'notify_items.json'
notify_items = {} # {user_id: "item_name"} (only one item per user at a time)

MY_GARDENS_FILE = 'my_gardens.json'
my_gardens = {} # {user_id: {"description": "...", "image_url": "..."}}

REMINDERS_FILE = 'reminders.json'
reminders = [] # [{"user_id": ..., "remind_time": timestamp, "message": "..."}]

# --- Economy System Variables ---
USER_BALANCES_FILE = 'user_balances.json'
user_balances = {} # {user_id: amount}

USER_INVENTORIES_FILE = 'user_inventories.json'
user_inventories = {} # {user_id: {item_name: quantity}}

DAILY_CLAIM_COOLDOWN = 24 * 3600 # 24 hours in seconds
LAST_DAILY_CLAIM_FILE = 'last_daily_claim.json'
last_daily_claim = {} # {user_id: timestamp_utc}

# Predefined shop items (for !shop, !buy, !sell)
SHOP_ITEMS = {
    "xp_boost": {"display_name": "XP Boost", "price": 100, "sell_price": 50, "type": "consumable", "description": "Boosts your XP gain for a short period."},
    "mystery_box": {"display_name": "Mystery Box", "price": 250, "sell_price": 125, "type": "lootbox", "description": "Contains a random valuable item."},
    "common_gem": {"display_name": "Common Gem", "price": None, "sell_price": 20, "type": "material", "description": "A basic crafting material."},
    "rare_material": {"display_name": "Rare Material", "price": 500, "sell_price": 250, "type": "material", "description": "A valuable crafting material."},
    "token_of_fortune": {"display_name": "Token of Fortune", "price": 75, "sell_price": 30, "type": "consumable", "description": "Increases your luck in minigames."}
}

# Predefined crafting recipes
CRAFTING_RECIPES = {
    "super_boost": {
        "display_name": "Super Boost",
        "ingredients": {"XP Boost": 2, "Token of Fortune": 1},
        "output": {"Super Boost": 1},
        "price": 0, # Not directly buyable, only crafted
        "sell_price": 200,
        "description": "A powerful boost combining XP and luck."
    },
    "legendary_gem": {
        "display_name": "Legendary Gem",
        "ingredients": {"Common Gem": 5, "Rare Material": 3},
        "output": {"Legendary Gem": 1},
        "price": 0,
        "sell_price": 1500,
        "description": "A highly valuable and rare gem."
    }
}

# --- Lottery System Variables ---
LOTTO_FILE = 'lotto.json'
LOTTO_TICKETS = {} # {user_id: quantity}
LOTTO_POT = 0      # Current coin amount in the lottery pot
LOTTO_TICKET_PRICE = 100 # Price per lottery ticket
LOTTO_MIN_PLAYERS = 2 # Minimum players for a lottery draw

# --- Ban Request Specifics ---
BAN_REQUEST_LOG_CHANNEL_ID = 1379985805027840120 # Channel to send ban request logs
BOOSTING_ROLE_ID = 1302076375922118696 # Role ID for users who cannot be banned

# Stores the state of each user's ban request process:
# {user_id: {"state": "awaiting_payment_confirmation" | "awaiting_userid", "guild_id": int}}
BAN_REQUEST_STATES = {}

# --- Achievement Definitions ---
ACHIEVEMENT_DEFINITIONS = {
    "FIRST_C4_WIN": "First Connect4 Victory!",
    "FIRST_TTT_WIN": "First Tic-Tac-Toe Victory!",
    "FIRST_AUTOSTOCK_TOGGLE": "Autostock Activator!",
    "FIRST_DM_NOTIFICATION": "Stock Alert Pioneer!",
    "FIRST_REMINDER_SET": "Time Bender!",
    "FIRST_GARDEN_SHOWCASE": "Budding Botanist!",
    "FIVE_C4_WINS": "Connect4 Pro!",
    "FIVE_TTT_WINS": "Tic-Tac-Toe Master!",
    "FIRST_DAILY_CLAIM": "Daily Dough Getter!", # New achievement for daily command
    "FIRST_ROLL_COMMAND": "First Roll!", # New achievement for roll command
    "FIRST_LOTTO_ENTRY": "Lottery Enthusiast!" # New achievement for lottery entry
}

# --- Helper Functions for Data Persistence (JSON files) ---
def load_data(file_path, default_data={}):
    """Loads data from a JSON file, returning default_data if file not found or corrupted."""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                data = json.load(f)
                print(f"Loaded data from {file_path}.")
                return data
            except json.JSONDecodeError:
                print(f"Error decoding {file_path}. File might be empty or corrupted. Returning default data.")
                return default_data
    else:
        print(f"{file_path} not found. Starting with empty data.")
        return default_data

def save_data(file_path, data):
    """Saves data to a JSON file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"Saved data to {file_path}.")
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")

# --- Economy Data Persistence ---
def load_user_balances():
    global user_balances
    user_balances_raw = load_data(USER_BALANCES_FILE, {})
    user_balances = {int(k): v for k, v in user_balances_raw.items()} # Ensure keys are ints
    print(f"Loaded balances for {len(user_balances)} users.")

def save_user_balances():
    save_data(USER_BALANCES_FILE, {str(k): v for k, v in user_balances.items()})

def load_user_inventories():
    global user_inventories
    user_inventories_raw = load_data(USER_INVENTORIES_FILE, {})
    user_inventories = {int(k): v for k, v in user_inventories_raw.items()} # Ensure user_ids are ints
    print(f"Loaded inventories for {len(user_inventories)} users.")

def save_user_inventories():
    save_data(USER_INVENTORIES_FILE, {str(k): v for k, v in user_inventories.items()})

def load_last_daily_claim():
    global last_daily_claim
    last_daily_claim_raw = load_data(LAST_DAILY_CLAIM_FILE, {})
    last_daily_claim = {}
    for user_id_str, timestamp_str in last_daily_claim_raw.items():
        try:
            last_daily_claim[int(user_id_str)] = datetime.fromisoformat(timestamp_str)
        except (ValueError, KeyError) as e:
            print(f"Error loading last daily claim for user {user_id_str}: {e}. Skipping entry.")
    print(f"Loaded last daily claims for {len(last_daily_claim)} users.")

def save_last_daily_claim():
    claims_to_save = {str(k): v.isoformat() for k, v in last_daily_claim.items()}
    save_data(LAST_DAILY_CLAIM_FILE, claims_to_save)

# --- Game Stats Persistence ---
def load_game_stats():
    global game_stats
    game_stats_raw = load_data(GAME_STATS_FILE, {})
    # Ensure user IDs are integers
    game_stats = {int(user_id): data for user_id, data in game_stats_raw.items()}
    print(f"Loaded game stats for {len(game_stats)} users.")

def save_game_stats():
    # Convert user IDs back to strings for JSON serialization
    save_data(GAME_STATS_FILE, {str(user_id): data for user_id, data in game_stats.items()})

def update_game_stats(user_id, game_type, result_type):
    """Updates game statistics for a user."""
    game_stats.setdefault(user_id, {"c4_wins": 0, "c4_losses": 0, "c4_draws": 0, "ttt_wins": 0, "ttt_losses": 0, "ttt_draws": 0})
    if game_type == "c4":
        if result_type == "win":
            game_stats[user_id]["c4_wins"] += 1
        elif result_type == "loss":
            game_stats[user_id]["c4_losses"] += 1
        elif result_type == "draw":
            game_stats[user_id]["c4_draws"] += 1
    elif game_type == "ttt":
        if result_type == "win":
            game_stats[user_id]["ttt_wins"] += 1
        elif result_type == "loss":
            game_stats[user_id]["ttt_losses"] += 1
        elif result_type == "draw":
            game_stats[user_id]["ttt_draws"] += 1
    save_game_stats()
    print(f"Updated game stats for user {user_id}: {game_stats[user_id]}")

# --- Achievement Persistence ---
def load_achievements():
    global achievements
    achievements_raw = load_data(ACHIEVEMENTS_FILE, {})
    # Ensure user IDs are integers
    achievements = {int(user_id): data for user_id, data in achievements_raw.items()}
    print(f"Loaded achievements for {len(achievements)} users.")

def save_achievements():
    # Convert user IDs back to strings for JSON serialization
    save_data(ACHIEVEMENTS_FILE, {str(user_id): data for user_id, data in achievements.items()})

async def check_achievement(user_id, achievement_id, ctx=None):
    """Awards an achievement to a user if not already earned."""
    if user_id not in achievements:
        achievements[user_id] = []
    
    if achievement_id not in achievements[user_id]:
        achievements[user_id].append(achievement_id)
        save_achievements()
        achievement_name = ACHIEVEMENT_DEFINITIONS.get(achievement_id, achievement_id.replace('_', ' ').title())
        print(f"User {user_id} earned achievement: {achievement_name}")
        if ctx: # Send a message only if a context is available
            try:
                embed = discord.Embed(
                    title="Achievement Unlocked!",
                    description=f"🎉 Congratulations, {ctx.author.mention}! You've earned the achievement: **{achievement_name}**!",
                    color=discord.Color.gold(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="made by summers 2000")
                await ctx.send(embed=embed)
            except discord.Forbidden:
                print(f"Could not send achievement message to channel {ctx.channel.id} for user {user_id}.")
            except Exception as e:
                print(f"Error sending achievement message: {e}")

# --- DM Users Persistence ---
def load_dm_users():
    global DM_NOTIFIED_USERS
    dm_users_raw = load_data(DM_USERS_FILE, {})
    DM_NOTIFIED_USERS = {int(k): v for k, v in dm_users_raw.items()} # Ensure keys are ints
    print(f"Loaded DM users for {len(DM_NOTIFIED_USERS)} users.")

def save_dm_users():
    save_data(DM_USERS_FILE, {str(k): v for k, v in DM_NOTIFIED_USERS.items()})

# --- Notify Items Persistence ---
def load_notify_items():
    global notify_items
    notify_items_raw = load_data(NOTIFY_ITEMS_FILE, {})
    notify_items = {int(k): v for k, v in notify_items_raw.items()}
    print(f"Loaded notify items for {len(notify_items)} users.")

def save_notify_items():
    save_data(NOTIFY_ITEMS_FILE, {str(k): v for k, v in notify_items.items()})

# --- My Gardens Persistence ---
def load_my_gardens():
    global my_gardens
    my_gardens_raw = load_data(MY_GARDENS_FILE, {})
    my_gardens = {int(k): v for k, v in my_gardens_raw.items()}
    print(f"Loaded gardens for {len(my_gardens)} users.")

def save_my_gardens():
    save_data(MY_GARDENS_FILE, {str(k): v for k, v in my_gardens.items()})

# --- Reminders Persistence ---
def load_reminders():
    global reminders
    reminders_raw = load_data(REMINDERS_FILE, [])
    reminders = []
    for r in reminders_raw:
        try:
            # Convert timestamp string back to datetime object
            r['remind_time'] = datetime.fromisoformat(r['remind_time'])
            reminders.append(r)
        except (ValueError, KeyError) as e:
            print(f"Error loading reminder: {e}. Skipping entry.")
    reminders.sort(key=lambda x: x['remind_time']) # Ensure sorted after loading
    print(f"Loaded {len(reminders)} reminders.")

def save_reminders():
    # Convert datetime objects to ISO format strings for JSON serialization
    reminders_to_save = []
    for r in reminders:
        r_copy = r.copy()
        r_copy['remind_time'] = r_copy['remind_time'].isoformat()
        reminders_to_save.append(r_copy)
    save_data(REMINDERS_FILE, reminders_to_save)

# --- Lottery Persistence ---
def load_lotto_data():
    global LOTTO_TICKETS, LOTTO_POT
    lotto_data = load_data(LOTTO_FILE, {"tickets": {}, "pot": 0})
    LOTTO_TICKETS = {int(k): v for k, v in lotto_data.get("tickets", {}).items()}
    LOTTO_POT = lotto_data.get("pot", 0)
    print(f"Loaded lottery data. Pot: {LOTTO_POT}, Tickets: {LOTTO_TICKETS}")

def save_lotto_data():
    lotto_data = {
        "tickets": {str(k): v for k, v in LOTTO_TICKETS.items()},
        "pot": LOTTO_POT
    }
    save_data(LOTTO_FILE, lotto_data)


# --- Helper Functions for API Calls ---
async def fetch_api_data(url, method='GET', json_data=None):
    """Fetches data from a given API URL."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(method, url, json=json_data) as response:
                print(f"API Request: {method} {url}")
                print(f"API Response Status ({url}): {response.status}")
                
                # Check for successful response before trying to parse JSON
                response.raise_for_status() 

                try:
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        json_data = await response.json()
                        return json_data
                    else:
                        text_data = await response.text()
                        print(f"API Error: Expected JSON but received Content-Type '{content_type}' for {url}. Raw text: {text_data[:200]}...") # Log first 200 chars
                        return None
                except aiohttp.ContentTypeError: # This might still trigger if header is wrong but content is parseable, or vice versa
                    text_data = await response.text()
                    print(f"API Error: Content-Type is not application/json for {url} (or parsing failed). Raw text: {text_data[:200]}...")
                    return None
        except aiohttp.ClientResponseError as e:
            print(f"API Client Response Error (HTTP Status {e.status}) for {url}: {e.message}")
            return None
        except aiohttp.ClientConnectorError as e:
            print(f"API Client Connector Error (connection issue) for {url}: {e}")
            return None
        except aiohttp.ClientError as e:
            print(f"API Client Error (general aiohttp issue) for {url}: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during API fetch process for {url}: {e}")
            return None

# --- Helper Function to Create Stock Embed ---
def create_stock_embed(data, title="Current Stock Information"):
    """
    Creates a Discord Embed for stock data.
    'data' is expected to be a DICTIONARY containing different stock lists (e.g., 'seedsStock', 'eggStock').
    """
    embed = discord.Embed(
        title=title,
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    if not data:
        embed.description = "No stock information available at this time."
        return embed

    # Define the order of categories to display and their user-friendly names
    display_categories = {
        'seedsStock': "Seeds",
        'eggStock': "Eggs",
        'gearStock': "Gear",
        'cosmeticsStock': "Cosmetics",
        'honeyStock': "Bees & Honey", # Combined as per API structure
        'nightStock': "Night Stock"
    }

    found_any_stock_item = False
    for api_key, display_name in display_categories.items():
        category_data = data.get(api_key, [])
        if category_data:
            found_any_stock_item = True
            field_value = ""
            # Limit items per category to keep embed readable
            for item in category_data[:5]: # Display up to 5 items per category
                item_name = item.get('name', 'N/A')
                item_quantity = item.get('value', 'N/A')
                item_emoji = item.get('emoji', '')
                field_value += f"{item_emoji} {item_name}: **{item_quantity}**\n"

            if len(category_data) > 5:
                field_value += f"...and {len(category_data) - 5} more."

            embed.add_field(
                name=f"__**{display_name}**__",
                value=field_value if field_value else "No items in this category.",
                inline=True
            )

    if not found_any_stock_item:
        embed.description = "No stock information available across any categories at this time."

    return embed


# --- Events ---
@bot.event
async def on_ready():
    """Event that fires when the bot successfully connects to Discord."""
    global BOT_START_TIME
    BOT_START_TIME = datetime.utcnow() # Record start time
    print(f"Bot logged in as {bot.user.name} (ID: {bot.user.id})")
    print("Bot is ready to receive commands!")
    
    load_dm_users() # Load DM notification users on startup
    load_game_stats() # Load game stats
    load_achievements() # Load achievements
    load_notify_items() # Load specific item notifications
    load_my_gardens() # Load user garden data
    load_reminders() # Load reminders
    load_user_balances() # Load user balances for economy
    load_user_inventories() # Load user inventories for economy
    load_last_daily_claim() # Load last daily claim timestamps
    load_lotto_data() # Load lottery data

    # Start the autostock task when the bot is ready
    if not autostock_checker.is_running():
        autostock_checker.start()
        print("Autostock checker task started.")
    else:
        print("Autostock checker task is already running.")
    
    # Start the reminder checker task
    if not reminder_checker.is_running():
        reminder_checker.start()
        print("Reminder checker task started.")
    
    # Start the garden showcase task
    if not garden_showcase_poster.is_running():
        garden_showcase_poster.start()
        print("Garden showcase poster task started.")

@bot.event
async def on_command_error(ctx, error):
    """Handles errors that occur during command execution."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"**Oops!** You're missing an argument. Correct usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"**Invalid input!** One of your arguments was incorrect. Correct usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignore command not found errors to avoid spam
    elif isinstance(error, commands.MissingPermissions):
        missing_perms = [p.replace('_', ' ').title() for p in error.missing_permissions]
        await ctx.send(f"**Permission Denied!** You need the following permission(s) to use this command: `{', '.join(missing_perms)}`")
    elif isinstance(error, commands.BotMissingPermissions):
        missing_perms = [p.replace('_', ' ').title() for p in error.missing_permissions]
        await ctx.send(f"**I'm missing permissions!** I need the following permission(s) to execute this command: `{', '.join(missing_perms)}`")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command can only be used in a server channel, not in DMs.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"This command is on cooldown. Please try again in `{error.retry_after:.1f}` seconds.")
    elif isinstance(error, commands.CheckFailure): # Handle custom permission/role checks
        embed = discord.Embed(
            title="Permission Denied",
            description=f"You do not have the necessary permissions or role to use the `!{ctx.command.name}` command.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed, delete_after=10)
    else:
        print(f"An unhandled error occurred in command '{ctx.command.name}': {error}")
        embed = discord.Embed(
            title="Command Error",
            description=f"**An unexpected error occurred:** `{error}`. My apologies! Please try again later or contact an administrator.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for error embeds too
        await ctx.send(embed=embed)


# --- Stock Commands ---

@bot.command(name="stockall", aliases=["seed"]) # Renamed to !stockall, kept !seed as alias
@commands.cooldown(1, 10, commands.BucketType.channel)
async def get_all_stock(ctx):
    """
    Displays current stock information for all categories (seeds, eggs, gear, cosmetics, bee/honey, night).
    Usage: !stockall or !seed
    """
    try:
        await ctx.send("Fetching all stock information... please wait a moment.")
        all_stock_data = await fetch_api_data(STOCK_API_URL)
        if not all_stock_data:
            await ctx.send("Apologies, I couldn't retrieve stock information from the API. It might be down or experiencing issues, or returned no data. Please try again later!")
            return

        embed = create_stock_embed(all_stock_data, title="Comprehensive Stock Overview")
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in !stockall command: {e}")
        embed = discord.Embed(
            title="Error",
            description=f"An unexpected error occurred while processing the `!stockall` command: `{e}`",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)

@bot.command(name="stock")
@commands.cooldown(1, 10, commands.BucketType.channel) # 1 use per 10 seconds per channel
async def get_stock_by_category(ctx, category: str = None):
    """
    Displays current stock information for a specific category.
    Usage: !stock [category] (e.g., !stock seeds)
    Available categories: seeds, eggs, bees, cosmetics, gear, honey, night
    """
    if category is None:
        await ctx.send("Please specify a category. Available categories: `seeds`, `eggs`, `bees`, `cosmetics`, `gear`, `honey`, `night`.\nExample: `!stock seeds`")
        return

    # Map user-friendly input to API keys
    category_map = {
        'seeds': 'seedsStock',
        'eggs': 'eggStock',
        'bees': 'honeyStock', # API uses 'honeyStock' for bees
        'cosmetics': 'cosmeticsStock',
        'gear': 'gearStock',
        'honey': 'honeyStock',
        'night': 'nightStock'
    }

    api_category_key = category_map.get(category.lower())

    if not api_category_key:
        await ctx.send(f"**Invalid category!** Available categories are: {', '.join(category_map.keys())}. Please choose one of these.")
        return

    try:
        await ctx.send(f"Fetching {category} stock information... please wait a moment.")
        all_stock_data = await fetch_api_data(STOCK_API_URL)
        if not all_stock_data:
            await ctx.send("Apologies, I couldn't retrieve stock information from the API. It might be down or experiencing issues, or returned no data. Please try again later!")
            return

        # Access the specific stock list using the mapped key
        filtered_stock_data = all_stock_data.get(api_category_key, [])

        if not filtered_stock_data:
            await ctx.send(f"Currently, there are no `{category}` stock items available.")
            return

        # This embed only displays the specified category, which is correct for !stock <category>
        embed = discord.Embed(
            title=f"Current {category.capitalize()} Stock",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")

        # Display up to 5 items to keep the embed concise, or you can adjust this.
        for item in filtered_stock_data:
            item_name = item.get('name', 'N/A')
            item_quantity = item.get('value', 'N/A')
            item_image = item.get('image')
            item_emoji = item.get('emoji', '')

            field_value = f"Quantity: {item_quantity}"

            if item_image and isinstance(item_image, str) and not embed.thumbnail:
                embed.set_thumbnail(url=item_image)

            embed.add_field(
                name=f"{item_name} {item_emoji}",
                value=field_value,
                inline=True
            )
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in !stock command for category '{category}': {e}")
        embed = discord.Embed(
            title="Error",
            description=f"An unexpected error occurred while processing the `!stock {category}` command: `{e}`",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for error embeds too
        await ctx.send(embed=embed)

@bot.command(name="autostock")
@commands.has_permissions(manage_channels=True) # Requires "Manage Channels" permission to use
@commands.bot_has_permissions(send_messages=True, embed_links=True) # Bot needs to send messages and embeds
async def autostock_toggle(ctx, status: str = None):
    """
    Toggles automatic stock updates.
    Usage: !autostock on/off
    """
    global AUTOSTOCK_ENABLED, AUTOSTOCK_CHANNEL_ID

    if status is None:
        current_status = "enabled" if AUTOSTOCK_ENABLED else "disabled"
        channel_info = f" in <#{AUTOSTOCK_CHANNEL_ID}>" if AUTOSTOCK_ENABLED and AUTOSTOCK_CHANNEL_ID else ""
        await ctx.send(f"Auto-stock is currently **{current_status}**{channel_info}. Please specify `on` or `off` to toggle (e.g., `!autostock on`).")
        return

    status = status.lower()
    if status == "on":
        if AUTOSTOCK_ENABLED:
            if AUTOSTOCK_CHANNEL_ID != ctx.channel.id:
                    # If it's enabled but user wants to change channel
                    AUTOSTOCK_CHANNEL_ID = ctx.channel.id
                    await ctx.send(f"Auto-stock was already enabled, but the update channel has been changed to this one (<#{AUTOSTOCK_CHANNEL_ID}>).")
                    # Trigger an immediate check for the new channel
                    await autostock_checker()
            else:
                    await ctx.send("Auto-stock is already enabled in this channel.")
            return

        AUTOSTOCK_ENABLED = True
        AUTOSTOCK_CHANNEL_ID = ctx.channel.id # Set the channel dynamically to where the command was run
        await ctx.send(f"Auto-stock updates are now **enabled** and will be sent to this channel (<#{AUTOSTOCK_CHANNEL_ID}>).")
        # Trigger an immediate check when turned on, to send current stock
        await autostock_checker()
        await check_achievement(ctx.author.id, "FIRST_AUTOSTOCK_TOGGLE", ctx)
    elif status == "off":
        if not AUTOSTOCK_ENABLED:
            await ctx.send("Auto-stock is already disabled.")
            return
        AUTOSTOCK_ENABLED = False
        AUTOSTOCK_CHANNEL_ID = None # Clear the channel ID when turned off
        await ctx.send("Auto-stock updates are now **disabled**.")
    else:
        await ctx.send("Invalid status provided. Please use `on` or `off`.")

@tasks.loop(seconds=5) # Checks every 5 seconds for immediate updates
async def autostock_checker():
    """Background task to check for new stock updates."""
    global AUTOSTOCK_ENABLED, LAST_STOCK_DATA, AUTOSTOCK_CHANNEL_ID, STOCK_LOGS, LAST_KNOWN_DM_ITEM_STATUS, DM_NOTIFIED_USERS, notify_items

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Autostock checker: Fetching stock data...")
    current_stock_data = await fetch_api_data(STOCK_API_URL)

    if current_stock_data is None:
        print("Autostock: Failed to fetch current stock data. Skipping update for this cycle.")
        # Don't return here, as DM notifications might still work if API was only temporarily down
        return # Skip further processing if API call failed

    # Helper to normalize the ENTIRE stock data for comparison (order-independent comparison of all items)
    def normalize_full_stock_data(data):
        if not data:
            return frozenset()

        normalized_items = []
        for category_key, items_list in data.items():
            # Skip 'lastSeen' as it's metadata, not actual stock, and any other non-list top-level keys
            if category_key == 'lastSeen' or not isinstance(items_list, list):
                continue
            
            for item in items_list:
                # Convert each item dict to a frozenset of its key-value pairs for hashability
                # Exclude 'image' and 'emoji' from comparison as they don't signify a stock change
                comparable_item = {k: v for k, v in item.items() if k not in ['image', 'emoji']}
                normalized_items.append(frozenset(comparable_item.items()))
        return frozenset(normalized_items)

    normalized_current = normalize_full_stock_data(current_stock_data)
    normalized_last = normalize_full_stock_data(LAST_STOCK_DATA)

    # Check if stock data has genuinely changed or if it's the first run
    if LAST_STOCK_DATA is None or normalized_current != normalized_last:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Autostock checker: Overall stock change detected!")
        if AUTOSTOCK_ENABLED and AUTOSTOCK_CHANNEL_ID is not None:
            channel = bot.get_channel(AUTOSTOCK_CHANNEL_ID)
            if channel:
                # Create a single embed for all relevant stock types
                embed = create_stock_embed(current_stock_data, title="New Shop Stock Update!")
                try:
                    await channel.send(embed=embed)
                    print(f"Autostock: New stock detected and sent to channel {channel.name} ({channel.id}).")

                    # Log the stock change for seeds only
                    stock_time = datetime.now()
                    seeds_in_current_stock = current_stock_data.get('seedsStock', [])
                    seeds_in_last_stock = LAST_STOCK_DATA.get('seedsStock', []) if LAST_STOCK_DATA else []
                    
                    normalized_current_seeds = frozenset(
                        frozenset({k: v for k, v in item.items() if k not in ['image', 'emoji']}.items())
                        for item in seeds_in_current_stock
                    )
                    normalized_last_seeds = frozenset(
                        frozenset({k: v for k, v in item.items() if k not in ['image', 'emoji']}.items())
                        for item in seeds_in_last_stock
                    )

                    if normalized_current_seeds != normalized_last_seeds:
                        seeds_log_details = []
                        if seeds_in_current_stock:
                            item_names = [item.get('name', 'Unknown') for item in seeds_in_current_stock]
                            seeds_log_details.append(f"Seeds: {', '.join(item_names)}")
                        
                        seeds_log_entry = " | ".join(seeds_log_details) if seeds_log_details else "No specific seed changes to report."
                        STOCK_LOGS.append({'time': stock_time, 'details': seeds_log_entry})
                        # Keep only the last 10 logs (or adjust as needed)
                        if len(STOCK_LOGS) > 10:
                            STOCK_LOGS.pop(0) # Remove the oldest log

                except discord.Forbidden:
                    print(f"Autostock: Bot does not have permission to send messages/embeds in channel {channel.name} ({channel.id}). Please check bot permissions!")
                except Exception as e:
                    print(f"Autostock: An unexpected error occurred while sending embed: {e}")
            else:
                print(f"Autostock: Configured channel with ID {AUTOSTOCK_CHANNEL_ID} not found or inaccessible. Disabling autostock.")
                AUTOSTOCK_ENABLED = False
        else:
            print("Autostock: Not enabled or channel not set, skipping public channel update.")

        # Always update LAST_STOCK_DATA with the full, new data after comparison and potential notification
        LAST_STOCK_DATA = current_stock_data
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Autostock checker: No overall stock change detected.")


    # --- DM Notification Specific Logic (for categories and specific items) ---
    for api_category_key, monitor_info in DM_MONITORED_CATEGORIES.items():
        dm_type = monitor_info["type"]
        monitored_items_list = monitor_info["items"]

        category_stock = current_stock_data.get(api_category_key, [])
        
        currently_available_dm_items = {
            item['name'] for item in category_stock
            if item['name'] in monitored_items_list and item.get('value', 0) > 0
        }

        # Check for newly in-stock items compared to last known status
        newly_in_stock_for_dm = currently_available_dm_items - LAST_KNOWN_DM_ITEM_STATUS.get(api_category_key, set())

        if newly_in_stock_for_dm:
            log_channel = bot.get_channel(DM_NOTIFICATION_LOG_CHANNEL_ID)
            if log_channel:
                log_message = f"**{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} - New DM-Monitored {dm_type.capitalize()} In Stock:**\n"
                for item_name in newly_in_stock_for_dm:
                    log_message += f"- `{item_name}` is now in stock!\n"
                try:
                    await log_channel.send(log_message)
                    print(f"Logged new DM-monitored items to channel {log_channel.name} ({log_channel.id}).")
                except discord.Forbidden:
                    print(f"Bot does not have permission to send messages in DM notification log channel {log_channel.id}.")
                except Exception as e:
                    print(f"Error sending log to DM notification channel: {e}")

            dm_embed = discord.Embed(
                title=f"GrowAGarden Stock Alert! ({dm_type.capitalize()})",
                description=f"The following {dm_type} you're monitoring are now in stock:",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            dm_embed.set_footer(text="made by summers 2000")

            for item_name in newly_in_stock_for_dm:
                dm_embed.add_field(name=f"✅ {item_name}", value="Available now!", inline=False)

            # Send DMs to users who have this category enabled
            for user_id, preferences in DM_NOTIFIED_USERS.items():
                if preferences.get(dm_type, False):
                    user = bot.get_user(user_id)
                    if user is None:
                        try:
                            user = await bot.fetch_user(user_id)
                        except discord.NotFound:
                            print(f"DM User {user_id} not found. Skipping DM for category {dm_type}.")
                            continue
                        except Exception as e:
                            print(f"Error fetching DM user {user_id} for category {dm_type}: {e}. Skipping DM.")
                            continue

                    if user:
                        try:
                            await user.send(embed=dm_embed)
                            print(f"Sent DM notification to {user.name} ({user.id}) for new {dm_type}.")
                            await check_achievement(user.id, "FIRST_DM_NOTIFICATION", None) # No ctx for DM
                        except discord.Forbidden:
                            print(f"Could not send DM to {user.name} ({user.id}). User has DMs disabled or blocked bot.")
                        except Exception as e:
                            print(f"An unexpected error occurred while sending DM to {user.name} ({user.id}): {e}")

        # Update the last known status for this category AFTER sending DMs
        LAST_KNOWN_DM_ITEM_STATUS[api_category_key] = currently_available_dm_items
    
    # Specific Item DM Notification Check
    for user_id, monitored_item_name in list(notify_items.items()): # Use list() to avoid RuntimeError if dict changes during iteration
        # Iterate through all stock categories to find the item
        found_item_in_stock = False
        for category_key, items_list in current_stock_data.items():
            if category_key == 'lastSeen' or not isinstance(items_list, list): continue
            
            for item in items_list:
                if item.get('name', '').lower() == monitored_item_name.lower() and item.get('value', 0) > 0:
                    found_item_in_stock = True
                    break
            if found_item_in_stock:
                break
        
        # This acts as the "last known status" for individual notify items
        last_item_status_for_user = LAST_KNOWN_DM_ITEM_STATUS.get(f"notifyItem_{user_id}", set())
        
        if found_item_in_stock and monitored_item_name not in last_item_status_for_user:
            # Item is newly in stock for this user
            user = bot.get_user(user_id)
            if user is None:
                try:
                    user = await bot.fetch_user(user_id)
                except discord.NotFound:
                    print(f"NotifyItem DM User {user_id} not found. Skipping DM for item '{monitored_item_name}'.")
                    continue
                except Exception as e:
                    print(f"Error fetching NotifyItem DM user {user_id} for item '{monitored_item_name}': {e}. Skipping DM.")
                    continue

            if user:
                dm_embed = discord.Embed(
                    title="GrowAGarden Item Alert!",
                    description=f"Your monitored item **{monitored_item_name}** is now in stock!",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                dm_embed.set_footer(text="made by summers 2000")
                try:
                    await user.send(embed=dm_embed)
                    print(f"Sent DM notification to {user.name} ({user.id}) for item '{monitored_item_name}'.")
                    await check_achievement(user.id, "FIRST_DM_NOTIFICATION", None) # Could make a specific one for this too
                except discord.Forbidden:
                    print(f"Could not send DM to {user.name} ({user.id}). DMs disabled for item notification.")
                except Exception as e:
                    print(f"An unexpected error occurred while sending item DM to {user.name} ({user.id}): {e}")
        
        # Update specific item status for this user
        if found_item_in_stock:
            LAST_KNOWN_DM_ITEM_STATUS[f"notifyItem_{user_id}"] = {monitored_item_name}
        else:
            LAST_KNOWN_DM_ITEM_STATUS[f"notifyItem_{user_id}"] = set()


@autostock_checker.before_loop
async def before_autostock_checker():
    """Waits for the bot to be ready before starting the autostock loop."""
    await bot.wait_until_ready() # Ensures bot is connected before fetching data

@bot.command(name="restocklogs")
@commands.cooldown(1, 10, commands.BucketType.user) # 1 use per 10 seconds per user
async def restock_logs(ctx):
    """
    Displays the logs of past stock changes.
    Usage: !restocklogs
    """
    if not STOCK_LOGS:
        await ctx.send("No seed stock logs available yet. The autostock feature needs to be `on` for a while to gather logs.")
        return

    embed = discord.Embed(
        title="Recent Seed Stock Change Logs", # Updated title for clarity
        description="Showing the latest **seed** stock changes:",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000") # Footer for this embed

    # Display logs in reverse order (most recent first)
    for log in reversed(STOCK_LOGS):
        time_str = log['time'].strftime("%Y-%m-%d %H:%M:%S UTC")
        embed.add_field(
            name=f"Change detected at {time_str}",
            value=f"`{log['details']}`", # Added backticks for monospace font
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="restock") # Changed to lowercase !restock
@commands.cooldown(1, 10, commands.BucketType.channel)
async def next_restock_time(ctx):
    """
    Shows the next planned restock time.
    Usage: !restock
    """
    try:
        await ctx.send("Fetching next restock time... please wait a moment.")
        restock_data = await fetch_api_data(RESTOCK_TIME_API_URL)

        if not restock_data:
            await ctx.send("Apologies, I couldn't retrieve the next restock time. The API might be down or returned no data. Please ensure the API is running and accessible.")
            return

        # Check for specific keys that might indicate an error or unexpected format
        # The API is documented to return 'timeUntilRestock' (seconds) and 'humanReadableTime'
        if 'timeUntilRestock' not in restock_data or 'humanReadableTime' not in restock_data:
            print(f"API Error: Missing expected keys in Restock-Time API response. Raw data: {restock_data}")
            await ctx.send("Apologies, the restock API returned data in an unexpected format. Expected `timeUntilRestock` and `humanReadableTime`. Please try again later or contact an administrator.")
            return

        time_until_restock = restock_data.get('timeUntilRestock', 'N/A')
        human_readable_time = restock_data.get('humanReadableTime', 'N/A')

        if time_until_restock == 'N/A' or human_readable_time == 'N/A':
             await ctx.send("The restock data was incomplete. Please try again or check the API.")
             return

        embed = discord.Embed(
            title="Next Restock Time",
            description=f"The shop will restock in approximately: `{human_readable_time}`",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Error in !restock command: {e}")
        embed = discord.Embed(
            title="Error",
            description=f"An unexpected error occurred while processing the `!restock` command: `{e}`",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)

# --- Weather Command ---
@bot.command(name="weather")
@commands.cooldown(1, 15, commands.BucketType.channel) # Cooldown to prevent API spam
async def get_weather(ctx):
    """
    Displays current in-game weather conditions (e.g., Rain, Sunny, Thunder).
    Usage: !weather
    """
    try:
        await ctx.send("Fetching current in-game weather... please wait a moment.")
        weather_data = await fetch_api_data(WEATHER_API_URL)

        if not weather_data:
            await ctx.send("Apologies, I couldn't retrieve weather information from the API. It might be down or experiencing issues, or returned no data. Please try again later!")
            return

        # Extracting relevant data: location and description (which should be the weather type)
        location = weather_data.get('location', 'Grow A Garden') # Default to "Grow A Garden"
        description = weather_data.get('description', 'Unknown weather conditions.')
        icon_url = weather_data.get('icon', None) # Icon for the weather type

        embed = discord.Embed(
            title=f"Current In-Game Weather in {location}",
            description=f"**Conditions:** `{description.capitalize()}`",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if icon_url:
            embed.set_thumbnail(url=icon_url)

        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Error in !weather command: {e}")
        embed = discord.Embed(
            title="Error",
            description=f"An unexpected error occurred while processing the `!weather` command: `{e}`",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)

# --- Uptime Command ---
@bot.command(name="uptime")
async def uptime_command(ctx):
    """
    Shows how long the bot has been online.
    Usage: !uptime
    """
    global BOT_START_TIME
    current_time = datetime.utcnow()
    uptime = current_time - BOT_START_TIME

    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    seconds = uptime.seconds % 60

    uptime_string = []
    if days > 0:
        uptime_string.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        uptime_string.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        uptime_string.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 or not uptime_string: # Include seconds if less than a minute, or if uptime is very short
        uptime_string.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    final_uptime = ", ".join(uptime_string)

    embed = discord.Embed(
        title="Bot Uptime",
        description=f"I have been online for: `{final_uptime}`",
        color=discord.Color.purple(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)


# --- Moderation Commands ---

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Bans a member from the server.
    Usage: !ban <@user> [reason]
    """
    if member == ctx.author:
        await ctx.send("You cannot ban yourself, silly!")
        return
    if member == bot.user:
        await ctx.send("I cannot ban myself. That would be quite counterproductive!")
        return
    # Check if the target member has a higher or equal role than the commander
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot ban someone with an equal or higher role than yourself.")
        return
    # Check if the target member has a higher or equal role than the bot
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("I cannot ban this user as their role is equal to or higher than my top role. Please adjust my role hierarchy.")
        return

    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="Member Banned",
            description=f"Successfully banned **{member.display_name}** for: `{reason}`",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for this embed
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to ban this user. Make sure my role is higher than theirs and I have the 'Ban Members' permission.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to ban **{member.display_name}**: `{e}`")

@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def unban_command(ctx, *, user_id: int):
    """
    Unbans a user by their ID.
    Usage: !unban <user_id>
    """
    try:
        user = discord.Object(id=user_id) # Create a partial user object from ID
        await ctx.guild.unban(user)

        # Try to fetch user details to display in embed
        try:
            unbanned_user = await bot.fetch_user(user_id)
            user_name = unbanned_user.name
            user_mention = unbanned_user.mention
        except discord.NotFound:
            user_name = f"User ID {user_id}"
            user_mention = f"<@{user_id}>"

        embed = discord.Embed(
            title="Member Unbanned",
            description=f"Successfully unbanned **{user_name}** ({user_mention}).",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)
    except discord.NotFound:
        await ctx.send(f"User with ID `{user_id}` is not found in the ban list.")
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to unban users. Make sure I have the 'Ban Members' permission.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to unban `{user_id}`: `{e}`")


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Kicks a member from the server.
    Usage: !kick <@user> [reason]
    """
    if member == ctx.author:
        await ctx.send("You cannot kick yourself, that's not how it works!")
        return
    if member == bot.user:
        await ctx.send("I cannot kick myself. I like it here!")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot kick someone with an equal or higher role than yourself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("I cannot kick this user as their role is equal to or higher than my top role. Please adjust my role hierarchy.")
        return

    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="Member Kicked",
            description=f"Successfully kicked **{member.display_name}** for: `{reason}`",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for this embed
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to kick this user. Make sure my role is higher than theirs and I have the 'Kick Members' permission.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to kick **{member.display_name}**: `{e}`")

@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def mute_command(ctx, member: discord.Member, duration_minutes: int = 0, *, reason: str = "No reason provided"):
    """
    Mutes a member by assigning a 'Muted' role.
    Usage: !mute <@user> [duration_minutes] [reason]
    Duration in minutes. If 0 or omitted, mute is permanent until unmuted.
    """
    # !!! IMPORTANT !!!
    # You MUST create a role named exactly "Muted" in your Discord server.
    # Configure this role to have no "Send Messages" permissions in your channels.
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

    if not muted_role:
        await ctx.send("**Error:** The 'Muted' role was not found. Please create a role named `Muted` with no permissions and try again.")
        return

    if muted_role in member.roles:
        await ctx.send(f"**{member.display_name}** is already muted.")
        return

    if member == ctx.author:
        await ctx.send("You cannot mute yourself.")
        return
    if member == bot.user:
        await ctx.send("I cannot mute myself. I need to talk!")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot mute someone with an equal or higher role than yourself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("I cannot mute this user as their role is equal to or higher than my top role. Please adjust my role hierarchy.")
        return

    try:
        await member.add_roles(muted_role, reason=reason)
        mute_message_desc = f"Successfully muted **{member.display_name}** for: `{reason}`"
        if duration_minutes > 0:
            mute_message_desc += f"\nThis mute will last for `{duration_minutes}` minutes."

        embed = discord.Embed(
            title="Member Muted",
            description=mute_message_desc,
            color=discord.Color.light_grey(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for this embed
        await ctx.send(embed=embed)

        if duration_minutes > 0:
            await asyncio.sleep(duration_minutes * 60)
            # After duration, check if user is still muted and unmute
            if muted_role in member.roles: # Ensure they weren't manually unmuted already
                await member.remove_roles(muted_role, reason="Mute duration expired")
                unmute_embed = discord.Embed(
                    title="Member Unmuted (Automatic)",
                    description=f"Unmuted **{member.display_name}** (mute duration expired).",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                unmute_embed.set_footer(text="made by summers 2000") # Footer for this embed
                await ctx.send(embed=unmute_embed)
            else:
                print(f"{member.display_name} was manually unmuted before duration expired.")

    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to manage roles. Make sure my role is higher than the 'Muted' role and the user's role.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to mute **{member.display_name}**: `{e}`")


@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def unmute_command(ctx, member: discord.Member):
    """
    Unmutes a member by removing the 'Muted' role.
    Usage: !unmute <@user>
    """
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

    if not muted_role:
        await ctx.send("**Error:** The 'Muted' role was not found. Please create a role named `Muted`.")
        return

    if muted_role not in member.roles:
        await ctx.send(f"**{member.display_name}** is not currently muted.")
        return

    try:
        await member.remove_roles(muted_role, reason="Unmuted by moderator")
        embed = discord.Embed(
            title="Member Unmuted",
            description=f"Successfully unmuted **{member.display_name}**.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for this embed
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to manage roles. Make sure my role is higher than the 'Muted' role.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to unmute **{member.display_name}**: `{e}`")

@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def slowmode_command(ctx, seconds: int):
    """
    Sets slowmode for the current channel.
    Usage: !slowmode <seconds> (0 to disable)
    """
    if seconds < 0 or seconds > 21600: # Discord's limit is 6 hours (21600 seconds)
        await ctx.send("Slowmode duration must be between 0 and 21600 seconds (6 hours).")
        return

    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        embed = discord.Embed(
            title="Slowmode Update",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for this embed

        if seconds == 0:
            embed.description = "Slowmode has been **disabled** in this channel."
        else:
            embed.description = f"Slowmode set to `{seconds}` seconds in this channel."
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to manage channels. Please ensure I have the 'Manage Channels' permission.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to set slowmode: `{e}`")

@bot.command(name="clear", aliases=["purge"])
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True, read_message_history=True) # Bot needs to read history to purge
async def clear_messages(ctx, amount: int):
    """
    Clears a specified amount of messages from the channel.
    Usage: !clear <amount>
    """
    if amount <= 0:
        await ctx.send("Please specify a positive number of messages to delete.")
        return
    if amount > 100: # Discord API limit for purge is 100 messages at once
        await ctx.send("I can only clear up to 100 messages at a time.")
        return

    try:
        # Add 1 to amount to delete the command message itself
        deleted = await ctx.channel.purge(limit=amount + 1)

        embed = discord.Embed(
            title="Messages Cleared",
            description=f"Successfully deleted `{len(deleted) - 1}` message(s).",
            color=discord.Color.dark_teal(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000") # Footer for this embed

        # Send a confirmation message that deletes itself after a few seconds
        await ctx.send(embed=embed, delete_after=5)
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to manage messages in this channel. Please ensure I have 'Manage Messages' and 'Read Message History'.")
    except discord.HTTPException as e:
        if "messages older than 14 days" in str(e):
            await ctx.send("I cannot delete messages older than 14 days using this command.")
        else:
            await ctx.send(f"An API error occurred while trying to clear messages: `{e}`")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to clear messages: `{e}")


@bot.command(name="cmds", aliases=["commands", "help"])
async def help_command(ctx):
    """
    Displays a list of all available commands.
    Usage: !cmds
    """
    embed = discord.Embed(
        title="GrowAGarden Bot Commands", # Changed "Sacrificed" to "GrowAGarden"
        description="Here's a list of all available commands and their usage:",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    # --- Stock & Auto-Stock Commands ---
    stock_commands_desc = (
        f"`!stockall` (or `!seed`): Displays a comprehensive overview of all current stock.\n"
        f"`!stock <category>`: Shows stock for a specific category. (e.g., `!stock seeds`)\n"
        f"Available categories: `seeds`, `eggs`, `bees`, `cosmetics`, `gear`, `honey`, `night`\n"
        f"`!autostock <on/off>`: Toggles automatic stock updates to the current channel.\n"
        f"`!restocklogs`: Shows recent stock change history.\n"
        f"`!restock`: Shows the next planned restock time."
    )
    embed.add_field(name="__Stock & Auto-Stock Commands__", value=stock_commands_desc, inline=False)

    # --- Moderation Commands ---
    moderation_commands_desc = (
        f"`!ban <@user> [reason]`: Bans a member from the server.\n"
        f"`!unban <user_id>`: Unbans a user by their ID.\n"
        f"`!kick <@user> [reason]`: Kicks a member from the server.\n"
        f"`!mute <@user> [duration_minutes] [reason]`: Mutes a member. Requires a 'Muted' role.\n"
        f"`!unmute <@user>`: Unmutes a member.\n"
        f"`!slowmode <seconds> (0 to disable)`: Sets slowmode for the channel.\n"
        f"`!clear <amount>` (or `!purge`): Deletes a specified number of messages (max 100).\n"
        f"`!auditlog <action_type> [user]`: Views recent server audit log entries. (Requires `View Audit Log` permission)"
    )
    embed.add_field(name="__Moderation Commands__", value=moderation_commands_desc, inline=False)

    # --- Utility Commands ---
    utility_commands_desc = (
        f"`!weather`: Displays current in-game weather conditions (e.g., Rain, Sunny).\n"
        f"`!uptime`: Shows how long the bot has been online.\n"
        f"`!rblxusername <username>`: Finds a Roblox player's profile by username.\n"
        f"`!remindme <time> <message>`: Sets a personal reminder (e.g., `!remindme 1h Check crops`).\n"
        f"`!notifyitem <item_name>`: Toggles DM notifications for a specific item (run again to disable/change).\n"
        f"`!mygarden`: Shows your saved garden showcase.\n"
        f"`!setgarden <description> [image_url]`: Sets your garden showcase description and optional image.\n"
        f"`!showgardens`: Manually triggers a random garden showcase post.\n" # Added !showgardens command
        f"`!myachievements`: Displays your earned achievements."
    )
    embed.add_field(name="__Utility Commands__", value=utility_commands_desc, inline=False)

    # --- Game Commands ---
    game_commands_desc = (
        f"`!c4 <@opponent>`: Starts a game of Connect4.\n"
        f"`!tictactoe <@opponent>`: Starts a game of Tic-Tac-Toe.\n"
        f"`!gamestats`: Shows your Connect4 and Tic-Tac-Toe game statistics.\n"
        f"`!c4leaderboard`: Shows the Connect4 server leaderboard.\n"
        f"`!tttleaderboard`: Shows the Tic-Tac-Toe server leaderboard.\n"
        f"`!roll [number]`: Rolls a dice or a number between 1 and [number] (default 100).\n"
        f"`!lotto <buy [tickets] | draw | status>`: Interact with the server lottery. Costs {LOTTO_TICKET_PRICE} coins per ticket."
    )
    embed.add_field(name="__Game Commands__", value=game_commands_desc, inline=False)

    # --- DM Notification Commands ---
    dm_notify_commands_desc = (
        f"`!seedstockdm`: Toggles DM notifications for Beanstalk, Pepper, and Mushroom seeds. (Requires role ID: `{DM_NOTIFY_ROLE_ID}` OR `{DM_BYPASS_ROLE_ID}`)\n"
        f"`!gearstockdm`: Toggles DM notifications for Master Sprinkler and Lightning Rod. (Requires role ID: `{DM_NOTIFY_ROLE_ID}` OR `{DM_BYPASS_ROLE_ID}`)"
    )
    embed.add_field(name="__DM Notification Commands__", value=dm_notify_commands_desc, inline=False)

    # --- Ban Request Command ---
    ban_request_desc = (
        f"`!banrequest`: Initiates a ban request process via DM. Costs $10."
    )
    embed.add_field(name="__Ban Request Command__", value=ban_request_desc, inline=False)

    # --- Economy Commands ---
    economy_commands_desc = (
        f"`!balance`: Check your current coin balance.\n"
        f"`!daily`: Claim your daily coin bonus.\n"
        f"`!transfer <@user> <amount>`: Send coins to another user.\n"
        f"`!shop [category]`: View items available for purchase.\n"
        f"`!buy <item_name> [quantity]`: Buy an item from the shop.\n"
        f"`!sell <item_name> [quantity]`: Sell an item from your inventory.\n"
        f"`!inventory`: View your current items.\n"
        f"`!use <item_name>`: Use a consumable item from your inventory.\n"
        f"`!craft <recipe_name>`: Craft an item from ingredients.\n"
        f"`!recipes`: View available crafting recipes.\n"
        f"`!iteminfo <item_name>`: Get information about a specific item.\n"
        f"`!richest`: See the top users by coin balance.\n"
        f"`!coinflip <amount> [heads/tails]`: Bet coins on a coin flip (heads/tails is optional)."
    )
    embed.add_field(name="__Economy Commands__", value=economy_commands_desc, inline=False)


    await ctx.send(embed=embed)

# --- DM Notification Command for Seeds ---
@bot.command(name="seedstockdm")
@commands.guild_only()
@commands.check_any(commands.has_role(DM_NOTIFY_ROLE_ID), commands.has_role(DM_BYPASS_ROLE_ID))
async def seed_stock_dm_toggle(ctx):
    """
    Toggles DM notifications for Beanstalk, Pepper, and Mushroom seeds.
    Only works for users with a specific role ID or the bypass role.
    Usage: !seedstockdm
    """
    user_id = ctx.author.id
    # Initialize user's preferences if they don't exist
    if user_id not in DM_NOTIFIED_USERS:
        DM_NOTIFIED_USERS[user_id] = {"seeds": False, "gear": False} # Ensure all types are initialized

    current_status = DM_NOTIFIED_USERS[user_id].get("seeds", False)
    DM_NOTIFIED_USERS[user_id]["seeds"] = not current_status

    status_message = "enabled" if DM_NOTIFIED_USERS[user_id]["seeds"] else "disabled"
    color = discord.Color.green() if DM_NOTIFIED_USERS[user_id]["seeds"] else discord.Color.red()

    save_dm_users() # Save the updated state

    embed = discord.Embed(
        title="Seed DM Notification Status",
        description=f"Your DM notifications for Beanstalk, Pepper, and Mushroom seeds have been **{status_message}**.",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    try:
        await ctx.author.send(f"Your GrowAGarden **seed** stock DM notifications are now **{status_message}**.")
    except discord.Forbidden:
        print(f"Could not DM user {ctx.author.id} for seedstockdm toggle. DMs disabled.")

    if status_message == "enabled":
        await check_achievement(user_id, "FIRST_DM_NOTIFICATION", ctx)

# --- DM Notification Command for Gear ---
@bot.command(name="gearstockdm")
@commands.guild_only()
@commands.check_any(commands.has_role(DM_NOTIFY_ROLE_ID), commands.has_role(DM_BYPASS_ROLE_ID))
async def gear_stock_dm_toggle(ctx):
    """
    Toggles DM notifications for specific gear items.
    Only works for users with a specific role ID or the bypass role.
    Usage: !gearstockdm
    """
    user_id = ctx.author.id
    # Initialize user's preferences if they don't exist
    if user_id not in DM_NOTIFIED_USERS:
        DM_NOTIFIED_USERS[user_id] = {"seeds": False, "gear": False} # Ensure all types are initialized

    current_status = DM_NOTIFIED_USERS[user_id].get("gear", False)
    DM_NOTIFIED_USERS[user_id]["gear"] = not current_status

    status_message = "enabled" if DM_NOTIFIED_USERS[user_id]["gear"] else "disabled"
    color = discord.Color.green() if DM_NOTIFIED_USERS[user_id]["gear"] else discord.Color.red()

    save_dm_users() # Save the updated state

    embed = discord.Embed(
        title="Gear DM Notification Status",
        description=f"Your DM notifications for Master Sprinkler and Lightning Rod have been **{status_message}**.",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    try:
        await ctx.author.send(f"Your GrowAGarden **gear** stock DM notifications are now **{status_message}**.")
    except discord.Forbidden:
        print(f"Could not DM user {ctx.author.id} for gearstockdm toggle. DMs disabled.")

    if status_message == "enabled":
        await check_achievement(user_id, "FIRST_DM_NOTIFICATION", ctx)

# --- Specific Item DM Notification Command ---
@bot.command(name="notifyitem")
@commands.guild_only()
@commands.check_any(commands.has_role(DM_NOTIFY_ROLE_ID), commands.has_role(DM_BYPASS_ROLE_ID))
async def notify_item_toggle(ctx, *, item_name: str):
    """
    Toggles DM notifications for a specific item (seed, gear, egg, etc.).
    Run the command again with the same item name to disable.
    Usage: !notifyitem <item name>
    """
    user_id = ctx.author.id
    current_monitored_item = notify_items.get(user_id)

    if current_monitored_item and current_monitored_item.lower() == item_name.lower():
        # User is already monitoring this item, so disable it
        del notify_items[user_id]
        status_message = "disabled"
        color = discord.Color.red()
        await ctx.send(f"Your DM notification for **{item_name}** has been **disabled**.")
        try:
            await ctx.author.send(f"Your GrowAGarden notification for **{item_name}** is now **disabled**.")
        except discord.Forbidden:
            print(f"Could not DM user {ctx.author.id} for notifyitem toggle. DMs disabled.")
    else:
        # Enable monitoring for this new item or change from a different item
        notify_items[user_id] = item_name
        status_message = "enabled"
        color = discord.Color.green()
        if current_monitored_item:
            await ctx.send(f"Your DM notification has been switched to **{item_name}** (was: {current_monitored_item}).")
            try:
                await ctx.author.send(f"Your GrowAGarden notification is now for **{item_name}** (was: {current_monitored_item}).")
            except discord.Forbidden:
                print(f"Could not DM user {ctx.author.id} for notifyitem change. DMs disabled.")
        else:
            await ctx.send(f"Your DM notification for **{item_name}** has been **enabled**.")
            try:
                await ctx.author.send(f"Your GrowAGarden notification for **{item_name}** is now **enabled**.")
            except discord.Forbidden:
                print(f"Could not DM user {ctx.author.id} for notifyitem enable. DMs disabled.")
        await check_achievement(user_id, "FIRST_DM_NOTIFICATION", ctx) # Could make a specific one for this too

    save_notify_items()

# --- Roblox Username Lookup Command ---
@bot.command(name="rblxusername")
@commands.check_any(commands.has_permissions(manage_roles=True), commands.has_role(1302076375922118696))
@commands.bot_has_permissions(send_messages=True, embed_links=True) # Bot needs to send messages and embeds
async def rblxusername(ctx, *, username: str):
    """
    Finds a Roblox player's profile by their username.
    Displays avatar, username, user ID, online/offline status, followers, friends,
    date joined, following, display name, and about me.
    Usage: !rblxusername <Roblox Username>
    """
    # The permission check is now handled by the decorators above.
    # No need for manual role check here.

    await ctx.send(f"Searching for Roblox user '{username}'... please wait.")

    try:
        # Step 1: Get User ID from Username
        username_api_url = "https://users.roblox.com/v1/usernames/users"
        payload = {"usernames": [username], "excludeBannedUsers": False}
        user_data_response = await fetch_api_data(username_api_url, method='POST', json_data=payload)

        if not user_data_response or not user_data_response.get('data'):
            await ctx.send(f"Could not find a Roblox user with the username: `{username}`. Please check the spelling.")
            return

        user_id = user_data_response['data'][0]['id']
        found_username = user_data_response['data'][0]['name']
        display_name = user_data_response['data'][0]['displayName']

        # Step 2: Get User Profile Details
        profile_api_url = f"https://users.roblox.com/v1/users/{user_id}"
        profile_data = await fetch_api_data(profile_api_url)

        if not profile_data:
            await ctx.send(f"Could not retrieve full profile details for user ID `{user_id}`. The Roblox API might be experiencing issues.")
            return

        # Step 3: Get User's Avatar
        avatar_api_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=48x48&format=Png&isCircular=false"
        avatar_data = await fetch_api_data(avatar_api_url)
        avatar_url = avatar_data['data'][0]['imageUrl'] if avatar_data and avatar_data.get('data') else None

        # Step 4: Get User's Presence (Online/Offline)
        presence_api_url = "https://presence.roblox.com/v1/presence/users"
        presence_payload = {"userIds": [user_id]}
        presence_data = await fetch_api_data(presence_api_url, method='POST', json_data=presence_payload)
        
        online_status = "Offline"
        if presence_data and presence_data.get('userPresences'):
            # Check for LastLocation and LastOnline for more detailed status
            user_presence = presence_data['userPresences'][0]
            if user_presence.get('userPresenceType') == 2: # 2 means InGame
                online_status = f"Online (Playing: {user_presence.get('lastLocation', 'Unknown Game')})"
            elif user_presence.get('userPresenceType') == 1: # 1 means Online
                online_status = "Online (Website)"
            elif user_presence.get('userPresenceType') == 0: # 0 means Offline
                online_status = "Offline"
            else:
                online_status = "Unknown Status" # Fallback for other types

        # Step 5: Get User's Friends and Followers/Following Counts
        # Note: Roblox API for friends/followers is often paginated and complex.
        # For simple counts, we might need to hit specific endpoints or infer.
        # For this example, we'll use simplified endpoints if available or default to N/A.
        # The profile_data usually contains some basic info.
        
        # Let's try to fetch these counts if possible
        followers_count = "N/A"
        following_count = "N/A"
        friends_count = "N/A"

        try:
            followers_res = await fetch_api_data(f"https://friends.roblox.com/v1/users/{user_id}/followers/count")
            if followers_res and 'count' in followers_res:
                followers_count = followers_res['count']
            
            following_res = await fetch_api_data(f"https://friends.roblox.com/v1/users/{user_id}/followings/count")
            if following_res and 'count' in following_res:
                following_count = following_res['count']

            friends_res = await fetch_api_data(f"https://friends.roblox.com/v1/users/{user_id}/friends/count")
            if friends_res and 'count' in friends_res:
                friends_count = friends_res['count']

        except Exception as e:
            print(f"Error fetching friend/follower counts for {user_id}: {e}")
            # Counts will remain N/A

        # Format joined date
        joined_date_str = profile_data.get('created', 'N/A')
        if joined_date_str != 'N/A':
            try:
                # Roblox API returns ISO 8601 format, e.g., "2013-05-16T00:00:00.000Z"
                joined_datetime = datetime.fromisoformat(joined_date_str.replace('Z', '+00:00'))
                joined_date_formatted = joined_datetime.strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                joined_date_formatted = "Invalid Date Format"
        else:
            joined_date_formatted = "N/A"

        about_me = profile_data.get('description', 'No description provided.')
        if not about_me.strip(): # Check if description is empty or just whitespace
            about_me = 'No description provided.'
        elif len(about_me) > 1024: # Discord embed field value limit
            about_me = about_me[:1020] + "..." # Truncate if too long

        embed = discord.Embed(
            title=f"Roblox Profile: {display_name}",
            url=f"https://www.roblox.com/users/{user_id}/profile",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(name="Username", value=f"`{found_username}`", inline=True)
        embed.add_field(name="User ID", value=f"`{user_id}`", inline=True)
        embed.add_field(name="Display Name", value=f"`{display_name}`", inline=True)
        embed.add_field(name="Status", value=f"`{online_status}`", inline=True)
        embed.add_field(name="Followers", value=f"`{followers_count}`", inline=True)
        embed.add_field(name="Following", value=f"`{following_count}`", inline=True)
        embed.add_field(name="Friends", value=f"`{friends_count}`", inline=True)
        embed.add_field(name="Date Joined", value=f"`{joined_date_formatted}`", inline=True)
        embed.add_field(name="About Me", value=about_me, inline=False) # Not inline for readability

        await ctx.send(embed=embed)

    except aiohttp.ClientError as e:
        await ctx.send(f"A network error occurred while trying to fetch Roblox data: `{e}`. Please try again later.")
    except Exception as e:
        print(f"Error in !rblxusername command for '{username}': {e}")
        await ctx.send(f"An unexpected error occurred while fetching Roblox profile: `{e}`. Please try again later.")

# --- Connect4 Game Implementation ---

# Emojis for Connect4
C4_EMPTY = '\u2B1C'  # White Square
C4_RED = '\U0001F534'    # Red Circle
C4_YELLOW = '\U0001F7E1' # Yellow Circle
C4_NUMBERS = ['1\u20E3', '2\u20E3', '3\u20E3', '4\u20E3', '5\u20E3', '6\u20E3', '7\u20E3']

class Connect4Game:
    def __init__(self, player1, player2):
        self.board = [[C4_EMPTY for _ in range(7)] for _ in range(6)] # 6 rows, 7 columns
        self.players = {C4_RED: player1, C4_YELLOW: player2}
        self.player_emojis = {player1.id: C4_RED, player2.id: C4_YELLOW}
        self.current_turn_emoji = C4_RED
        self.message = None # To store the Discord message object for updating
        self.winner = None
        self.draw = False
        self.last_move = None # (row, col) of last piece dropped

    def _render_board(self):
        board_str = ""
        for row in self.board:
            board_str += "".join(row) + "\n"
        board_str += "".join(C4_NUMBERS) # Add column numbers at the bottom
        return board_str

    def _check_win(self):
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)] # Horizontal, Vertical, Diagonal (positive), Diagonal (negative)
        last_row, last_col = self.last_move
        piece = self.board[last_row][last_col]

        # Check all 4 directions from the last placed piece
        for dr, dc in directions:
            for i in range(-3, 1): # Check 4-in-a-row starting from up to 3 positions behind current
                r_start, c_start = last_row + dr * i, last_col + dc * i
                count = 0
                for j in range(4): # Check 4 pieces in this direction
                    r, c = r_start + dr * j, c_start + dc * j
                    if 0 <= r < 6 and 0 <= c < 7 and self.board[r][c] == piece:
                        count += 1
                        if count == 4:
                            return True
                    else:
                        break # Break if sequence is interrupted
        return False


    def _check_draw(self):
        for r in range(6):
            for c in range(7):
                if self.board[r][c] == C4_EMPTY:
                    return False # If any empty spot, not a draw
        return True # All spots filled, no winner

    def drop_piece(self, col):
        if not (0 <= col < 7):
            return False, "Invalid column number."
        if self.board[0][col] != C4_EMPTY: # Top of column is not empty
            return False, "Column is full."

        for r in range(5, -1, -1): # Start from bottom row
            if self.board[r][col] == C4_EMPTY:
                self.board[r][col] = self.current_turn_emoji
                self.last_move = (r, col)
                return True, ""
        return False, "An unexpected error occurred dropping the piece." # Should not happen if column not full

    def switch_turn(self):
        self.current_turn_emoji = C4_YELLOW if self.current_turn_emoji == C4_RED else C4_RED

    async def update_game_message(self):
        player_red = self.players[C4_RED]
        player_yellow = self.players[C4_YELLOW]
        turn_player = self.players[self.current_turn_emoji]

        embed = discord.Embed(
            title="Connect4!",
            description=f"{player_red.display_name} {C4_RED} vs {player_yellow.display_name} {C4_YELLOW}\n\n"
                        f"{self._render_board()}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="made by summers 2000")

        if self.winner:
            winner_player = self.players[self.winner]
            embed.add_field(name="Game Over!", value=f"{winner_player.display_name} {self.winner} wins!", inline=False)
            embed.color = discord.Color.green()
        elif self.draw:
            embed.add_field(name="Game Over!", value="It's a draw!", inline=False)
            embed.color = discord.Color.greyple()
        else:
            embed.add_field(name="Current Turn", value=f"{turn_player.display_name} {self.current_turn_emoji}'s turn!", inline=False)

        if self.message:
            await self.message.edit(embed=embed)


@bot.command(name="c4")
@commands.guild_only()
async def connect_four(ctx, opponent: discord.Member):
    """
    Starts a Connect4 game against another player.
    Usage: !c4 <@opponent>
    """
    if ctx.channel.id in active_c4_games:
        return await ctx.send("A Connect4 game is already active in this channel. Please finish it or start a new one elsewhere.")
    if opponent.bot:
        return await ctx.send("You cannot play Connect4 against a bot.")
    if opponent == ctx.author:
        return await ctx.send("You cannot play Connect4 against yourself!")

    player1 = ctx.author
    player2 = opponent

    game = Connect4Game(player1, player2)
    active_c4_games[ctx.channel.id] = game

    # Initial message for the game
    embed = discord.Embed(
        title="Connect4!",
        description=f"{player1.display_name} {C4_RED} vs {player2.display_name} {C4_YELLOW}\n\n"
                    f"{game._render_board()}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Current Turn", value=f"{player1.display_name} {C4_RED}'s turn!", inline=False)
    embed.set_footer(text="made by summers 2000")

    game_message = await ctx.send(embed=embed)
    game.message = game_message

    # Add reactions for columns
    for emoji in C4_NUMBERS:
        await game_message.add_reaction(emoji)

    await ctx.send(f"Connect4 game started between {player1.mention} and {player2.mention}! "
                   f"Use the reactions below the board to make your move.")

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return # Ignore bot's own reactions

    channel_id = reaction.message.channel.id
    
    # Handle Connect4 reactions
    if channel_id in active_c4_games:
        game = active_c4_games[channel_id]

        if reaction.message.id != game.message.id:
            return # Not the current game message

        # Check if it's the correct player's turn
        expected_player = game.players[game.current_turn_emoji]
        if user.id != expected_player.id:
            # Optionally remove reaction if not their turn
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass # Bot might not have permission
            return

        # Check if game is already over
        if game.winner or game.draw:
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass
            return

        # Determine the column from reaction
        if reaction.emoji in C4_NUMBERS:
            col = C4_NUMBERS.index(reaction.emoji)
            success, error_msg = game.drop_piece(col)

            if success:
                # Remove all reactions to prevent spam/re-use (and re-add them after turn)
                try:
                    # Clear all reactions from the message after a valid move to prevent re-using old reactions
                    # This also ensures only valid current moves can be reacted to.
                    await reaction.message.clear_reactions()
                except discord.Forbidden:
                    print(f"Bot missing permissions to clear reactions in channel {reaction.message.channel.id}.")
                    pass # Bot might not have permission

                if game._check_win():
                    game.winner = game.current_turn_emoji
                    # Update stats
                    update_game_stats(game.players[game.winner].id, "c4", "win")
                    other_player_id = game.players[C4_RED if game.winner == C4_YELLOW else C4_YELLOW].id
                    update_game_stats(other_player_id, "c4", "loss")
                    await game.update_game_message()
                    await reaction.message.channel.send(f"Congratulations, {user.mention}! You won the Connect4 game!")
                    del active_c4_games[channel_id] # Game over, remove from active games
                elif game._check_draw():
                    game.draw = True
                    # Update stats for draw
                    update_game_stats(game.players[C4_RED].id, "c4", "draw")
                    update_game_stats(game.players[C4_YELLOW].id, "c4", "draw")
                    await game.update_game_message()
                    await reaction.message.channel.send("The Connect4 game is a draw!")
                    del active_c4_games[channel_id]
                else:
                    game.switch_turn()
                    await game.update_game_message()
                    # Re-add reactions for the next turn
                    for emoji in C4_NUMBERS:
                        await game.message.add_reaction(emoji)
            else:
                # If drop failed (e.g., column full), remove player's reaction
                try:
                    await reaction.remove(user)
                except discord.Forbidden:
                    pass
                await reaction.message.channel.send(f"{user.mention}, {error_msg} Please choose another column.", delete_after=5)
        else:
            # If invalid emoji, remove reaction
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass
            return
    
    # Handle Tic-Tac-Toe reactions
    elif channel_id in active_tictactoe_games:
        await handle_tictactoe_reaction(reaction, user)

# --- Tic-Tac-Toe Game Implementation ---

# Emojis for Tic-Tac-Toe
TTT_EMPTY = '\u2B1C'  # White Square
TTT_X = '\u274C'      # Red X
TTT_O = '\u2B55'      # Large Blue Circle (for O)
TTT_NUMBERS = ['1\u20E3', '2\u20E3', '3\u20E3', '4\u20E3', '5\u20E3', '6\u20E3', '7\u20E3', '8\u20E3', '9\u20E3']

class TicTacToeGame:
    def __init__(self, player1, player2):
        self.board = [[TTT_EMPTY for _ in range(3)] for _ in range(3)] # 3x3 board
        self.players = {TTT_X: player1, TTT_O: player2}
        self.player_emojis = {player1.id: TTT_X, player2.id: TTT_O}
        self.current_turn_emoji = TTT_X
        self.message = None # To store the Discord message object for updating
        self.winner = None
        self.draw = False
        self.last_player_move = None # Stores the player who made the last valid move

    def _render_board(self):
        board_str = ""
        for i, row in enumerate(self.board):
            board_str += "".join(row)
            if i < 2:
                board_str += "\n"
        return board_str

    def _check_win(self):
        # Check rows, columns, and diagonals
        lines = []
        # Rows
        for r in range(3):
            lines.append(self.board[r])
        # Columns
        for c in range(3):
            lines.append([self.board[r][c] for r in range(3)])
        # Diagonals
        lines.append([self.board[i][i] for i in range(3)])
        lines.append([self.board[i][2-i] for i in range(3)])

        for line in lines:
            if line[0] != TTT_EMPTY and all(x == line[0] for x in line):
                self.winner = line[0]
                return True
        return False

    def _check_draw(self):
        if self.winner: return False # Can't be a draw if there's a winner
        for r in range(3):
            for c in range(3):
                if self.board[r][c] == TTT_EMPTY:
                    return False # If any empty spot, not a draw
        return True # All spots filled, no winner

    def make_move(self, position): # position is 1-9
        row = (position - 1) // 3
        col = (position - 1) % 3

        if not (0 <= row < 3 and 0 <= col < 3):
            return False, "Invalid position."
        if self.board[row][col] != TTT_EMPTY:
            return False, "That spot is already taken."

        self.board[row][col] = self.current_turn_emoji
        return True, ""

    def switch_turn(self):
        self.current_turn_emoji = TTT_O if self.current_turn_emoji == TTT_X else TTT_X

    async def update_game_message(self):
        player_x = self.players[TTT_X]
        player_o = self.players[TTT_O]
        turn_player = self.players[self.current_turn_emoji]

        embed = discord.Embed(
            title="Tic-Tac-Toe!",
            description=f"{player_x.display_name} {TTT_X} vs {player_o.display_name} {TTT_O}\n\n"
                        f"{self._render_board()}",
            color=discord.Color.purple()
        )
        embed.set_footer(text="made by summers 2000")

        if self.winner:
            winner_player = self.players[self.winner]
            embed.add_field(name="Game Over!", value=f"{winner_player.display_name} {self.winner} wins!", inline=False)
            embed.color = discord.Color.green()
        elif self.draw:
            embed.add_field(name="Game Over!", value="It's a draw!", inline=False)
            embed.color = discord.Color.greyple()
        else:
            embed.add_field(name="Current Turn", value=f"{turn_player.display_name} {self.current_turn_emoji}'s turn!", inline=False)

        if self.message:
            await self.message.edit(embed=embed)


@bot.command(name="tictactoe")
@commands.guild_only()
async def tictactoe_game(ctx, opponent: discord.Member):
    """
    Starts a Tic-Tac-Toe game against another player.
    Usage: !tictactoe <@opponent>
    """
    if ctx.channel.id in active_tictactoe_games:
        return await ctx.send("A Tic-Tac-Toe game is already active in this channel. Please finish it or start a new one elsewhere.")
    if opponent.bot:
        return await ctx.send("You cannot play Tic-Tac-Toe against a bot.")
    if opponent == ctx.author:
        return await ctx.send("You cannot play Tic-Tac-Toe against yourself!")

    player1 = ctx.author
    player2 = opponent

    game = TicTacToeGame(player1, player2)
    active_tictactoe_games[ctx.channel.id] = game

    # Initial message for the game
    embed = discord.Embed(
        title="Tic-Tac-Toe!",
        description=f"{player1.display_name} {TTT_X} vs {player2.display_name} {TTT_O}\n\n"
                    f"{game._render_board()}",
        color=discord.Color.purple()
    )
    embed.add_field(name="Current Turn", value=f"{player1.display_name} {TTT_X}'s turn!", inline=False)
    embed.set_footer(text="made by summers 2000")

    game_message = await ctx.send(embed=embed)
    game.message = game_message

    # Add reactions for positions 1-9
    for emoji in TTT_NUMBERS:
        await game_message.add_reaction(emoji)

    await ctx.send(f"Tic-Tac-Toe game started between {player1.mention} and {player2.mention}! "
                   f"Use the reactions below the board to make your move.")


async def handle_tictactoe_reaction(reaction, user):
    channel_id = reaction.message.channel.id
    if channel_id in active_tictactoe_games:
        game = active_tictactoe_games[channel_id]

        if reaction.message.id != game.message.id:
            return # Not the current game message

        # Check if it's the correct player's turn
        expected_player = game.players[game.current_turn_emoji]
        if user.id != expected_player.id:
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass
            return

        # Check if game is already over
        if game.winner or game.draw:
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass
            return

        # Determine the position from reaction
        if reaction.emoji in TTT_NUMBERS:
            position = TTT_NUMBERS.index(reaction.emoji) + 1 # Convert 0-indexed to 1-indexed
            success, error_msg = game.make_move(position)

            if success:
                # Remove all reactions to prevent spam/re-use (and re-add them after turn)
                try:
                    # Clear all reactions from the message after a valid move
                    await reaction.message.clear_reactions()
                except discord.Forbidden:
                    print(f"Bot missing permissions to clear reactions in channel {reaction.message.channel.id}.")
                    pass

                if game._check_win():
                    game.winner = game.current_turn_emoji
                    # Update stats
                    update_game_stats(game.players[game.winner].id, "ttt", "win")
                    other_player_id = game.players[TTT_X if game.winner == TTT_O else TTT_O].id
                    update_game_stats(other_player_id, "ttt", "loss")
                    await game.update_game_message()
                    await reaction.message.channel.send(f"Congratulations, {user.mention}! You won the Tic-Tac-Toe game!")
                    del active_tictactoe_games[channel_id] # Game over, remove from active games
                elif game._check_draw():
                    game.draw = True
                    # Update stats for draw
                    update_game_stats(game.players[TTT_X].id, "ttt", "draw")
                    update_game_stats(game.players[TTT_O].id, "ttt", "draw")
                    await game.update_game_message()
                    await reaction.message.channel.send("The Tic-Tac-Toe game is a draw!")
                    del active_tictactoe_games[channel_id]
                else:
                    game.switch_turn()
                    await game.update_game_message()
                    # Re-add reactions for the next turn
                    for emoji in TTT_NUMBERS:
                        await game.message.add_reaction(emoji)
            else:
                # If move failed (e.g., spot taken), remove player's reaction
                try:
                    await reaction.remove(user)
                except discord.Forbidden:
                    pass
                await reaction.message.channel.send(f"{user.mention}, {error_msg} Please choose another spot.", delete_after=5)
        else:
            # If invalid emoji, remove reaction
            try:
                await reaction.remove(user)
            except discord.Forbidden:
                pass
            return


# --- Game Stats Commands ---
@bot.command(name="gamestats")
async def game_stats_command(ctx):
    """
    Displays your Connect4 and Tic-Tac-Toe game statistics.
    Usage: !gamestats
    """
    user_id = ctx.author.id
    stats = game_stats.get(user_id, {"c4_wins": 0, "c4_losses": 0, "c4_draws": 0, "ttt_wins": 0, "ttt_losses": 0, "ttt_draws": 0})

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Game Statistics",
        color=discord.Color.purple(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    embed.add_field(name="Connect4 Stats", value=(
        f"Wins: `{stats['c4_wins']}`\n"
        f"Losses: `{stats['c4_losses']}`\n"
        f"Draws: `{stats['c4_draws']}`"
    ), inline=True)

    embed.add_field(name="Tic-Tac-Toe Stats", value=(
        f"Wins: `{stats['ttt_wins']}`\n"
        f"Losses: `{stats['ttt_losses']}`\n"
        f"Draws: `{stats['ttt_draws']}`"
    ), inline=True)

    await ctx.send(embed=embed)

@bot.command(name="c4leaderboard")
async def c4_leaderboard(ctx):
    """
    Displays the Connect4 server leaderboard.
    Usage: !c4leaderboard
    """
    leaderboard_data = []
    # Fetch all members to get display names, if available in cache
    # If not in cache, bot.get_user(user_id) will return None, need to fetch_user
    for user_id, stats in game_stats.items():
        if stats["c4_wins"] > 0 or stats["c4_losses"] > 0 or stats["c4_draws"] > 0:
            user = bot.get_user(user_id) # Try to get from cache first
            if user:
                leaderboard_data.append({"user": user, "wins": stats["c4_wins"], "losses": stats["c4_losses"], "draws": stats["c4_draws"]})
            else:
                # User not in cache, skip for now to avoid blocking on fetch_user for many users
                # This could be improved by fetching in batches or only when explicitly needed.
                print(f"User {user_id} not in cache for c4leaderboard. Skipping their entry for this run.")

    if not leaderboard_data:
        await ctx.send("No Connect4 games recorded yet for the leaderboard.")
        return

    leaderboard_data.sort(key=lambda x: x["wins"], reverse=True)

    embed = discord.Embed(
        title="Connect4 Leaderboard (Top 10 Wins)",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    description = ""
    for i, entry in enumerate(leaderboard_data[:10]):
        description += f"**{i+1}. {entry['user'].display_name}** - Wins: `{entry['wins']}` | Losses: `{entry['losses']}` | Draws: `{entry['draws']}`\n"
    
    if len(leaderboard_data) > 10:
        description += "\n*...and more!*"
    
    embed.description = description if description else "No Connect4 wins yet!"
    await ctx.send(embed=embed)

@bot.command(name="tttleaderboard")
async def ttt_leaderboard(ctx):
    """
    Displays the Tic-Tac-Toe server leaderboard.
    Usage: !tttleaderboard
    """
    leaderboard_data = []
    for user_id, stats in game_stats.items():
        if stats["ttt_wins"] > 0 or stats["ttt_losses"] > 0 or stats["ttt_draws"] > 0:
            user = bot.get_user(user_id) # Try to get from cache first
            if user:
                leaderboard_data.append({"user": user, "wins": stats["ttt_wins"], "losses": stats["ttt_losses"], "draws": stats["ttt_draws"]})
            else:
                print(f"User {user_id} not in cache for tttleaderboard. Skipping their entry for this run.")
    
    if not leaderboard_data:
        await ctx.send("No Tic-Tac-Toe games recorded yet for the leaderboard.")
        return

    leaderboard_data.sort(key=lambda x: x["wins"], reverse=True)

    embed = discord.Embed(
        title="Tic-Tac-Toe Leaderboard (Top 10 Wins)",
        color=discord.Color.purple(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    description = ""
    for i, entry in enumerate(leaderboard_data[:10]):
        description += f"**{i+1}. {entry['user'].display_name}** - Wins: `{entry['wins']}` | Losses: `{entry['losses']}` | Draws: `{entry['draws']}`\n"
    
    if len(leaderboard_data) > 10:
        description += "\n*...and more!*"
    
    embed.description = description if description else "No Tic-Tac-Toe wins yet!"
    await ctx.send(embed=embed)

# --- Roll Command ---
@bot.command(name="roll")
async def roll_command(ctx, max_number: int = 100):
    """
    Rolls a dice or a number between 1 and [number] (default 100).
    Usage: !roll [max_number]
    """
    if max_number <= 0:
        await ctx.send("The maximum number must be a positive integer.")
        return
    
    result = random.randint(1, max_number)
    
    embed = discord.Embed(
        title="🎲 Roll the Dice! 🎲",
        description=f"{ctx.author.mention} rolled a **`{result}`** (1 - {max_number})!",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(ctx.author.id, "FIRST_ROLL_COMMAND", ctx)


# --- Lottery Commands ---
@bot.group(name="lotto", invoke_without_command=True)
async def lotto_group(ctx):
    """
    Interact with the server lottery.
    Usage: !lotto <buy [tickets] | draw | status>
    """
    await ctx.send(f"Welcome to the Lottery! Use `!lotto buy [amount]` to buy tickets, `!lotto status` to check the current pot and players, or `!lotto draw` to draw a winner (admin only). Each ticket costs `{LOTTO_TICKET_PRICE}` coins.")

@lotto_group.command(name="buy")
async def lotto_buy(ctx, quantity: int = 1):
    """
    Buy lottery tickets.
    Usage: !lotto buy [amount]
    """
    if quantity <= 0:
        await ctx.send("You must buy at least one lottery ticket.")
        return
    
    cost = LOTTO_TICKET_PRICE * quantity
    user_id = ctx.author.id

    if user_balances.get(user_id, 0) < cost:
        await ctx.send(f"You don't have enough coins to buy `{quantity}` ticket(s). You need `{cost}` coins, but you only have `{user_balances.get(user_id, 0)}`.")
        return
    
    user_balances[user_id] -= cost
    LOTTO_POT += cost
    LOTTO_TICKETS[user_id] = LOTTO_TICKETS.get(user_id, 0) + quantity

    save_user_balances()
    save_lotto_data()

    embed = discord.Embed(
        title="Lottery Tickets Purchased!",
        description=f"You bought `{quantity}` lottery ticket(s) for **`{cost}`** coins.\n"
                    f"Your total tickets: `{LOTTO_TICKETS[user_id]}`\n"
                    f"Current pot: **`{LOTTO_POT}`** coins.",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(user_id, "FIRST_LOTTO_ENTRY", ctx)

@lotto_group.command(name="status")
async def lotto_status(ctx):
    """
    Check the current lottery pot and participating players.
    Usage: !lotto status
    """
    embed = discord.Embed(
        title="Current Lottery Status",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    embed.add_field(name="Current Pot", value=f"**`{LOTTO_POT}`** coins", inline=False)
    
    if not LOTTO_TICKETS:
        embed.add_field(name="Participants", value="No one has bought tickets yet!", inline=False)
    else:
        participants_list = []
        # Sort participants by number of tickets descending
        sorted_participants = sorted(LOTTO_TICKETS.items(), key=lambda item: item[1], reverse=True)
        for user_id, tickets in sorted_participants:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            user_name = user.display_name if user else f"Unknown User (ID: {user_id})"
            participants_list.append(f"{user_name}: `{tickets}` tickets")
        
        embed.add_field(name="Participants (Tickets)", value="\n".join(participants_list), inline=False)
    
    await ctx.send(embed=embed)

@lotto_group.command(name="draw")
@commands.has_permissions(administrator=True) # Only administrators can draw the lottery
async def lotto_draw(ctx):
    """
    Draws a winner for the lottery. (Admin only)
    Usage: !lotto draw
    """
    if len(LOTTO_TICKETS) < LOTTO_MIN_PLAYERS:
        await ctx.send(f"At least `{LOTTO_MIN_PLAYERS}` players are required to draw the lottery. Current players: `{len(LOTTO_TICKETS)}`.")
        return
    
    if LOTTO_POT == 0:
        await ctx.send("The lottery pot is empty. No one has bought tickets yet!")
        return

    # Create a list of all tickets for drawing (each ticket represents a chance)
    all_tickets = []
    for user_id, tickets in LOTTO_TICKETS.items():
        all_tickets.extend([user_id] * tickets) # Add user_id 'tickets' times

    winner_id = random.choice(all_tickets)
    winner_user = bot.get_user(winner_id) or await bot.fetch_user(winner_id)
    winner_name = winner_user.mention if winner_user else f"Unknown User (ID: {winner_id})"

    winnings = LOTTO_POT
    user_balances[winner_id] = user_balances.get(winner_id, 0) + winnings
    
    # Reset lottery state
    global LOTTO_TICKETS, LOTTO_POT
    LOTTO_TICKETS = {}
    LOTTO_POT = 0

    save_user_balances()
    save_lotto_data()

    embed = discord.Embed(
        title="🎉 Lottery Winner! 🎉",
        description=f"The lottery has been drawn!\n"
                    f"And the winner is... {winner_name}!\n"
                    f"They won the entire pot of **`{winnings}`** coins!",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)


# --- Audit Log Command ---
@bot.command(name="auditlog")
@commands.has_permissions(view_audit_log=True)
@commands.guild_only()
async def audit_log_command(ctx, action_type: str = None, user: discord.Member = None):
    """
    Views recent server audit log entries.
    Usage: !auditlog [action_type] [@user]
    Example: !auditlog ban @user
    Valid action types (case-insensitive, can be partial): ban, kick, member_update, channel_create, role_update, etc.
    See: https://discordpy.readthedocs.io/en/latest/api.html#discord.AuditLogAction
    """
    audit_log_actions = {
        "guild_update": discord.AuditLogAction.guild_update,
        "channel_create": discord.AuditLogAction.channel_create,
        "channel_update": discord.AuditLogAction.channel_update,
        "channel_delete": discord.AuditLogAction.channel_delete,
        "overwrite_create": discord.AuditLogAction.overwrite_create,
        "overwrite_update": discord.AuditLogAction.overwrite_update,
        "overwrite_delete": discord.AuditLogAction.overwrite_delete,
        "kick": discord.AuditLogAction.kick,
        "member_prune": discord.AuditLogAction.member_prune,
        "ban": discord.AuditLogAction.ban,
        "unban": discord.AuditLogAction.unban,
        "member_update": discord.AuditLogAction.member_update,
        "member_role_update": discord.AuditLogAction.member_role_update,
        "role_create": discord.AuditLogAction.role_create,
        "role_update": discord.AuditLogAction.role_update,
        "role_delete": discord.AuditLogAction.role_delete,
        "invite_create": discord.AuditLogAction.invite_create,
        "invite_update": discord.AuditLogAction.invite_update,
        "invite_delete": discord.AuditLogAction.invite_delete,
        "webhook_create": discord.AuditLogAction.webhook_create,
        "webhook_update": discord.AuditLogAction.webhook_update,
        "webhook_delete": discord.AuditLogAction.webhook_delete,
        "emoji_create": discord.AuditLogAction.emoji_create,
        "emoji_update": discord.AuditLogAction.emoji_update,
        "emoji_delete": discord.AuditLogAction.emoji_delete,
        "message_delete": discord.AuditLogAction.message_delete,
        "message_bulk_delete": discord.AuditLogAction.message_bulk_delete,
        "message_pin": discord.AuditLogAction.message_pin,
        "message_unpin": discord.AuditLogAction.message_unpin,
        "integration_create": discord.AuditLogAction.integration_create,
        "integration_update": discord.AuditLogAction.integration_update,
        "integration_delete": discord.AuditLogAction.integration_delete,
        "thread_create": discord.AuditLogAction.thread_create,
        "thread_update": discord.AuditLogAction.thread_update,
        "thread_delete": discord.AuditLogAction.thread_delete,
        "stage_instance_create": discord.AuditLogAction.stage_instance_create,
        "stage_instance_update": discord.AuditLogAction.stage_instance_update,
        "stage_instance_delete": discord.AuditLogAction.stage_instance_delete,
        "sticker_create": discord.AuditLogAction.sticker_create,
        "sticker_update": discord.AuditLogAction.sticker_update,
        "sticker_delete": discord.AuditLogAction.sticker_delete,
        "guild_scheduled_event_create": discord.AuditLogAction.guild_scheduled_event_create,
        "guild_scheduled_event_update": discord.AuditLogAction.guild_scheduled_event_update,
        "guild_scheduled_event_delete": discord.AuditLogAction.guild_scheduled_event_delete,
        "auto_moderation_configuration": discord.AuditLogAction.auto_moderation_configuration,
        "auto_moderation_block_message": discord.AuditLogAction.auto_moderation_block_message,
        "auto_moderation_flag_to_channel": discord.AuditLogAction.auto_moderation_flag_to_channel,
        "auto_moderation_user_communication_disabled": discord.AuditLogAction.auto_moderation_user_communication_disabled
    }

    selected_action = None
    if action_type:
        # Find action type, allowing for partial or case-insensitive matches
        found_match = False
        for key, action_enum in audit_log_actions.items():
            if action_type.lower() in key.lower():
                selected_action = action_enum
                found_match = True
                break
        
        if not found_match: # Use found_match to check if a valid action was found
            await ctx.send(f"Invalid audit log action type: `{action_type}`. Please choose from a partial match of these: `{', '.join(audit_log_actions.keys())}`")
            return

    embed = discord.Embed(
        title=f"Recent Audit Log Entries",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    logs = []
    try:
        # Fetch up to 10 recent logs. Adjust limit if needed.
        async for entry in ctx.guild.audit_logs(limit=10, action=selected_action, user=user):
            logs.append(entry)
    except discord.Forbidden:
        await ctx.send("I don't have permission to view the audit log. Please grant me 'View Audit Log' permission.")
        return
    except Exception as e:
        await ctx.send(f"An error occurred while fetching audit logs: `{e}`")
        return

    if not logs:
        embed.description = "No audit log entries found matching your criteria."
    else:
        description_lines = []
        for entry in logs:
            target_info = ""
            if entry.target:
                if isinstance(entry.target, discord.Member):
                    target_info = f"Target: {entry.target.display_name} (`{entry.target.id}`)"
                elif hasattr(entry.target, 'name'):
                    target_info = f"Target: {entry.target.name}"
                else:
                    target_info = f"Target ID: `{entry.target.id}`"

            reason_info = f"Reason: `{entry.reason}`" if entry.reason else "No reason provided."
            
            description_lines.append(
                f"**{entry.action.name.replace('_', ' ').title()}** by **{entry.user.display_name}** (`{entry.user.id}`)\n"
                f"{target_info}\n"
                f"{reason_info}\n"
                f"At: <t:{int(entry.created_at.timestamp())}:F>" # Discord's timestamp format
            )
        embed.description = "\n\n".join(description_lines)

    await ctx.send(embed=embed)


# --- Achievements Command ---
@bot.command(name="myachievements")
async def my_achievements_command(ctx):
    """
    Displays your earned achievements.
    Usage: !myachievements
    """
    user_id = ctx.author.id
    user_achievements = achievements.get(user_id, [])

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Achievements",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    if not user_achievements:
        embed.description = "You haven't unlocked any achievements yet. Keep interacting with the bot!"
    else:
        # Sort achievements alphabetically for consistent display
        user_achievements_sorted = sorted(user_achievements, key=lambda x: ACHIEVEMENT_DEFINITIONS.get(x, x))
        description = "\n".join([f"🏆 **{ACHIEVEMENT_DEFINITIONS.get(ach_id, ach_id)}**" for ach_id in user_achievements_sorted])
        embed.description = description
    
    await ctx.send(embed=embed)

# --- My Garden Commands ---
@bot.command(name="setgarden")
async def set_garden(ctx, description: str, image_url: str = None):
    """
    Sets your personal garden showcase description and an optional image URL.
    Usage: !setgarden "My beautiful flower bed" [https://example.com/garden.png]
    """
    user_id = ctx.author.id
    # Ensure description is not too long for Discord embed field
    if len(description) > 1024:
        description = description[:1020] + "..."
        await ctx.send("Your description was too long and has been truncated.")

    my_gardens[user_id] = {"description": description}
    if image_url:
        # Basic URL validation (you might want more robust validation)
        # Added a check for common image file extensions
        if image_url.startswith(("http://", "https://")) and any(image_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]) or "placehold.co" in image_url.lower():
            my_gardens[user_id]["image_url"] = image_url
        else:
            await ctx.send("Invalid image URL provided. Please ensure it's a direct link to a `.png`, `.jpg`, `.jpeg`, `.gif`, or `.webp` file. Your description was saved, but the image was not.")
            image_url = None # Don't save invalid URL
    else:
        # If no image_url is provided, remove any existing one
        if "image_url" in my_gardens[user_id]:
            del my_gardens[user_id]["image_url"]
    
    save_my_gardens()

    embed = discord.Embed(
        title="Your Garden Showcase Updated!",
        description=f"**Description:** {description}",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    if image_url:
        embed.set_image(url=image_url)
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(user_id, "FIRST_GARDEN_SHOWCASE", ctx)

@bot.command(name="mygarden")
async def show_my_garden(ctx):
    """
    Shows your saved garden showcase.
    Usage: !mygarden
    """
    user_id = ctx.author.id
    garden_data = my_gardens.get(user_id)

    if not garden_data:
        await ctx.send("You haven't set up your garden showcase yet! Use `!setgarden \"Your description here\" [optional_image_url]` to set it up.")
        return

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Garden Showcase",
        description=garden_data.get("description", "No description set."),
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    if garden_data.get("image_url"):
        embed.set_image(url=garden_data["image_url"])
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="showgardens")
@commands.cooldown(1, 60, commands.BucketType.channel) # Cooldown to prevent spam
async def show_random_garden(ctx):
    """
    Manually triggers a random user's garden showcase post.
    Usage: !showgardens
    """
    if not my_gardens:
        await ctx.send("No gardens have been set up by users yet. Be the first with `!setgarden`!")
        return

    # Filter out gardens without descriptions or where the user might not exist anymore
    valid_gardens = []
    for user_id_str, garden_data in my_gardens.items():
        user_id = int(user_id_str)
        if "description" in garden_data:
            user = bot.get_user(user_id) # Try to get from cache
            if user:
                valid_gardens.append({"user": user, "data": garden_data})
            else:
                # Attempt to fetch user if not in cache, for a more reliable showcase
                try:
                    user = await bot.fetch_user(user_id)
                    valid_gardens.append({"user": user, "data": garden_data})
                except discord.NotFound:
                    print(f"User {user_id} not found when trying to fetch for !showgardens. Skipping.")
                except Exception as e:
                    print(f"Error fetching user {user_id} for !showgardens: {e}. Skipping.")
    
    if not valid_gardens:
        await ctx.send("Could not find any valid gardens to showcase at this time. Please ensure users have set descriptions for their gardens.")
        return

    import random
    selected_garden = random.choice(valid_gardens)
    user = selected_garden["user"]
    garden_data = selected_garden["data"]

    embed = discord.Embed(
        title=f"🏡 Garden Showcase: {user.display_name}'s Garden 🏡",
        description=garden_data.get("description", "No description set."),
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    if garden_data.get("image_url"):
        embed.set_image(url=garden_data["image_url"])
    embed.set_footer(text="made by summers 2000")

    try:
        await ctx.send(embed=embed)
        print(f"Manually posted {user.display_name}'s garden to showcase channel via !showgardens.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to send messages in this channel for garden showcases.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while posting garden showcase: `{e}`")


@tasks.loop(hours=6) # Posts a random garden every 6 hours
async def garden_showcase_poster():
    """Background task to periodically post a random user's garden."""
    if not GARDEN_SHOWCASE_CHANNEL_ID:
        print("Garden Showcase channel ID not set. Skipping garden showcase poster.")
        return
    
    channel = bot.get_channel(GARDEN_SHOWCASE_CHANNEL_ID)
    if not channel:
        print(f"Garden Showcase channel with ID {GARDEN_SHOWCASE_CHANNEL_ID} not found or inaccessible.")
        return

    if not my_gardens:
        print("No gardens saved for showcasing.")
        return

    # Filter out gardens without descriptions or where the user might not exist anymore
    valid_gardens = []
    for user_id_str, garden_data in my_gardens.items():
        user_id = int(user_id_str)
        if "description" in garden_data:
            user = bot.get_user(user_id)
            if user: # Ensure the user still exists in the bot's cache
                valid_gardens.append({"user": user, "data": garden_data})
    
    if not valid_gardens:
        print("No valid gardens to showcase.")
        return

    import random
    selected_garden = random.choice(valid_gardens)
    user = selected_garden["user"]
    garden_data = selected_garden["data"]

    embed = discord.Embed(
        title=f"🏡 Garden Showcase: {user.display_name}'s Garden 🏡",
        description=garden_data.get("description", "No description set."),
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    if garden_data.get("image_url"):
        embed.set_image(url=garden_data["image_url"])
    embed.set_footer(text="made by summers 2000")

    try:
        await channel.send(embed=embed)
        print(f"Posted {user.display_name}'s garden to showcase channel.")
    except discord.Forbidden:
        print(f"Bot does not have permission to send messages in garden showcase channel {channel.id}.")
    except Exception as e:
        print(f"Error posting garden showcase: {e}")

@garden_showcase_poster.before_loop
async def before_garden_showcase_poster():
    await bot.wait_until_ready()

# --- Remind Me Command ---
@bot.command(name="remindme")
async def remind_me(ctx, time_str: str, *, message: str):
    """
    Sets a personal reminder.
    Usage: !remindme <time> <message>
    Time examples: 30s, 5m, 1h, 1d (seconds, minutes, hours, days)
    """
    unit_map = {
        's': 1,      # seconds
        'm': 60,     # minutes
        'h': 3600,   # hours
        'd': 86400   # days
    }

    match = re.fullmatch(r'(\d+)([smhd])', time_str.lower())
    if not match:
        await ctx.send("Invalid time format. Please use a number followed by s (seconds), m (minutes), h (hours), or d (days). E.g., `!remindme 30m Check my crops`")
        return

    amount = int(match.group(1))
    unit = match.group(2)
    
    if amount <= 0:
        await ctx.send("Reminder time must be a positive number.")
        return
    
    if amount > 365 and unit == 'd': # Limit reminders to max 1 year
        await ctx.send("You can only set reminders for up to 365 days.")
        return

    delay_seconds = amount * unit_map[unit]
    remind_time = datetime.utcnow() + timedelta(seconds=delay_seconds)

    reminders.append({
        "user_id": ctx.author.id,
        "remind_time": remind_time,
        "message": message
    })
    reminders.sort(key=lambda x: x['remind_time']) # Keep sorted for efficient checking
    save_reminders()

    # Format human-readable delay more nicely
    parts = []
    if delay_seconds >= 86400:
        d = delay_seconds // 86400
        parts.append(f"{d} day{'s' if d != 1 else ''}")
        delay_seconds %= 86400
    if delay_seconds >= 3600:
        h = delay_seconds // 3600
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
        delay_seconds %= 3600
    if delay_seconds >= 60:
        m = delay_seconds // 60
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
        delay_seconds %= 60
    if delay_seconds > 0 or not parts: # Include seconds if there are any remaining or if total delay is less than a minute
        parts.append(f"{delay_seconds} second{'s' if delay_seconds != 1 else ''}")
    
    human_readable_delay = ", ".join(parts)


    embed = discord.Embed(
        title="Reminder Set!",
        description=f"I will remind you about: **`{message}`**\n"
                    f"In approximately: `{human_readable_delay}`",
        color=discord.Color.teal(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(ctx.author.id, "FIRST_REMINDER_SET", ctx)

@tasks.loop(seconds=10) # Check reminders every 10 seconds
async def reminder_checker():
    global reminders
    current_time = datetime.utcnow()
    reminders_to_send = []
    reminders_to_keep = []

    # Iterate a copy of the list to avoid issues if items are removed during iteration
    for reminder in list(reminders):
        if reminder['remind_time'] <= current_time:
            reminders_to_send.append(reminder)
        else:
            reminders_to_keep.append(reminder)
    
    reminders = reminders_to_keep # Update global list with remaining reminders
    
    if reminders_to_send:
        save_reminders() # Save state immediately after populating to_send list and updating global list

    for reminder in reminders_to_send:
        user = bot.get_user(reminder['user_id'])
        if user is None:
            try:
                user = await bot.fetch_user(reminder['user_id'])
            except discord.NotFound:
                print(f"Reminder: User {reminder['user_id']} not found. Skipping reminder.")
                continue
            except Exception as e:
                print(f"Reminder: Error fetching user {reminder['user_id']}: {e}. Skipping reminder.")
                continue

        if user:
            try:
                embed = discord.Embed(
                    title="⏰ Your Reminder! ⏰",
                    description=f"You asked me to remind you about: **`{reminder['message']}`**",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="made by summers 2000")
                await user.send(embed=embed)
                print(f"Sent reminder to {user.name} ({user.id}): {reminder['message']}")
            except discord.Forbidden:
                print(f"Could not send reminder DM to {user.name} ({user.id}). DMs disabled.")
            except Exception as e:
                print(f"An unexpected error occurred while sending reminder DM to {user.name} ({user.id}): {e}")

@reminder_checker.before_loop
async def before_reminder_checker():
    await bot.wait_until_ready()


# --- Ban Request View ---
class ConfirmBanRequestView(discord.ui.View):
    def __init__(self, original_author_id, guild_id):
        super().__init__(timeout=300) # 5 minutes timeout
        self.original_author_id = original_author_id
        self.guild_id = guild_id
        self.response = None # To store 'yes' or 'no'

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author_id:
            await interaction.response.send_message("This interaction is not for you.", ephemeral=True)
            return

        self.response = True
        self.stop() # Stop the view from listening for more interactions

        # Update the original message to disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        embed = discord.Embed(
            title="Ban Request: Payment Required",
            description="Please send $15 to Cash App: **`$sxi659`**\n"
                        "Once sent, reply to this DM with the **User ID** of the person you want to ban from Sacrificed.",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await interaction.response.send_message(embed=embed)

        # Update the global state for this user to await User ID
        BAN_REQUEST_STATES[self.original_author_id] = {"state": "awaiting_userid", "guild_id": self.guild_id}


    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author_id:
            await interaction.response.send_message("This interaction is not for you.", ephemeral=True)
            return

        self.response = False
        self.stop() # Stop the view from listening for more interactions

        # Update the original message to disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        embed = discord.Embed(
            title="Ban Request Canceled",
            description="You have canceled the ban request process.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await interaction.response.send_message(embed=embed)

    async def on_timeout(self):
        if self.response is None: # Only if no button was clicked
            try:
                # Disable buttons on timeout
                for item in self.children:
                    item.disabled = True
                await self.message.edit(content="Ban request confirmation timed out.", view=self)
                embed = discord.Embed(
                    title="Ban Request Timed Out",
                    description="Your ban request confirmation timed out. Please try again if you wish to proceed.",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text="made by summers 2000")
                # Removed sending ephemeral message here as it might conflict with original DM channel.
                # await self.message.channel.send(embed=embed) # This was trying to send in DM, but message.channel is the DM channel
            except discord.HTTPException:
                pass # Message might have been deleted or inaccessible
            finally:
                if self.original_author_id in BAN_REQUEST_STATES:
                    del BAN_REQUEST_STATES[self.original_author_id]


# --- Ban Request Command ---
@bot.command(name="banrequest")
@commands.guild_only()
async def ban_request(ctx):
    """
    Initiates a ban request process via DM. Costs $10.
    Usage: !banrequest
    """
    if ctx.author.id in BAN_REQUEST_STATES:
        await ctx.send("You already have an active ban request. Please complete or cancel it in your DMs first.", ephemeral=True)
        return

    ban_request_embed = discord.Embed(
        title="Ban Request Confirmation",
        description="Before we continue, please note that a ban request costs **$15**. "
                    "Are you willing to pay this to get a user banned from Sacrificed?",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    ban_request_embed.set_footer(text="made by summers 2000")

    view = ConfirmBanRequestView(ctx.author.id, ctx.guild.id)

    try:
        dm_message = await ctx.author.send(embed=ban_request_embed, view=view)
        view.message = dm_message # Store the DM message to edit it later
        BAN_REQUEST_STATES[ctx.author.id] = {"state": "awaiting_payment_confirmation", "guild_id": ctx.guild.id}
        await ctx.send("I've sent you a DM to confirm your ban request. Please check your private messages.", ephemeral=True)
    except discord.Forbidden:
        await ctx.send("I couldn't send you a DM. Please make sure your DMs are open for me.", ephemeral=True)
        if ctx.author.id in BAN_REQUEST_STATES:
            del BAN_REQUEST_STATES[ctx.author.id]
    except Exception as e:
        print(f"Error sending initial ban request DM: {e}")
        await ctx.send("An unexpected error occurred while starting your ban request. Please try again later.", ephemeral=True)
        if ctx.author.id in BAN_REQUEST_STATES:
            del BAN_REQUEST_STATES[ctx.author.id]

@bot.event
async def on_message(message):
    # Ignore messages from bots to prevent loops
    if message.author.bot:
        return

    # Check if the message is a DM and if the user is in the ban request state
    if isinstance(message.channel, discord.DMChannel) and message.author.id in BAN_REQUEST_STATES:
        user_state = BAN_REQUEST_STATES[message.author.id]

        if user_state["state"] == "awaiting_userid":
            try:
                target_user_id = int(message.content.strip())
            except ValueError:
                await message.channel.send("Invalid User ID. Please send a valid numeric User ID.")
                return # Keep state as awaiting_userid until valid ID is provided

            requester = message.author
            guild = bot.get_guild(user_state["guild_id"])
            
            if not guild:
                await message.channel.send("It seems the server where you initiated the ban request is no longer accessible to me. Please try `!banrequest` again in the desired server.")
                if message.author.id in BAN_REQUEST_STATES:
                    del BAN_REQUEST_STATES[message.author.id]
                return

            log_channel = bot.get_channel(BAN_REQUEST_LOG_CHANNEL_ID)
            
            if not log_channel:
                await message.channel.send("Error: The ban request log channel could not be found or is inaccessible. Please contact a bot administrator.")
                if message.author.id in BAN_REQUEST_STATES:
                    del BAN_REQUEST_STATES[message.author.id]
                return

            target_member = None
            try:
                # Use guild.fetch_member to reliably get member object, even if not in cache
                target_member = await guild.fetch_member(target_user_id)
            except discord.NotFound:
                # User ID not found in the guild
                log_embed = discord.Embed(
                    title="🚨 Ban Request Log 🚨",
                    description=f"**Requester:** {requester.mention} (`{requester.id}`)\n"
                                f"**Requested Ban User ID:** `{target_user_id}`\n"
                                f"**Status:** User ID `{target_user_id}` not found in the server. No action taken.",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                log_embed.set_footer(text="made by summers 2000")
                await log_channel.send(embed=log_embed)
                await message.channel.send(f"The User ID `{target_user_id}` was not found in the server. Please ensure you provided a valid User ID from the server where you wish to ban them. The request has been logged.")
                del BAN_REQUEST_STATES[message.author.id]
                return
            except discord.Forbidden:
                # Bot does not have permission to fetch member
                log_embed = discord.Embed(
                    title="🚨 Ban Request Log 🚨",
                    description=f"**Requester:** {requester.mention} (`{requester.id}`)\n"
                                f"**Requested Ban User ID:** `{target_user_id}`\n"
                                f"**Status:** Bot missing permissions to fetch member in the server. Cannot process request.",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                log_embed.set_footer(text="made by summers 2000")
                await log_channel.send(embed=log_embed)
                await message.channel.send("I do not have the necessary permissions to fetch user details in the server. Please contact a bot administrator. The request has been logged.")
                del BAN_REQUEST_STATES[message.author.id]
                return
            except Exception as e:
                print(f"Error fetching member for ban request: {e}")
                log_embed = discord.Embed(
                    title="🚨 Ban Request Log 🚨",
                    description=f"**Requester:** {requester.mention} (`{requester.id}`)\n"
                                f"**Requested Ban User ID:** `{target_user_id}`\n"
                                f"**Status:** An unexpected error occurred while fetching user data. Cannot process request. Error: `{e}`",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                log_embed.set_footer(text="made by summers 2000")
                await log_channel.send(embed=log_embed)
                await message.channel.send(f"An unexpected error occurred while processing the User ID. The request has been logged.")
                del BAN_REQUEST_STATES[message.author.id]
                return

            # Check if target user has the boosting role
            if discord.utils.get(target_member.roles, id=BOOSTING_ROLE_ID):
                log_embed = discord.Embed(
                    title="🚨 Ban Request Log ?",
                    description=f"**Requester:** {requester.mention} (`{requester.id}`)\n"
                                f"**Target User:** {target_member.mention} (`{target_member.id}`)\n"
                                f"**Status:** This person cannot be banned because they are boosting.",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                log_embed.set_footer(text="made by summers 2000")
                await log_channel.send(embed=log_embed)
                await message.channel.send(f"The user {target_member.mention} cannot be banned because they are currently boosting the server. The request has been logged.")
            else:
                log_embed = discord.Embed(
                    title="🚨 Ban Request Log 🚨",
                    description=f"**Requester:** {requester.mention} (`{requester.id}`)\n"
                                f"**Target User:** {target_member.mention} (`{target_member.id}`)\n"
                                f"**Status:** Ban request received and logged. A moderator will review this. (User is NOT boosting)",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                log_embed.set_footer(text="made by summers 2000")
                await log_channel.send(embed=log_embed)
                await message.channel.send(f"Thank you! Your ban request for {target_member.mention} has been received and logged. A moderator will review this shortly.")

            # Remove user from state after processing
            del BAN_REQUEST_STATES[message.author.id]

    # Process other commands
    await bot.process_commands(message)

# --- Economy System Commands ---

@bot.command(name="balance", aliases=["wallet"])
async def balance_command(ctx):
    """
    Displays your current coin balance.
    Usage: !balance
    """
    user_id = ctx.author.id
    balance = user_balances.get(user_id, 0)
    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Balance",
        description=f"You have **`{balance}`** coins.",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="daily")
@commands.cooldown(1, DAILY_CLAIM_COOLDOWN, commands.BucketType.user)
async def daily_command(ctx):
    """
    Claim your daily coin bonus.
    Usage: !daily
    """
    user_id = ctx.author.id
    current_time = datetime.utcnow()
    
    # Check if the user has claimed before and if cooldown is active
    last_claim_time = last_daily_claim.get(user_id)
    if last_claim_time:
        time_since_last_claim = current_time - last_claim_time
        if time_since_last_claim.total_seconds() < DAILY_CLAIM_COOLDOWN:
            remaining_seconds = DAILY_CLAIM_COOLDOWN - time_since_last_claim.total_seconds()
            hours = int(remaining_seconds // 3600)
            minutes = int((remaining_seconds % 3600) // 60)
            seconds = int(remaining_seconds % 60)
            
            await ctx.send(f"You've already claimed your daily bonus! Please wait **{hours}h {minutes}m {seconds}s** before claiming again.")
            ctx.command.reset_cooldown(ctx) # Reset cooldown if they tried too early
            return

    daily_amount = random.randint(100, 200) # Give a random amount between 100 and 200 coins
    user_balances[user_id] = user_balances.get(user_id, 0) + daily_amount
    last_daily_claim[user_id] = current_time

    save_user_balances()
    save_last_daily_claim()

    embed = discord.Embed(
        title="Daily Bonus Claimed!",
        description=f"You received **`{daily_amount}`** coins!",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(user_id, "FIRST_DAILY_CLAIM", ctx)

@bot.command(name="transfer")
async def transfer_command(ctx, member: discord.Member, amount: int):
    """
    Send coins to another user.
    Usage: !transfer <@user> <amount>
    """
    if amount <= 0:
        await ctx.send("You can only transfer positive amounts of coins.")
        return
    if member.bot:
        await ctx.send("You cannot transfer coins to a bot!")
        return
    if member.id == ctx.author.id:
        await ctx.send("You cannot transfer coins to yourself.")
        return

    sender_id = ctx.author.id
    receiver_id = member.id

    if user_balances.get(sender_id, 0) < amount:
        await ctx.send(f"You don't have enough coins to transfer `{amount}`. Your current balance is `{user_balances.get(sender_id, 0)}`.")
        return

    user_balances[sender_id] -= amount
    user_balances[receiver_id] = user_balances.get(receiver_id, 0) + amount

    save_user_balances()

    embed = discord.Embed(
        title="Coin Transfer Successful!",
        description=f"**`{amount}`** coins transferred from {ctx.author.mention} to {member.mention}.",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="shop")
async def shop_command(ctx, category: str = None):
    """
    View items available for purchase.
    Usage: !shop [category]
    Categories: consumable, lootbox, material, all
    """
    embed = discord.Embed(
        title="Shop Items",
        description="Available items for purchase:",
        color=discord.Color.purple(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    found_items = False
    for item_key, item_data in SHOP_ITEMS.items():
        item_display_name = item_data.get("display_name", item_key.replace('_', ' ').title())
        item_price = item_data.get("price")
        item_description = item_data.get("description", "No description.")
        item_type = item_data.get("type", "misc")

        # Filter by category if provided
        if category and category.lower() != "all" and item_type != category.lower():
            continue

        if item_price is not None: # Only show items with a price
            found_items = True
            embed.add_field(
                name=f"🛒 {item_display_name} - `{item_price}` coins",
                value=f"Type: `{item_type.capitalize()}`\nDescription: `{item_description}`",
                inline=False
            )
    
    if not found_items:
        if category:
            embed.description = f"No items found in the `{category}` category."
        else:
            embed.description = "No items available in the shop right now."
    
    await ctx.send(embed=embed)

@bot.command(name="buy")
async def buy_command(ctx, item_name: str, quantity: int = 1):
    """
    Buy an item from the shop.
    Usage: !buy <item_name> [quantity]
    """
    item_name_lower = item_name.lower()
    item_found = None
    for key, data in SHOP_ITEMS.items():
        if data.get("display_name", key).lower() == item_name_lower or key == item_name_lower:
            item_found = {**data, "key": key} # Add original key for accurate reference
            break
    
    if item_found is None:
        await ctx.send(f"Item `{item_name}` not found in the shop.")
        return
    
    if item_found["price"] is None:
        await ctx.send(f"Item `{item_found['display_name']}` cannot be purchased directly from the shop.")
        return

    if quantity <= 0:
        await ctx.send("You must buy at least one item.")
        return

    total_cost = item_found["price"] * quantity
    user_id = ctx.author.id

    if user_balances.get(user_id, 0) < total_cost:
        await ctx.send(f"You don't have enough coins. You need `{total_cost}` coins, but you only have `{user_balances.get(user_id, 0)}`.")
        return

    user_balances[user_id] -= total_cost
    user_inventories.setdefault(user_id, {})
    user_inventories[user_id][item_found["display_name"]] = user_inventories[user_id].get(item_found["display_name"], 0) + quantity

    save_user_balances()
    save_user_inventories()

    embed = discord.Embed(
        title="Purchase Successful!",
        description=f"You bought `{quantity}x {item_found['display_name']}` for **`{total_cost}`** coins.",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="sell")
async def sell_command(ctx, item_name: str, quantity: int = 1):
    """
    Sell an item from your inventory.
    Usage: !sell <item_name> [quantity]
    """
    user_id = ctx.author.id
    if user_id not in user_inventories or not user_inventories[user_id]:
        await ctx.send("Your inventory is empty!")
        return

    item_name_lower = item_name.lower()
    item_in_inventory = None
    for inv_item_name in user_inventories[user_id].keys():
        if inv_item_name.lower() == item_name_lower:
            item_in_inventory = inv_item_name
            break
    
    if item_in_inventory is None:
        await ctx.send(f"You don't have `{item_name}` in your inventory.")
        return

    current_quantity = user_inventories[user_id].get(item_in_inventory, 0)
    if current_quantity < quantity:
        await ctx.send(f"You only have `{current_quantity}` of `{item_in_inventory}`.")
        return
    
    if quantity <= 0:
        await ctx.send("You must sell at least one item.")
        return

    # Find sell price from SHOP_ITEMS or CRAFTING_RECIPES
    item_data = None
    for key, data in SHOP_ITEMS.items():
        if data.get("display_name", key).lower() == item_in_inventory.lower() or key == item_in_inventory.lower():
            item_data = data
            break
    if item_data is None: # Check crafting recipes if not found in shop items
        for key, data in CRAFTING_RECIPES.items():
            if data.get("display_name", key).lower() == item_in_inventory.lower() or key == item_in_inventory.lower():
                item_data = data
                break

    if item_data is None or item_data.get("sell_price") is None:
        await ctx.send(f"Item `{item_in_inventory}` cannot be sold.")
        return

    sell_price = item_data["sell_price"] * quantity
    user_inventories[user_id][item_in_inventory] -= quantity
    if user_inventories[user_id][item_in_inventory] <= 0:
        del user_inventories[user_id][item_in_inventory]
        if not user_inventories[user_id]: # If inventory becomes empty, remove user entry
            del user_inventories[user_id]

    user_balances[user_id] = user_balances.get(user_id, 0) + sell_price

    save_user_balances()
    save_user_inventories()

    embed = discord.Embed(
        title="Sale Successful!",
        description=f"You sold `{quantity}x {item_in_inventory}` for **`{sell_price}`** coins.",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="inventory")
async def inventory_command(ctx):
    """
    View your current items.
    Usage: !inventory
    """
    user_id = ctx.author.id
    inventory = user_inventories.get(user_id, {})

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Inventory",
        color=discord.Color.greyple(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    if not inventory:
        embed.description = "Your inventory is empty. Use `!shop` to buy some items!"
    else:
        description_lines = []
        for item_name, quantity in inventory.items():
            description_lines.append(f"**`{item_name}`**: `{quantity}`")
        embed.description = "\n".join(description_lines)
    
    await ctx.send(embed=embed)

@bot.command(name="use")
async def use_command(ctx, *, item_name: str):
    """
    Use a consumable item from your inventory.
    Usage: !use <item_name>
    """
    user_id = ctx.author.id
    inventory = user_inventories.get(user_id, {})
    item_name_lower = item_name.lower()

    item_to_use = None
    for inv_item_name in inventory.keys():
        if inv_item_name.lower() == item_name_lower:
            item_to_use = inv_item_name
            break

    if item_to_use is None or inventory.get(item_to_use, 0) < 1:
        await ctx.send(f"You don't have `{item_name}` in your inventory to use.")
        return

    # Check if the item is actually consumable from SHOP_ITEMS or CRAFTING_RECIPES
    item_data = None
    for key, data in SHOP_ITEMS.items():
        if data.get("display_name", key).lower() == item_to_use.lower() or key == item_to_use.lower():
            item_data = data
            break
    if item_data is None:
        for key, data in CRAFTING_RECIPES.items():
            if data.get("display_name", key).lower() == item_to_use.lower() or key == item_to_use.lower():
                item_data = data
                break

    if item_data is None or item_data.get("type") != "consumable":
        await ctx.send(f"`{item_to_use}` is not a consumable item.")
        return
    
    user_inventories[user_id][item_to_use] -= 1
    if user_inventories[user_id][item_to_use] <= 0:
        del user_inventories[user_id][item_to_use]
        if not user_inventories[user_id]:
            del user_inventories[user_id]
    
    save_user_inventories()

    embed = discord.Embed(
        title="Item Used!",
        description=f"You successfully used **`{item_to_use}`**.",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    # Add a placeholder for the effect of the item
    if item_to_use.lower() == "xp boost":
        embed.add_field(name="Effect", value="Your XP gain is temporarily boosted!", inline=False)
    elif item_to_use.lower() == "token of fortune":
        embed.add_field(name="Effect", value="Your luck in minigames has increased!", inline=False)
    elif item_to_use.lower() == "super boost":
        embed.add_field(name="Effect", value="You feel supercharged with both XP and luck!", inline=False)
    else:
        embed.add_field(name="Effect", value="The item had its effect! (Effect not specified in code)", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="craft")
async def craft_command(ctx, *, recipe_name: str):
    """
    Craft an item from ingredients.
    Usage: !craft <recipe_name>
    """
    user_id = ctx.author.id
    inventory = user_inventories.get(user_id, {})

    recipe_name_lower = recipe_name.lower()
    recipe_found = None
    for key, data in CRAFTING_RECIPES.items():
        if data.get("display_name", key).lower() == recipe_name_lower or key == recipe_name_lower:
            recipe_found = data
            break
    
    if recipe_found is None:
        await ctx.send(f"Recipe for `{recipe_name}` not found. Use `!recipes` to see available recipes.")
        return

    # Check if user has all ingredients
    missing_ingredients = []
    for ingredient, required_quantity in recipe_found["ingredients"].items():
        if inventory.get(ingredient, 0) < required_quantity:
            missing_ingredients.append(f"`{required_quantity}x {ingredient}` (have `{inventory.get(ingredient, 0)}`)")
    
    if missing_ingredients:
        await ctx.send(f"You are missing the following ingredients to craft `{recipe_found['display_name']}`:\n" + "\n".join(missing_ingredients))
        return

    # Deduct ingredients
    for ingredient, required_quantity in recipe_found["ingredients"].items():
        user_inventories[user_id][ingredient] -= required_quantity
        if user_inventories[user_id][ingredient] <= 0:
            del user_inventories[user_id][ingredient]
    
    # Add crafted output
    user_inventories.setdefault(user_id, {})
    for output_item, output_quantity in recipe_found["output"].items():
        user_inventories[user_id][output_item] = user_inventories[user_id].get(output_item, 0) + output_quantity

    if not user_inventories[user_id]: # Clean up user entry if inventory becomes empty
            del user_inventories[user_id]

    save_user_inventories()

    embed = discord.Embed(
        title="Crafting Successful!",
        description=f"You successfully crafted **`{recipe_found['display_name']}`**!",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="recipes")
async def recipes_command(ctx):
    """
    View available crafting recipes.
    Usage: !recipes
    """
    embed = discord.Embed(
        title="Crafting Recipes",
        description="Available recipes:",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    if not CRAFTING_RECIPES:
        embed.description = "No crafting recipes defined yet."
    else:
        for recipe_key, recipe_data in CRAFTING_RECIPES.items():
            ingredients_list = ", ".join([f"{qty}x {item}" for item, qty in recipe_data["ingredients"].items()])
            output_list = ", ".join([f"{qty}x {item}" for item, qty in recipe_data["output"].items()])
            
            embed.add_field(
                name=f"🛠️ {recipe_data.get('display_name', recipe_key.replace('_', ' ').title())}",
                value=f"**Ingredients:** `{ingredients_list}`\n**Output:** `{output_list}`\nDescription: `{recipe_data.get('description', 'No description.')}`",
                inline=False
            )
    await ctx.send(embed=embed)

@bot.command(name="iteminfo")
async def iteminfo_command(ctx, *, item_name: str):
    """
    Get information about a specific item.
    Usage: !iteminfo <item_name>
    """
    item_name_lower = item_name.lower()
    item_data = None

    # Check shop items
    for key, data in SHOP_ITEMS.items():
        if data.get("display_name", key).lower() == item_name_lower or key == item_name_lower:
            item_data = data
            item_data["source"] = "Shop"
            break
    
    # Check crafting recipes if not found in shop items
    if item_data is None:
        for key, data in CRAFTING_RECIPES.items():
            if data.get("display_name", key).lower() == item_name_lower or key == item_name_lower:
                item_data = data
                item_data["source"] = "Crafting"
                break

    if item_data is None:
        await ctx.send(f"Item `{item_name}` not found in the bot's item database.")
        return

    embed = discord.Embed(
        title=f"ℹ️ Item Info: {item_data.get('display_name', item_name)}",
        description=item_data.get("description", "No description provided."),
        color=discord.Color.teal(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    if item_data.get("price") is not None:
        embed.add_field(name="Buy Price", value=f"`{item_data['price']}` coins", inline=True)
    if item_data.get("sell_price") is not None:
        embed.add_field(name="Sell Price", value=f"`{item_data['sell_price']}` coins", inline=True)
    
    embed.add_field(name="Type", value=f"`{item_data.get('type', 'N/A').capitalize()}`", inline=True)
    embed.add_field(name="Source", value=f"`{item_data.get('source', 'N/A')}`", inline=True)

    if item_data.get("source") == "Crafting":
        ingredients_list = "\n".join([f"- `{qty}x {item}`" for item, qty in item_data["ingredients"].items()])
        embed.add_field(name="Ingredients", value=ingredients_list, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="richest")
async def richest_command(ctx):
    """
    See the top users by coin balance.
    Usage: !richest
    """
    if not user_balances:
        await ctx.send("No users have coins yet!")
        return

    # Filter out users with 0 balance if desired, or keep everyone
    sorted_balances = sorted([
        (user_id, balance) for user_id, balance in user_balances.items() if balance > 0
    ], key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="💰 Richest Users Leaderboard �",
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    description = ""
    for i, (user_id, balance) in enumerate(sorted_balances[:10]): # Top 10
        user = bot.get_user(user_id) or await bot.fetch_user(user_id) # Fetch user if not in cache
        user_name = user.display_name if user else f"Unknown User (ID: {user_id})"
        description += f"**{i+1}. {user_name}** - `{balance}` coins\n"
    
    if not description:
        embed.description = "No users with a positive coin balance found."
    else:
        embed.description = description
    
    await ctx.send(embed=embed)

@bot.command(name="coinflip")
async def coinflip_command(ctx, amount: int, choice: str = None):
    """
    Bet coins on a coin flip.
    Usage: !coinflip <amount> [heads/tails]
    """
    if amount <= 0:
        await ctx.send("You must bet a positive amount of coins.")
        return
    if user_balances.get(ctx.author.id, 0) < amount:
        await ctx.send(f"You don't have enough coins to bet `{amount}`. Your current balance is `{user_balances.get(ctx.author.id, 0)}`.")
        return

    valid_choices = ["heads", "tails", "h", "t"]
    if choice and choice.lower() not in valid_choices:
        await ctx.send("Invalid choice. Please choose `heads` or `tails`.")
        return
    
    result = random.choice(["heads", "tails"])
    
    embed = discord.Embed(
        title="Coin Flip!",
        description=f"The coin landed on **`{result.upper()}`**!",
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")

    won = False
    if choice is None: # No choice made, just show result
        embed.color = discord.Color.light_grey()
        embed.add_field(name="Bet", value="No specific choice made.", inline=False)
    elif result.lower() == choice.lower() or (choice.lower() == "h" and result == "heads") or (choice.lower() == "t" and result == "tails"):
        user_balances[ctx.author.id] += amount
        won = True
        embed.color = discord.Color.green()
        embed.add_field(name="Outcome", value=f"You guessed correctly and won **`{amount}`** coins!", inline=False)
    else:
        user_balances[ctx.author.id] -= amount
        embed.color = discord.Color.red()
        embed.add_field(name="Outcome", value=f"You guessed incorrectly and lost **`{amount}`** coins.", inline=False)

    save_user_balances()
    embed.add_field(name="Your New Balance", value=f"`{user_balances.get(ctx.author.id, 0)}` coins", inline=False)
    await ctx.send(embed=embed)

# --- Run the Bot ---
# Get the bot token from an environment variable (e.g., DISCORD_TOKEN in Railway)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if DISCORD_TOKEN is None:
    print("\n!!! CRITICAL ERROR: DISCORD_TOKEN environment variable is not set. !!!")
    print("Please ensure you have set the 'DISCORD_TOKEN' environment variable in Railway.")
    print("The bot cannot start without a token.")
    exit(1) # Exit the script if no token is found

try:
    bot.run(DISCORD_TOKEN)
except discord.LoginFailure:
    print("\n!!! LOGIN FAILED: Invalid token or connection issue. !!!")
    print("Please check your DISCORD_TOKEN environment variable in Railway. It might be incorrect or expired.")
except discord.HTTPException as e:
    print(f"\n!!! HTTP EXCEPTION DURING LOGIN: {e} !!!")
    print("This often indicates a problem with Discord's API or your network connection.")
except Exception as e:
    print(f"\n!!! AN UNEXPECTED ERROR OCCURRED DURING BOT STARTUP: {e} !!!")
