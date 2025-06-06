import os
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
import json
import re # For parsing reminder time, tempmute duration
import random # For games, 8ball, fact, joke, ship

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
intents.reactions = True        # Required for polls and reaction roles
intents.guilds = True           # Required for serverinfo, channelinfo, roleinfo, audit logs

bot = commands.Bot(command_prefix=("!", ":"), intents=intents)
bot.remove_command('help') # This line removes the default help command

# --- Global Variables for New Features ---
# Bot start time for uptime command
BOT_START_TIME = datetime.now(timezone.utc)

# --- Game States ---
active_c4_games = {} # {channel_id: Connect4Game instance}
active_tictactoe_games = {} # {channel_id: TicTacToeGame instance}

# --- Data Storage File Paths ---
GAME_STATS_FILE = 'game_stats.json'
ACHIEVEMENTS_FILE = 'achievements.json'
REMINDERS_FILE = 'reminders.json'
USER_BALANCES_FILE = 'user_balances.json'
USER_INVENTORIES_FILE = 'user_inventories.json'
LAST_DAILY_CLAIM_FILE = 'last_daily_claim.json'
LOTTO_FILE = 'lotto.json'
POLL_DATA_FILE = 'polls.json' # For ongoing polls
WARNINGS_FILE = 'warnings.json' # For user warnings
QUOTES_FILE = 'quotes.json' # For !quote_add and !quote_random
DAILY_STREAKS_FILE = 'daily_streaks.json' # For !daily_streak
REACTION_ROLES_FILE = 'reaction_roles.json' # For !reactionrole
ANTI_NUKE_CONFIG_FILE = 'anti_nuke_config.json' # For anti-nuke settings
ANTI_NUKE_LOG_FILE = 'anti_nuke_log.json' # For logging anti-nuke events
MOD_LOG_CHANNEL_FILE = 'mod_log_channel.json' # To store the moderation log channel ID

# --- In-memory Data Structures ---
game_stats = {} # {user_id: {"c4_wins": X, "c4_losses": Y, "c4_draws": Z, "ttt_wins": X, ...}}
achievements = {} # {user_id: ["achievement_id_1", "achievement_id_2"]}
reminders = [] # [{"user_id": ..., "remind_time": timestamp, "message": "..."}]
user_balances = {} # {user_id: amount}
user_inventories = {} # {user_id: {item_name: quantity}}
last_daily_claim = {} # {user_id: timestamp_utc}
LOTTO_TICKETS = {} # {user_id: quantity}
LOTTO_POT = 0      # Current coin amount in the lottery pot
polls = {} # {message_id: {"channel_id": int, "question": str, "options": [], "votes": {emoji: [user_ids]}}}
warnings = {} # {guild_id: {user_id: [{"id": str, "reason": str, "timestamp": str, "moderator_id": int}]}}
quotes = [] # [{"text": "...", "author": "..."}]
daily_streaks = {} # {user_id: {"current_streak": int, "last_claim_date": str}}
reaction_roles = {} # {guild_id: {message_id: {emoji: role_id}}}

# --- Economy System Variables ---
DAILY_CLAIM_COOLDOWN = 24 * 3600 # 24 hours in seconds
LOTTO_TICKET_PRICE = 100 # Price per lottery ticket
LOTTO_MIN_PLAYERS = 2 # Minimum players for a lottery draw

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

# --- Ban Request Specifics ---
BAN_REQUEST_LOG_CHANNEL_ID = 1379985805027840120 # Channel to send ban request logs
BOOSTING_ROLE_ID = 1302076375922118696 # Role ID for users who cannot be banned
BAN_REQUEST_STATES = {} # {user_id: {"state": "awaiting_payment_confirmation" | "awaiting_userid", "guild_id": int}}

# --- Anti-Nuke System Variables ---
ANTI_NUKE_ENABLED = False
SAFE_MODE_ENABLED = False
MOD_WHITELIST_ROLES = [] # List of role IDs
MOD_WHITELIST_USERS = [] # List of user IDs
NUKE_THRESHOLDS = { # Default thresholds
    "channel_delete": {"count": 5, "time_period": 30}, # 5 channels deleted in 30 seconds
    "member_ban": {"count": 3, "time_period": 30},     # 3 members banned in 30 seconds
    "member_kick": {"count": 5, "time_period": 30},    # 5 members kicked in 30 seconds
    "role_permission_escalation": {"count": 1, "time_period": 10}, # 1 role permission escalation in 10s
}
ANTI_NUKE_LOGS = [] # Stores a history of anti-nuke events

# Activity tracking for anti-nuke
# {guild_id: {user_id: {"channel_delete": [], "member_ban": [], "member_kick": [], "role_permission_escalation": []}}}
SUSPICIOUS_ACTIVITY = {}

MOD_LOG_CHANNEL_ID = None # Stored channel ID for general moderation logs

# --- Achievement Definitions ---
ACHIEVEMENT_DEFINITIONS = {
    "FIRST_C4_WIN": "First Connect4 Victory!",
    "FIRST_TTT_WIN": "First Tic-Tac-Toe Victory!",
    "FIRST_REMINDER_SET": "Time Bender!",
    "FIVE_C4_WINS": "Connect4 Pro!",
    "FIVE_TTT_WINS": "Tic-Tac-Toe Master!",
    "FIRST_DAILY_CLAIM": "Daily Dough Getter!",
    "FIRST_ROLL_COMMAND": "First Roll!",
    "FIRST_LOTTO_ENTRY": "Lottery Enthusiast!",
    "FIRST_POLL_CREATED": "Pollster Extraordinaire!",
    "FIRST_WARNING": "First Warning Issued!",
    "FIRST_QUOTE_ADDED": "Wordsmith!",
    "FIRST_DAILY_STREAK_5": "Daily Streak Initiate (5 Days)!",
    "FIRST_BLACKJACK_WIN": "Blackjack Ace!",
    "FIRST_SLOTS_WIN": "Slot Machine Master!",
    "FIRST_SHIP": "Matchmaker!"
}

# --- Helper Functions for Data Persistence (JSON files) ---
def load_data(file_path, default_data={}):
    """Loads data from a JSON file, returning default_data if file not found or corrupted."""
    print(f"Attempting to load data from {file_path}...")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                data = json.load(f)
                print(f"Successfully loaded data from {file_path}.")
                return data
            except json.JSONDecodeError as e:
                print(f"ERROR: JSON decoding failed for {file_path}. File might be empty or corrupted: {e}. Returning default data.")
                return default_data
            except Exception as e:
                print(f"ERROR: An unexpected error occurred while reading {file_path}: {e}. Returning default data.")
                return default_data
    else:
        print(f"INFO: {file_path} not found. Starting with default data.")
        return default_data

def save_data(file_path, data):
    """Saves data to a JSON file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        print(f"Successfully saved data to {file_path}.")
    except Exception as e:
        print(f"ERROR: Failed to save data to {file_path}: {e}")

# --- Data Persistence Load/Save Functions ---
def load_user_balances():
    global user_balances
    user_balances_raw = load_data(USER_BALANCES_FILE, {})
    user_balances = {int(k): v for k, v in user_balances_raw.items()}

def save_user_balances():
    save_data(USER_BALANCES_FILE, {str(k): v for k, v in user_balances.items()})

def load_user_inventories():
    global user_inventories
    user_inventories_raw = load_data(USER_INVENTORIES_FILE, {})
    user_inventories = {int(k): v for k, v in user_inventories_raw.items()}

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
            print(f"WARNING: Error loading last daily claim for user {user_id_str}: {e}. Skipping entry.")

def save_last_daily_claim():
    claims_to_save = {str(k): v.isoformat() for k, v in last_daily_claim.items()}
    save_data(LAST_DAILY_CLAIM_FILE, claims_to_save)

def load_game_stats():
    global game_stats
    game_stats_raw = load_data(GAME_STATS_FILE, {})
    game_stats = {int(user_id): data for user_id, data in game_stats_raw.items()}

def save_game_stats():
    save_data(GAME_STATS_FILE, {str(user_id): data for user_id, data in game_stats.items()})

def update_game_stats(user_id, game_type, result_type):
    game_stats.setdefault(user_id, {"c4_wins": 0, "c4_losses": 0, "c4_draws": 0, "ttt_wins": 0, "ttt_losses": 0, "ttt_draws": 0})
    if game_type == "c4":
        if result_type == "win": game_stats[user_id]["c4_wins"] += 1
        elif result_type == "loss": game_stats[user_id]["c4_losses"] += 1
        elif result_type == "draw": game_stats[user_id]["c4_draws"] += 1
    elif game_type == "ttt":
        if result_type == "win": game_stats[user_id]["ttt_wins"] += 1
        elif result_type == "loss": game_stats[user_id]["ttt_losses"] += 1
        elif result_type == "draw": game_stats[user_id]["ttt_draws"] += 1
    save_game_stats()

def load_achievements():
    global achievements
    achievements_raw = load_data(ACHIEVEMENTS_FILE, {})
    achievements = {int(user_id): data for user_id, data in achievements_raw.items()}

def save_achievements():
    save_data(ACHIEVEMENTS_FILE, {str(user_id): data for user_id, data in achievements.items()})

async def check_achievement(user_id, achievement_id, ctx=None):
    if user_id not in achievements:
        achievements[user_id] = []
    
    if achievement_id not in achievements[user_id]:
        achievements[user_id].append(achievement_id)
        save_achievements()
        achievement_name = ACHIEVEMENT_DEFINITIONS.get(achievement_id, achievement_id.replace('_', ' ').title())
        print(f"User {user_id} earned achievement: {achievement_name}")
        if ctx:
            try:
                embed = discord.Embed(
                    title="Achievement Unlocked!",
                    description=f"🎉 Congratulations, {ctx.author.mention}! You've earned the achievement: **{achievement_name}**!",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text="made by summers 2000")
                await ctx.send(embed=embed)
            except discord.Forbidden:
                print(f"WARNING: Could not send achievement message to channel {ctx.channel.id} for user {user_id} (Forbidden).")
            except Exception as e:
                print(f"ERROR: Error sending achievement message for user {user_id}: {e}")

def load_reminders():
    global reminders
    reminders_raw = load_data(REMINDERS_FILE, [])
    reminders = []
    for r in reminders_raw:
        try:
            r['remind_time'] = datetime.fromisoformat(r['remind_time']).astimezone(timezone.utc)
            reminders.append(r)
        except (ValueError, KeyError) as e:
            print(f"WARNING: Error loading reminder: {e}. Skipping entry.")
    reminders.sort(key=lambda x: x['remind_time'])

def save_reminders():
    reminders_to_save = []
    for r in reminders:
        r_copy = r.copy()
        r_copy['remind_time'] = r_copy['remind_time'].isoformat()
        reminders_to_save.append(r_copy)
    save_data(REMINDERS_FILE, reminders_to_save)

def load_lotto_data():
    global LOTTO_TICKETS, LOTTO_POT
    lotto_data = load_data(LOTTO_FILE, {"tickets": {}, "pot": 0})
    LOTTO_TICKETS = {int(k): v for k, v in lotto_data.get("tickets", {}).items()}
    LOTTO_POT = lotto_data.get("pot", 0)

def save_lotto_data():
    lotto_data = {
        "tickets": {str(k): v for k, v in LOTTO_TICKETS.items()},
        "pot": LOTTO_POT
    }
    save_data(LOTTO_FILE, lotto_data)

def load_polls():
    global polls
    polls_raw = load_data(POLL_DATA_FILE, {})
    polls = {}
    for msg_id_str, poll_data in polls_raw.items():
        # Ensure user IDs in votes are integers
        cleaned_votes = {emoji: [int(uid) for uid in uids] for emoji, uids in poll_data["votes"].items()}
        polls[int(msg_id_str)] = {
            "channel_id": poll_data["channel_id"],
            "question": poll_data["question"],
            "options": poll_data["options"],
            "votes": cleaned_votes
        }

def save_polls():
    polls_to_save = {}
    for msg_id, poll_data in polls.items():
        # Convert user IDs in votes to strings for JSON serialization
        votes_to_save = {emoji: [str(uid) for uid in uids] for emoji, uids in poll_data["votes"].items()}
        polls_to_save[str(msg_id)] = {
            "channel_id": poll_data["channel_id"],
            "question": poll_data["question"],
            "options": poll_data["options"],
            "votes": votes_to_save
        }
    save_data(POLL_DATA_FILE, polls_to_save)

def load_warnings():
    global warnings
    warnings_raw = load_data(WARNINGS_FILE, {})
    warnings = {}
    for guild_id_str, guild_warnings in warnings_raw.items():
        user_warnings = {}
        for user_id_str, warns_list in guild_warnings.items():
            parsed_warns = []
            for warn in warns_list:
                try:
                    warn_copy = warn.copy()
                    warn_copy["timestamp"] = datetime.fromisoformat(warn["timestamp"]).astimezone(timezone.utc)
                    parsed_warns.append(warn_copy)
                except (ValueError, KeyError) as e:
                    print(f"WARNING: Error loading warning for user {user_id_str} in guild {guild_id_str}: {e}. Skipping entry.")
            user_warnings[int(user_id_str)] = parsed_warns
        warnings[int(guild_id_str)] = user_warnings

def save_warnings():
    warnings_to_save = {}
    for guild_id, guild_warnings in warnings.items():
        user_warnings_to_save = {}
        for user_id, warns_list in guild_warnings.items():
            warns_str_timestamp = []
            for warn in warns_list:
                warn_copy = warn.copy()
                warn_copy["timestamp"] = warn_copy["timestamp"].isoformat()
                warns_str_timestamp.append(warn_copy)
            user_warnings_to_save[str(user_id)] = warns_str_timestamp
        warnings_to_save[str(guild_id)] = user_warnings_to_save
    save_data(WARNINGS_FILE, warnings_to_save)

def load_quotes():
    global quotes
    quotes = load_data(QUOTES_FILE, [])

def save_quotes():
    save_data(QUOTES_FILE, quotes)

def load_daily_streaks():
    global daily_streaks
    daily_streaks_raw = load_data(DAILY_STREAKS_FILE, {})
    daily_streaks = {}
    for user_id_str, streak_data in daily_streaks_raw.items():
        # last_claim_date is stored as YYYY-MM-DD string
        daily_streaks[int(user_id_str)] = streak_data

def save_daily_streaks():
    save_data(DAILY_STREAKS_FILE, {str(k): v for k, v in daily_streaks.items()})

def load_reaction_roles():
    global reaction_roles
    reaction_roles_raw = load_data(REACTION_ROLES_FILE, {})
    reaction_roles = {}
    for guild_id_str, guild_data in reaction_roles_raw.items():
        message_data = {}
        for msg_id_str, emoji_role_map in guild_data.items():
            # Convert message ID string to int
            message_data[int(msg_id_str)] = emoji_role_map
        reaction_roles[int(guild_id_str)] = message_data

def save_reaction_roles():
    reaction_roles_to_save = {}
    for guild_id, guild_data in reaction_roles.items():
        message_data_to_save = {}
        for msg_id, emoji_role_map in guild_data.items():
            # Convert message ID int to string for saving
            message_data_to_save[str(msg_id)] = emoji_role_map
        reaction_roles_to_save[str(guild_id)] = message_data_to_save
    save_data(REACTION_ROLES_FILE, reaction_roles_to_save)

def load_anti_nuke_config():
    global ANTI_NUKE_ENABLED, SAFE_MODE_ENABLED, MOD_WHITELIST_ROLES, MOD_WHITELIST_USERS, NUKE_THRESHOLDS, MOD_LOG_CHANNEL_ID
    config = load_data(ANTI_NUKE_CONFIG_FILE, {
        "enabled": False,
        "safe_mode": False,
        "mod_whitelist_roles": [],
        "mod_whitelist_users": [],
        "thresholds": {
            "channel_delete": {"count": 5, "time_period": 30},
            "member_ban": {"count": 3, "time_period": 30},
            "member_kick": {"count": 5, "time_period": 30},
            "role_permission_escalation": {"count": 1, "time_period": 10},
        },
        "mod_log_channel_id": None
    })
    ANTI_NUKE_ENABLED = config.get("enabled", False)
    SAFE_MODE_ENABLED = config.get("safe_mode", False)
    MOD_WHITELIST_ROLES = [int(r) for r in config.get("mod_whitelist_roles", [])]
    MOD_WHITELIST_USERS = [int(u) for u in config.get("mod_whitelist_users", [])]
    NUKE_THRESHOLDS = config.get("thresholds", NUKE_THRESHOLDS)
    MOD_LOG_CHANNEL_ID = config.get("mod_log_channel_id", None)
    if MOD_LOG_CHANNEL_ID: MOD_LOG_CHANNEL_ID = int(MOD_LOG_CHANNEL_ID) # Ensure int

def save_anti_nuke_config():
    config = {
        "enabled": ANTI_NUKE_ENABLED,
        "safe_mode": SAFE_MODE_ENABLED,
        "mod_whitelist_roles": [str(r) for r in MOD_WHITELIST_ROLES],
        "mod_whitelist_users": [str(u) for u in MOD_WHITELIST_USERS],
        "thresholds": NUKE_THRESHOLDS,
        "mod_log_channel_id": str(MOD_LOG_CHANNEL_ID) if MOD_LOG_CHANNEL_ID else None
    }
    save_data(ANTI_NUKE_CONFIG_FILE, config)

def load_anti_nuke_logs():
    global ANTI_NUKE_LOGS
    ANTI_NUKE_LOGS_raw = load_data(ANTI_NUKE_LOG_FILE, [])
    ANTI_NUKE_LOGS = []
    for log_entry in ANTI_NUKE_LOGS_raw:
        try:
            log_entry_copy = log_entry.copy()
            log_entry_copy["timestamp"] = datetime.fromisoformat(log_entry["timestamp"]).astimezone(timezone.utc)
            ANTI_NUKE_LOGS.append(log_entry_copy)
        except (ValueError, KeyError) as e:
            print(f"WARNING: Error loading anti-nuke log entry: {e}. Skipping entry.")

def save_anti_nuke_logs():
    logs_to_save = []
    for log_entry in ANTI_NUKE_LOGS:
        log_entry_copy = log_entry.copy()
        log_entry_copy["timestamp"] = log_entry_copy["timestamp"].isoformat()
        logs_to_save.append(log_entry_copy)
    save_data(ANTI_NUKE_LOG_FILE, logs_to_save)

async def send_mod_log(guild, title, description, color, author=None, target=None):
    if MOD_LOG_CHANNEL_ID:
        channel = guild.get_channel(MOD_LOG_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text="made by summers 2000")
            if author:
                embed.add_field(name="Responsible User", value=f"{author.mention} (`{author.id}`)", inline=False)
            if target:
                embed.add_field(name="Target User/Item", value=f"{target.mention if isinstance(target, discord.Member) else target} (`{target.id if hasattr(target, 'id') else 'N/A'}`)", inline=False)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                print(f"WARNING: Bot forbidden from sending mod log to channel {MOD_LOG_CHANNEL_ID}.")
            except Exception as e:
                print(f"ERROR: Error sending mod log: {e}")
        else:
            print(f"WARNING: Mod log channel with ID {MOD_LOG_CHANNEL_ID} not found or inaccessible.")


# --- Helper Functions for API Calls (General purpose) ---
async def fetch_api_data(url, method='GET', json_data=None):
    """Fetches data from a given API URL."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(method, url, json=json_data) as response:
                response.raise_for_status() 
                try:
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        return await response.json()
                    else:
                        return await response.text() # Fallback to text if not JSON
                except aiohttp.ContentTypeError:
                    return await response.text()
        except aiohttp.ClientResponseError as e:
            print(f"API Error (HTTP Status {e.status}) for {url}: {e.message}")
            return None
        except aiohttp.ClientConnectorError as e:
            print(f"API Client Connector Error for {url}: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during API fetch for {url}: {e}")
            return None

# --- Events ---
@bot.event
async def on_ready():
    global BOT_START_TIME
    BOT_START_TIME = datetime.now(timezone.utc)
    print(f"Bot logged in as {bot.user.name} (ID: {bot.user.id})")
    print("Bot is ready to receive commands!")
    
    # Load all persistent data
    print("Loading persistent data...")
    load_game_stats()
    load_achievements()
    load_reminders()
    load_user_balances()
    load_user_inventories()
    load_last_daily_claim()
    load_lotto_data()
    load_polls()
    load_warnings()
    load_quotes()
    load_daily_streaks()
    load_reaction_roles()
    load_anti_nuke_config()
    load_anti_nuke_logs()
    print("All persistent data loaded.")

    # Start tasks
    if not reminder_checker.is_running():
        reminder_checker.start()
        print("Reminder checker task started.")

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
    elif isinstance(error, commands.CheckFailure): # Handle custom permission/role checks (e.g. from check_any)
        embed = discord.Embed(
            title="Permission Denied",
            description=f"You do not have the necessary permissions or role to use the `!{ctx.command.name}` command.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed, delete_after=10)
    else:
        print(f"ERROR: An unhandled error occurred in command '{ctx.command.name}': {error}")
        embed = discord.Embed(
            title="Command Error",
            description=f"**An unexpected error occurred:** `{error}`. My apologies! Please try again later or contact an administrator.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)

# --- Uptime Command (existing) ---
@bot.command(name="uptime")
async def uptime_command(ctx):
    """
    Shows how long the bot has been online.
    Usage: !uptime
    """
    global BOT_START_TIME
    current_time = datetime.now(timezone.utc)
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
    if seconds > 0 or not uptime_string:
        uptime_string.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    final_uptime = ", ".join(uptime_string)

    embed = discord.Embed(
        title="Bot Uptime",
        description=f"I have been online for: `{final_uptime}`",
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

# --- General/Utility Commands ---
@bot.command(name="poll")
@commands.guild_only()
@commands.bot_has_permissions(send_messages=True, add_reactions=True, manage_messages=True, embed_links=True)
async def create_poll(ctx, question: str, *options: str):
    """
    Creates a reaction-based poll.
    Usage: !poll "Question" "Option 1" "Option 2" ...
    Max 10 options. Enclose each in quotes.
    """
    if len(options) < 2:
        await ctx.send("Please provide at least two options for the poll.")
        return
    if len(options) > 10:
        await ctx.send("You can provide a maximum of 10 options for the poll.")
        return

    # Using regional indicator emojis for options (🇦, 🇧, 🇨, etc.)
    # We need to ensure we have enough emojis for the options
    emoji_letters = [chr(0x1F1E6 + i) for i in range(len(options))] # A is 0x1F1E6

    description = f"**{question}**\n\n"
    for i, option in enumerate(options):
        description += f"{emoji_letters[i]} {option}\n"

    embed = discord.Embed(
        title="📊 New Poll! 📊",
        description=description,
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Poll by {ctx.author.display_name} | made by summers 2000")

    try:
        poll_message = await ctx.send(embed=embed)
        for emoji in emoji_letters:
            await poll_message.add_reaction(emoji)

        # Store poll data for tracking votes
        polls[poll_message.id] = {
            "channel_id": ctx.channel.id,
            "question": question,
            "options": list(options),
            "emojis": emoji_letters, # Store emojis used for this poll
            "votes": {emoji: [] for emoji in emoji_letters} # {emoji: [user_ids]}
        }
        save_polls()
        await check_achievement(ctx.author.id, "FIRST_POLL_CREATED", ctx)

    except discord.Forbidden:
        await ctx.send("I don't have permission to send messages or add reactions in this channel. Please check my permissions!")
    except Exception as e:
        print(f"ERROR: Error creating poll: {e}")
        await ctx.send("An unexpected error occurred while creating the poll.")

@bot.event
async def on_raw_reaction_add(payload):
    # Ignore bot's own reactions
    if payload.user_id == bot.user.id:
        return

    # Check if the reaction is on a tracked poll message
    if payload.message_id in polls:
        poll_info = polls[payload.message_id]
        channel = bot.get_channel(payload.channel_id)
        if not channel: return # Channel not found

        user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
        if not user: return # User not found

        # Ensure the emoji is one of the poll's valid options
        if str(payload.emoji) in poll_info["emojis"]:
            emoji = str(payload.emoji)
            if payload.user_id not in poll_info["votes"][emoji]:
                poll_info["votes"][emoji].append(payload.user_id)
                save_polls()

            # Remove other reactions by the same user to enforce single vote (optional)
            message = await channel.fetch_message(payload.message_id)
            for existing_reaction in message.reactions:
                if existing_reaction.emoji in poll_info["emojis"] and str(existing_reaction.emoji) != emoji:
                    if user in await existing_reaction.users().flatten():
                        try:
                            await message.remove_reaction(existing_reaction.emoji, user)
                            # Also remove from stored data if necessary
                            if payload.user_id in poll_info["votes"].get(str(existing_reaction.emoji), []):
                                poll_info["votes"][str(existing_reaction.emoji)].remove(payload.user_id)
                                save_polls()
                        except discord.HTTPException as e:
                            print(f"ERROR: Failed to remove reaction in poll: {e}")
        else:
            # If user reacted with an invalid emoji, remove it
            message = await channel.fetch_message(payload.message_id)
            try:
                await message.remove_reaction(payload.emoji, user)
            except discord.HTTPException as e:
                print(f"ERROR: Failed to remove invalid reaction from poll: {e}")
            
    # Handle reaction roles
    guild_id = payload.guild_id
    if guild_id and guild_id in reaction_roles:
        if payload.message_id in reaction_roles[guild_id]:
            emoji_to_role_map = reaction_roles[guild_id][payload.message_id]
            emoji_str = str(payload.emoji)

            if emoji_str in emoji_to_role_map:
                role_id = emoji_to_role_map[emoji_str]
                guild = bot.get_guild(guild_id)
                member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)

                if member:
                    role = guild.get_role(role_id)
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Reaction Role")
                            print(f"Assigned role {role.name} to {member.display_name} via reaction.")
                        except discord.Forbidden:
                            print(f"WARNING: Bot forbidden from assigning role {role.name} to {member.display_name}.")
                        except Exception as e:
                            print(f"ERROR: Error assigning reaction role: {e}")
                    elif role and role in member.roles:
                        # If user already has the role, allow them to remove it by reacting again (toggle behavior)
                        try:
                            await member.remove_roles(role, reason="Reaction Role (toggle off)")
                            print(f"Removed role {role.name} from {member.display_name} via reaction (toggle off).")
                            # Remove the user's reaction as well
                            message = await channel.fetch_message(payload.message_id)
                            await message.remove_reaction(payload.emoji, member)
                        except discord.Forbidden:
                            print(f"WARNING: Bot forbidden from removing role {role.name} from {member.display_name}.")
                        except Exception as e:
                            print(f"ERROR: Error removing reaction role (toggle): {e}")

    # Process other commands if this wasn't a reaction role or poll vote
    # This prevents the bot from ignoring command messages that happen to have reactions.
    # Note: message content is not available in on_raw_reaction_add, so we can't directly process commands.
    # The primary `on_message` handles command processing.
    pass

@bot.event
async def on_raw_reaction_remove(payload):
    # Only handle if reaction is on a tracked poll message
    if payload.message_id in polls:
        poll_info = polls[payload.message_id]
        
        if str(payload.emoji) in poll_info["emojis"]:
            emoji = str(payload.emoji)
            if payload.user_id in poll_info["votes"][emoji]:
                poll_info["votes"][emoji].remove(payload.user_id)
                save_polls()
    
    # Handle reaction roles removal (if needed)
    guild_id = payload.guild_id
    if guild_id and guild_id in reaction_roles:
        if payload.message_id in reaction_roles[guild_id]:
            emoji_to_role_map = reaction_roles[guild_id][payload.message_id]
            emoji_str = str(payload.emoji)

            if emoji_str in emoji_to_role_map:
                role_id = emoji_to_role_map[emoji_str]
                guild = bot.get_guild(guild_id)
                member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)

                if member:
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        try:
                            await member.remove_roles(role, reason="Reaction Role Removed")
                            print(f"Removed role {role.name} from {member.display_name} via reaction removal.")
                        except discord.Forbidden:
                            print(f"WARNING: Bot forbidden from removing role {role.name} from {member.display_name} on reaction remove.")
                        except Exception as e:
                            print(f"ERROR: Error removing reaction role: {e}")


@bot.command(name="serverinfo")
@commands.guild_only()
async def server_info(ctx):
    """
    Displays information about the current Discord server.
    Usage: !serverinfo
    """
    guild = ctx.guild

    embed = discord.Embed(
        title=f"Server Info: {guild.name}",
        description=guild.description if guild.description else "No description.",
        color=discord.Color.dark_orange(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    if guild.banner:
        embed.set_image(url=guild.banner.url)

    embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="Members", value=f"`{guild.member_count}`", inline=True)
    embed.add_field(name="Channels", value=f"`{len(guild.channels)}`", inline=True)
    embed.add_field(name="Roles", value=f"`{len(guild.roles)}`", inline=True)
    embed.add_field(name="Created On", value=f"<t:{int(guild.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="Boost Level", value=f"`{guild.premium_tier}` (Boosts: `{guild.premium_subscription_count}`)", inline=True)
    
    features = ", ".join(guild.features) if guild.features else "None"
    if len(features) > 1024: # Discord embed field value limit
        features = features[:1020] + "..."
    embed.add_field(name="Features", value=f"`{features}`", inline=False)

    await ctx.send(embed=embed)

@bot.command(name="userinfo")
@commands.guild_only()
async def user_info(ctx, member: discord.Member = None):
    """
    Displays detailed information about a mentioned user or yourself.
    Usage: !userinfo [@user]
    """
    if member is None:
        member = ctx.author

    embed = discord.Embed(
        title=f"User Info: {member.display_name}",
        color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(name="Username", value=f"`{member.name}`", inline=True)
    if member.discriminator != "0": # Check if the user has a discriminator (legacy username)
        embed.add_field(name="Discriminator", value=f"`#{member.discriminator}`", inline=True)
    embed.add_field(name="User ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:F>", inline=True)

    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    if roles:
        roles_str = ", ".join(roles)
        if len(roles_str) > 1024: # Discord embed field value limit
            roles_str = roles_str[:1020] + "..."
        embed.add_field(name=f"Roles ({len(roles)})", value=roles_str, inline=False)
    else:
        embed.add_field(name="Roles", value="No roles.", inline=False)

    await ctx.send(embed=embed)

@bot.command(name="ping")
async def ping_command(ctx):
    """
    Shows the bot's latency to Discord.
    Usage: !ping
    """
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: **`{latency_ms}`** ms",
        color=discord.Color.dark_green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="define")
async def define_command(ctx, *, word: str):
    """
    Get the definition of a word.
    Usage: !define <word>
    """
    # This example uses a simplified approach. A real-world bot would use a dictionary API.
    # For demonstration, I'll use a placeholder or a very small hardcoded dictionary.
    
    # Placeholder API for definition (replace with a real API if needed)
    # Example using a public API (e.g., Free Dictionary API) - requires aiohttp
    # API URL: "https://api.dictionaryapi.dev/api/v2/entries/en/<word>"
    
    api_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    response_data = await fetch_api_data(api_url)

    embed = discord.Embed(
        title=f"Definition of: `{word.capitalize()}`",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    if response_data and isinstance(response_data, list) and response_data[0].get('word'):
        # Assuming the first entry is the most relevant
        entry = response_data[0]
        meanings = entry.get('meanings', [])
        
        found_definition = False
        for meaning in meanings:
            part_of_speech = meaning.get('partOfSpeech')
            definitions = meaning.get('definitions', [])
            if definitions:
                definition_text = definitions[0].get('definition')
                if definition_text:
                    embed.add_field(
                        name=f"({part_of_speech.capitalize() if part_of_speech else 'N/A'})",
                        value=f"`{definition_text}`",
                        inline=False
                    )
                    found_definition = True
                    break # Just take the first definition for brevity

        if not found_definition:
            embed.description = "Could not find a definition for this word."
            embed.color = discord.Color.red()

    else:
        embed.description = "Could not find a definition for this word. The API might be down or the word doesn't exist."
        embed.color = discord.Color.red()
    
    await ctx.send(embed=embed)


@bot.command(name="remindme_list")
async def remindme_list_command(ctx):
    """
    List all active reminders for the user.
    Usage: !remindme_list
    """
    user_id = ctx.author.id
    user_reminders = [r for r in reminders if r['user_id'] == user_id]

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Active Reminders",
        color=discord.Color.teal(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    if not user_reminders:
        embed.description = "You have no active reminders set. Use `!remindme <time> <message>` to set one!"
    else:
        description_lines = []
        for i, r in enumerate(user_reminders):
            time_left = r['remind_time'] - datetime.now(timezone.utc)
            if time_left.total_seconds() <= 0:
                # Should have been caught by checker, but handle gracefully
                time_left_str = "Overdue!"
            else:
                total_seconds = int(time_left.total_seconds())
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                
                parts = []
                if days > 0: parts.append(f"{days}d")
                if hours > 0: parts.append(f"{hours}h")
                if minutes > 0: parts.append(f"{minutes}m")
                if seconds > 0 or not parts: parts.append(f"{seconds}s")
                time_left_str = " ".join(parts)

            description_lines.append(f"`{i+1}.` **`{r['message']}`** (in {time_left_str})")
        embed.description = "\n".join(description_lines)
    
    await ctx.send(embed=embed)

@bot.command(name="remindme_clear")
async def remindme_clear_command(ctx):
    """
    Clears all personal active reminders for the user.
    Usage: !remindme_clear
    """
    global reminders
    original_count = len([r for r in reminders if r['user_id'] == ctx.author.id])
    
    reminders = [r for r in reminders if r['user_id'] != ctx.author.id]
    save_reminders()

    if original_count > 0:
        await ctx.send(f"Successfully cleared `{original_count}` reminder(s) for {ctx.author.mention}.")
    else:
        await ctx.send(f"You have no active reminders to clear, {ctx.author.mention}.")

@bot.command(name="avatar")
async def avatar_command(ctx, member: discord.Member = None):
    """
    Display the avatar of a mentioned user or yourself.
    Usage: !avatar [@user]
    """
    if member is None:
        member = ctx.author

    embed = discord.Embed(
        title=f"{member.display_name}'s Avatar",
        color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
        url=member.display_avatar.url,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="channelinfo")
@commands.guild_only()
async def channel_info(ctx, channel: discord.TextChannel = None):
    """
    Displays details about the current channel or a specified channel.
    Usage: !channelinfo [#channel]
    """
    if channel is None:
        channel = ctx.channel

    embed = discord.Embed(
        title=f"Channel Info: #{channel.name}",
        color=discord.Color.dark_teal(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    embed.add_field(name="Name", value=f"`#{channel.name}`", inline=True)
    embed.add_field(name="ID", value=f"`{channel.id}`", inline=True)
    embed.add_field(name="Type", value=f"`{channel.type.name.replace('_', ' ').title()}`", inline=True)
    embed.add_field(name="Created On", value=f"<t:{int(channel.created_at.timestamp())}:F>", inline=True)
    embed.add_field(name="NSFW", value=f"`{'Yes' if channel.is_nsfw() else 'No'}`", inline=True)
    embed.add_field(name="Slowmode", value=f"`{channel.slowmode_delay}` seconds", inline=True)
    
    if channel.topic:
        topic = channel.topic
        if len(topic) > 1024:
            topic = topic[:1020] + "..."
        embed.add_field(name="Topic", value=f"`{topic}`", inline=False)
    else:
        embed.add_field(name="Topic", value="`No topic set.`", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="roleinfo")
@commands.guild_only()
async def role_info(ctx, *, role: discord.Role):
    """
    Shows information about a specific role.
    Usage: !roleinfo <role_name> (or mention the role)
    """
    embed = discord.Embed(
        title=f"Role Info: {role.name}",
        color=role.color if role.color != discord.Color.default() else discord.Color.light_grey(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    embed.add_field(name="Name", value=f"`{role.name}`", inline=True)
    embed.add_field(name="ID", value=f"`{role.id}`", inline=True)
    embed.add_field(name="Color (Hex)", value=f"`{str(role.color)}`", inline=True)
    embed.add_field(name="Members", value=f"`{len(role.members)}`", inline=True)
    embed.add_field(name="Mentionable", value=f"`{'Yes' if role.mentionable else 'No'}`", inline=True)
    embed.add_field(name="Hoisted (Displayed Separately)", value=f"`{'Yes' if role.hoist else 'No'}`", inline=True)
    embed.add_field(name="Created On", value=f"<t:{int(role.created_at.timestamp())}:F>", inline=False)
    
    # Permissions are complex, can list common ones or just status
    # For brevity, let's just indicate if it has admin
    if role.permissions.administrator:
        embed.add_field(name="Permissions", value="`Administrator`", inline=False)
    else:
        # You could list key permissions here if you want more detail
        embed.add_field(name="Key Permissions", value="`No Administrator, specific permissions listed here.`", inline=False) # Placeholder

    await ctx.send(embed=embed)


# --- Economy/Game Enhancements ---
@bot.command(name="profile")
async def profile_command(ctx, member: discord.Member = None):
    """
    Shows a summary of a user's economy, game stats, and achievements.
    Usage: !profile [@user]
    """
    if member is None:
        member = ctx.author

    user_id = member.id
    balance = user_balances.get(user_id, 0)
    inventory = user_inventories.get(user_id, {})
    game_stats_data = game_stats.get(user_id, {"c4_wins": 0, "c4_losses": 0, "c4_draws": 0, "ttt_wins": 0, "ttt_losses": 0, "ttt_draws": 0})
    user_achievements = achievements.get(user_id, [])
    daily_streak_data = daily_streaks.get(user_id, {"current_streak": 0, "last_claim_date": "N/A"})

    embed = discord.Embed(
        title=f"{member.display_name}'s Profile",
        color=member.color if member.color != discord.Color.default() else discord.Color.dark_purple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    embed.set_thumbnail(url=member.display_avatar.url)

    # Economy
    embed.add_field(name="__Economy__", value=(
        f"**Coins:** `{balance}`\n"
        f"**Daily Streak:** `{daily_streak_data['current_streak']}` days"
    ), inline=False)

    # Inventory
    if inventory:
        inventory_items = "\n".join([f"`{item}`: `{qty}`" for item, qty in inventory.items()])
        embed.add_field(name="__Inventory__", value=inventory_items, inline=False)
    else:
        embed.add_field(name="__Inventory__", value="`Empty`", inline=False)

    # Game Stats
    embed.add_field(name="__Game Statistics__", value=(
        f"**Connect4:** W:`{game_stats_data['c4_wins']}` L:`{game_stats_data['c4_losses']}` D:`{game_stats_data['c4_draws']}`\n"
        f"**Tic-Tac-Toe:** W:`{game_stats_data['ttt_wins']}` L:`{game_stats_data['ttt_losses']}` D:`{game_stats_data['ttt_draws']}`"
    ), inline=False)

    # Achievements
    if user_achievements:
        achievements_names = [ACHIEVEMENT_DEFINITIONS.get(ach_id, ach_id) for ach_id in user_achievements]
        # Limit to 5 achievements for brevity in profile, suggest using !myachievements for full list
        achievements_display = "\n".join([f"🏆 `{name}`" for name in achievements_names[:5]])
        if len(achievements_names) > 5:
            achievements_display += f"\n*...and {len(achievements_names) - 5} more. Use `!myachievements` to see all.*"
        embed.add_field(name="__Achievements__", value=achievements_display, inline=False)
    else:
        embed.add_field(name="__Achievements__", value="`None yet!`", inline=False)
    
    await ctx.send(embed=embed)


@bot.command(name="daily_streak")
async def daily_streak_command(ctx):
    """
    Displays your current daily claim streak.
    Usage: !daily_streak
    """
    user_id = ctx.author.id
    streak_data = daily_streaks.get(user_id, {"current_streak": 0, "last_claim_date": "N/A"})

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Daily Streak",
        description=f"Your current daily claim streak is: **`{streak_data['current_streak']}`** days!",
        color=discord.Color.dark_green(),
        timestamp=datetime.now(timezone.utc)
    )
    if streak_data["last_claim_date"] != "N/A":
        embed.add_field(name="Last Claimed", value=f"`{streak_data['last_claim_date']}` (UTC)", inline=False)
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

# Override daily_command to include streak logic
@bot.command(name="daily")
@commands.cooldown(1, DAILY_CLAIM_COOLDOWN, commands.BucketType.user)
async def daily_command_with_streak(ctx):
    user_id = ctx.author.id
    current_time = datetime.now(timezone.utc)
    today_date_str = current_time.strftime("%Y-%m-%d")
    
    last_claim_time = last_daily_claim.get(user_id)
    last_claim_date_str = daily_streaks.get(user_id, {}).get("last_claim_date")
    current_streak = daily_streaks.get(user_id, {}).get("current_streak", 0)

    # Check for cooldown
    if last_claim_time:
        time_since_last_claim = current_time - last_claim_time
        if time_since_last_claim.total_seconds() < DAILY_CLAIM_COOLDOWN:
            remaining_seconds = DAILY_CLAIM_COOLDOWN - time_since_last_claim.total_seconds()
            hours = int(remaining_seconds // 3600)
            minutes = int((remaining_seconds % 3600) // 60)
            seconds = int(remaining_seconds % 60)
            
            await ctx.send(f"You've already claimed your daily bonus! Please wait **{hours}h {minutes}m {seconds}s** before claiming again.")
            ctx.command.reset_cooldown(ctx)
            return

    daily_amount = random.randint(100, 200) # Give a random amount
    
    # Streak logic
    if last_claim_date_str:
        last_claim_date_obj = datetime.strptime(last_claim_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        # Check if yesterday
        if (current_time.date() - last_claim_date_obj.date()).days == 1:
            current_streak += 1
            streak_message = f"🔥 Your streak is now **`{current_streak}`** days!"
        elif (current_time.date() - last_claim_date_obj.date()).days > 1:
            current_streak = 1 # Streak broken
            streak_message = "😭 Your streak was broken! Starting a new streak of **`1`** day."
        else: # Claimed on the same day (should be caught by cooldown, but defensive)
            streak_message = f"Your streak remains **`{current_streak}`** days."
    else:
        current_streak = 1 # First claim ever
        streak_message = "🎉 You started a new daily streak of **`1`** day!"

    user_balances[user_id] = user_balances.get(user_id, 0) + daily_amount
    last_daily_claim[user_id] = current_time
    daily_streaks[user_id] = {"current_streak": current_streak, "last_claim_date": today_date_str}

    save_user_balances()
    save_last_daily_claim()
    save_daily_streaks()

    embed = discord.Embed(
        title="Daily Bonus Claimed!",
        description=f"You received **`{daily_amount}`** coins!\n{streak_message}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(user_id, "FIRST_DAILY_CLAIM", ctx)
    if current_streak >= 5: # Example achievement for streak
        await check_achievement(user_id, "FIRST_DAILY_STREAK_5", ctx)

@bot.command(name="blackjack")
async def blackjack_command(ctx, bet_amount: int):
    """
    Play a game of Blackjack against the bot.
    Usage: !blackjack <bet_amount>
    """
    if bet_amount <= 0:
        return await ctx.send("You must bet a positive amount of coins.")
    if user_balances.get(ctx.author.id, 0) < bet_amount:
        return await ctx.send(f"You don't have enough coins. You need `{bet_amount}` coins, but you only have `{user_balances.get(ctx.author.id, 0)}`.")

    deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4 # 2-10, J, Q, K (all 10), Ace (11)
    random.shuffle(deck)

    def deal_card():
        return deck.pop()

    def calculate_hand_value(hand):
        value = sum(hand)
        aces = hand.count(11)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    player_hand = [deal_card(), deal_card()]
    dealer_hand = [deal_card(), deal_card()]

    player_value = calculate_hand_value(player_hand)
    dealer_value = calculate_hand_value(dealer_hand) # For calculating purposes
    
    # Check for immediate Blackjack
    if player_value == 21:
        if dealer_value == 21:
            result = "draw"
        else:
            result = "player_blackjack"
    elif dealer_value == 21:
        result = "dealer_blackjack"
    else:
        result = "ongoing"

    game_embed = discord.Embed(
        title="♣️♠️ Blackjack! ♥️♦️",
        color=discord.Color.dark_blue(),
        timestamp=datetime.now(timezone.utc)
    )
    game_embed.set_footer(text="made by summers 2000")

    def update_embed_fields(embed, player_hand, dealer_hand, show_dealer_full=False):
        embed.clear_fields()
        embed.add_field(name=f"{ctx.author.display_name}'s Hand", value=f"Cards: `{player_hand}` (Value: `{calculate_hand_value(player_hand)}`)", inline=False)
        if show_dealer_full:
            embed.add_field(name="Bot's Hand", value=f"Cards: `{dealer_hand}` (Value: `{calculate_hand_value(dealer_hand)}`)", inline=False)
        else:
            embed.add_field(name="Bot's Hand", value=f"Cards: `{dealer_hand[0]}, [Hidden Card]`", inline=False)

    update_embed_fields(game_embed, player_hand, dealer_hand, show_dealer_full=False)

    if result == "player_blackjack":
        game_embed.add_field(name="Result", value="🎉 Blackjack! You win!", inline=False)
        user_balances[ctx.author.id] += bet_amount
        game_embed.color = discord.Color.green()
        update_embed_fields(game_embed, player_hand, dealer_hand, show_dealer_full=True)
        await ctx.send(embed=game_embed)
        save_user_balances()
        await check_achievement(ctx.author.id, "FIRST_BLACKJACK_WIN", ctx)
        return
    elif result == "dealer_blackjack":
        game_embed.add_field(name="Result", value="💔 Bot has Blackjack! You lose.", inline=False)
        user_balances[ctx.author.id] -= bet_amount
        game_embed.color = discord.Color.red()
        update_embed_fields(game_embed, player_hand, dealer_hand, show_dealer_full=True)
        await ctx.send(embed=game_embed)
        save_user_balances()
        return
    elif result == "draw":
        game_embed.add_field(name="Result", value="It's a push! Both have Blackjack.", inline=False)
        game_embed.color = discord.Color.light_grey()
        update_embed_fields(game_embed, player_hand, dealer_hand, show_dealer_full=True)
        await ctx.send(embed=game_embed)
        save_user_balances() # No change to balance, but saves state if other changes pending
        return
    
    # Game is ongoing
    hit_button = discord.ui.Button(label="Hit", style=discord.ButtonStyle.green)
    stand_button = discord.ui.Button(label="Stand", style=discord.ButtonStyle.red)

    async def hit_callback(interaction: discord.Interaction):
        if interaction.user != ctx.author:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        
        player_hand.append(deal_card())
        new_player_value = calculate_hand_value(player_hand)
        
        update_embed_fields(game_embed, player_hand, dealer_hand, show_dealer_full=False)

        if new_player_value > 21:
            game_embed.add_field(name="Result", value="BUST! You went over 21. You lose.", inline=False)
            game_embed.color = discord.Color.red()
            user_balances[ctx.author.id] -= bet_amount
            save_user_balances()
            for child in view.children: child.disabled = True
            await interaction.response.edit_message(embed=game_embed, view=view)
            return

        await interaction.response.edit_message(embed=game_embed, view=view)

    async def stand_callback(interaction: discord.Interaction):
        if interaction.user != ctx.author:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        
        # Dealer's turn
        while calculate_hand_value(dealer_hand) < 17:
            dealer_hand.append(deal_card())
        
        final_player_value = calculate_hand_value(player_hand)
        final_dealer_value = calculate_hand_value(dealer_hand)

        result_message = ""
        final_color = discord.Color.blue() # Default

        if final_dealer_value > 21:
            result_message = "Bot BUSTS! You win!"
            user_balances[ctx.author.id] += bet_amount
            final_color = discord.Color.green()
            await check_achievement(ctx.author.id, "FIRST_BLACKJACK_WIN", ctx)
        elif final_player_value > final_dealer_value:
            result_message = "You win!"
            user_balances[ctx.author.id] += bet_amount
            final_color = discord.Color.green()
            await check_achievement(ctx.author.id, "FIRST_BLACKJACK_WIN", ctx)
        elif final_dealer_value > final_player_value:
            result_message = "You lose."
            user_balances[ctx.author.id] -= bet_amount
            final_color = discord.Color.red()
        else:
            result_message = "It's a push (draw)!"
            final_color = discord.Color.light_grey()
        
        game_embed.add_field(name="Result", value=result_message, inline=False)
        game_embed.color = final_color
        update_embed_fields(game_embed, player_hand, dealer_hand, show_dealer_full=True)
        user_balances[ctx.author.id] = user_balances.get(ctx.author.id, 0) # Ensure it's inited if not changed
        game_embed.add_field(name="Your New Balance", value=f"`{user_balances[ctx.author.id]}` coins", inline=False)
        
        save_user_balances()
        for child in view.children: child.disabled = True
        await interaction.response.edit_message(embed=game_embed, view=view)

    view = discord.ui.View(timeout=60) # 60 seconds to play
    hit_button.callback = hit_callback
    stand_button.callback = stand_callback
    view.add_item(hit_button)
    view.add_item(stand_button)

    message_sent = await ctx.send(embed=game_embed, view=view)
    
    async def on_timeout():
        for child in view.children: child.disabled = True
        await message_sent.edit(content="Game timed out. You lose the bet.", view=view, embed=game_embed)
        user_balances[ctx.author.id] -= bet_amount # Player loses bet on timeout
        save_user_balances()
        game_embed.add_field(name="Your New Balance", value=f"`{user_balances[ctx.author.id]}` coins", inline=False)
        await message_sent.edit(embed=game_embed)
    view.on_timeout = on_timeout

@bot.command(name="slots")
async def slots_command(ctx, bet_amount: int):
    """
    Play a game of Slots.
    Usage: !slots <bet_amount>
    """
    if bet_amount <= 0:
        return await ctx.send("You must bet a positive amount of coins.")
    if user_balances.get(ctx.author.id, 0) < bet_amount:
        return await ctx.send(f"You don't have enough coins. You need `{bet_amount}` coins, but you only have `{user_balances.get(ctx.author.id, 0)}`.")

    # Slot machine symbols and their multipliers
    symbols = ["🍒", "🍋", "🔔", "⭐", "💎", "💰"]
    payouts = {
        ("🍒", "🍒", "🍒"): 3,
        ("🍋", "🍋", "🍋"): 5,
        ("🔔", "🔔", "🔔"): 7,
        ("⭐", "⭐", "⭐"): 10,
        ("💎", "💎", "💎"): 20,
        ("💰", "💰", "💰"): 50,
        # Two matching symbols (e.g., two cherries) - smaller payout
        ("🍒", "🍒"): 1.5,
        ("🍋", "🍋"): 2,
    }

    # Simulate the reels
    reel1 = random.choice(symbols)
    reel2 = random.choice(symbols)
    reel3 = random.choice(symbols)
    
    result_reels = (reel1, reel2, reel3)
    
    winnings = 0
    outcome_message = "You lost! Better luck next time."
    color = discord.Color.red()
    
    # Check for wins
    if reel1 == reel2 == reel3:
        # Perfect match (3 of a kind)
        multiplier = payouts.get(result_reels, 0) # Get specific payout for 3 of a kind
        winnings = bet_amount * multiplier
        outcome_message = f"🎉 Jackpot! 3x {reel1}! You won `{winnings}` coins!"
        color = discord.Color.gold()
        await check_achievement(ctx.author.id, "FIRST_SLOTS_WIN", ctx)
    elif reel1 == reel2:
        multiplier = payouts.get((reel1, reel2), 0) # Check for 2 of a kind
        winnings = bet_amount * multiplier
        if winnings > 0:
            outcome_message = f"Nice! 2x {reel1}! You won `{winnings}` coins!"
            color = discord.Color.green()
    elif reel2 == reel3:
        multiplier = payouts.get((reel2, reel3), 0)
        winnings = bet_amount * multiplier
        if winnings > 0:
            outcome_message = f"Nice! 2x {reel2}! You won `{winnings}` coins!"
            color = discord.Color.green()
    elif reel1 == reel3 and reel1 != reel2: # Edge case: reel1 and reel3 match but not middle
         multiplier = payouts.get((reel1, reel3), 0) # Can add specific payout for this
         winnings = bet_amount * multiplier
         if winnings > 0:
             outcome_message = f"Nice! 2x {reel1}! You won `{winnings}` coins!"
             color = discord.Color.green()


    if winnings > 0:
        user_balances[ctx.author.id] = user_balances.get(ctx.author.id, 0) + winnings
    else:
        user_balances[ctx.author.id] = user_balances.get(ctx.author.id, 0) - bet_amount

    save_user_balances()

    embed = discord.Embed(
        title="🎰 Slot Machine 🎰",
        description=f"You bet: `{bet_amount}` coins\n\n"
                    f"**[ {reel1} | {reel2} | {reel3} ]**\n\n"
                    f"{outcome_message}",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Your New Balance", value=f"`{user_balances.get(ctx.author.id, 0)}` coins", inline=False)
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)


# --- Fun/Interactive Commands ---
@bot.command(name="8ball")
async def eightball_command(ctx, *, question: str):
    """
    A classic magic 8-ball that provides a random answer to a yes/no question.
    Usage: !8ball <question>
    """
    responses = [
        "It is certain.",
        "It is decidedly so.",
        "Without a doubt.",
        "Yes, definitely.",
        "You may rely on it.",
        "As I see it, yes.",
        "Most likely.",
        "Outlook good.",
        "Yes.",
        "Signs point to yes.",
        "Reply hazy, try again.",
        "Ask again later.",
        "Better not tell you now.",
        "Cannot predict now.",
        "Concentrate and ask again.",
        "Don't count on it.",
        "My reply is no.",
        "My sources say no.",
        "Outlook not so good.",
        "Very doubtful."
    ]
    answer = random.choice(responses)
    
    embed = discord.Embed(
        title="🎱 Magic 8-Ball 🎱",
        description=f"**Question:** `{question}`\n\n**Answer:** `{answer}`",
        color=discord.Color.dark_grey(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="fact")
async def fact_command(ctx):
    """
    Fetches a random interesting fact.
    Usage: !fact
    """
    # For a real bot, you'd integrate with an API that provides random facts.
    # For this example, I'll use a small hardcoded list.
    facts = [
        "A group of owls is called a parliament.",
        "Honey never spoils.",
        "The shortest war in history lasted only 38 to 45 minutes.",
        "Octopuses have three hearts.",
        "A jiffy is an actual unit of time: 1/100th of a second.",
        "The human nose can remember 50,000 different scents.",
        "Bananas are berries, but strawberries aren't."
    ]
    fact = random.choice(facts)
    
    embed = discord.Embed(
        title="🧠 Random Fact! 🧠",
        description=f"`{fact}`",
        color=discord.Color.light_grey(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="joke")
async def joke_command(ctx):
    """
    Fetches a random joke.
    Usage: !joke
    """
    # Similar to !fact, for a real bot, you'd use a joke API.
    jokes = [
        "Why don't scientists trust atoms? Because they make up everything!",
        "What do you call a fish with no eyes? Fsh!",
        "Did you hear about the restaurant on the moon? Great food, no atmosphere.",
        "Why did the scarecrow win an award? Because he was outstanding in his field!",
        "I'm reading a book about anti-gravity. It's impossible to put down!",
        "What's orange and sounds like a parrot? A carrot!"
    ]
    joke = random.choice(jokes)
    
    embed = discord.Embed(
        title="😂 Have a laugh! 😂",
        description=f"`{joke}`",
        color=discord.Color.magenta(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)

@bot.command(name="ship")
async def ship_command(ctx, user1: discord.Member, user2: discord.Member):
    """
    Calculate and display a "compatibility score" between two users.
    Usage: !ship <@user1> <@user2>
    """
    if user1.id == user2.id:
        return await ctx.send("You can't ship someone with themselves!")
    
    # Simple hash-based "compatibility" for consistent results for the same pair
    # Order of users shouldn't matter for the score
    user_ids = sorted([user1.id, user2.id])
    seed = sum(user_ids) # Simple numeric sum as seed
    random.seed(seed)
    
    compatibility_score = random.randint(0, 100)
    
    love_messages = {
        range(0, 21): "Not quite a match made in heaven...",
        range(21, 41): "A challenging pairing, but anything is possible!",
        range(41, 61): "There's potential, with some effort and understanding.",
        range(61, 81): "A harmonious duo, with a good foundation!",
        range(81, 96): "A truly strong connection!",
        range(96, 101): "💖 Perfect match! Soulmates detected! 💖"
    }

    message = ""
    for score_range, msg in love_messages.items():
        if compatibility_score in score_range:
            message = msg
            break
            
    embed = discord.Embed(
        title="💘 Shipometer! 💘",
        description=f"Calculating the compatibility between {user1.mention} and {user2.mention}...",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Compatibility Score", value=f"**`{compatibility_score}%`**", inline=False)
    embed.add_field(name="Verdict", value=message, inline=False)
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(ctx.author.id, "FIRST_SHIP", ctx)

@bot.command(name="quote_add")
async def quote_add_command(ctx, quote_text: str, author: str = "Anonymous"):
    """
    Allows users to add their favorite quotes to a collection.
    Usage: !quote_add "Quote Text" - [Author]
    If author is not provided, defaults to "Anonymous".
    """
    if len(quote_text) > 500:
        await ctx.send("Quote text is too long (max 500 characters).")
        return
    if len(author) > 100:
        await ctx.send("Author name is too long (max 100 characters).")
        return

    quotes.append({"text": quote_text, "author": author})
    save_quotes()

    embed = discord.Embed(
        title="Quote Added!",
        description=f"Successfully added:\n\n\"`{quote_text}`\" - `{author}`",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(ctx.author.id, "FIRST_QUOTE_ADDED", ctx)


@bot.command(name="quote_random")
async def quote_random_command(ctx):
    """
    Fetches a random quote from the collected quotes.
    Usage: !quote_random
    """
    if not quotes:
        await ctx.send("No quotes have been added yet! Use `!quote_add` to add one.")
        return

    random_quote = random.choice(quotes)

    embed = discord.Embed(
        title="📚 Random Quote 📚",
        description=f"\"`{random_quote['text']}`\"\n\n- `{random_quote['author']}`",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)


# --- Moderation Enhancements ---

@bot.command(name="warn")
@commands.has_permissions(kick_members=True) # Usually kick/ban permissions are sufficient for warning
@commands.bot_has_permissions(send_messages=True, embed_links=True)
async def warn_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Issues a warning to a user.
    Usage: !warn <@user> [reason]
    """
    if member.bot:
        return await ctx.send("You cannot warn a bot.")
    if member == ctx.author:
        return await ctx.send("You cannot warn yourself.")
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("You cannot warn someone with an equal or higher role than yourself.")

    guild_id = ctx.guild.id
    user_id = member.id

    if guild_id not in warnings:
        warnings[guild_id] = {}
    if user_id not in warnings[guild_id]:
        warnings[guild_id][user_id] = []

    warning_id = str(len(warnings[guild_id][user_id]) + 1) # Simple sequential ID
    warnings[guild_id][user_id].append({
        "id": warning_id,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc),
        "moderator_id": ctx.author.id
    })
    save_warnings()

    embed = discord.Embed(
        title="User Warned",
        description=f"**{member.display_name}** has been warned for: `{reason}`",
        color=discord.Color.yellow(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Warning ID", value=f"`{warning_id}`", inline=True)
    embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await check_achievement(ctx.author.id, "FIRST_WARNING", ctx)
    await send_mod_log(ctx.guild, "User Warned", f"{member.mention} warned by {ctx.author.mention} for: `{reason}` (ID: `{warning_id}`)", discord.Color.yellow(), ctx.author, member)


@bot.command(name="warnings")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(send_messages=True, embed_links=True)
async def list_warnings(ctx, member: discord.Member = None):
    """
    Displays a list of warnings for a user.
    Usage: !warnings [@user]
    """
    if member is None:
        member = ctx.author

    guild_id = ctx.guild.id
    user_id = member.id

    user_warnings = warnings.get(guild_id, {}).get(user_id, [])

    embed = discord.Embed(
        title=f"Warnings for {member.display_name}",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    if not user_warnings:
        embed.description = f"No warnings found for **{member.display_name}**."
    else:
        for warn_entry in user_warnings:
            mod = ctx.guild.get_member(warn_entry["moderator_id"])
            mod_name = mod.display_name if mod else f"Unknown User (ID: {warn_entry['moderator_id']})"
            
            embed.add_field(
                name=f"Warning ID: `{warn_entry['id']}`",
                value=(
                    f"**Reason:** `{warn_entry['reason']}`\n"
                    f"**Moderator:** {mod_name}\n"
                    f"**Date:** <t:{int(warn_entry['timestamp'].timestamp())}:F>"
                ),
                inline=False
            )
    await ctx.send(embed=embed)

@bot.command(name="warn_remove")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(send_messages=True, embed_links=True)
async def warn_remove_command(ctx, member: discord.Member, warning_id: str):
    """
    Removes a specific warning from a user's record.
    Usage: !warn_remove <@user> <warning_id>
    """
    guild_id = ctx.guild.id
    user_id = member.id

    if guild_id not in warnings or user_id not in warnings[guild_id]:
        return await ctx.send(f"No warnings found for {member.display_name}.")

    user_warnings = warnings[guild_id][user_id]
    
    # Find and remove the warning by ID
    warning_found = False
    new_warnings_list = []
    removed_reason = "N/A"

    for warn in user_warnings:
        if warn["id"] == warning_id:
            warning_found = True
            removed_reason = warn["reason"]
        else:
            new_warnings_list.append(warn)
    
    if not warning_found:
        return await ctx.send(f"Warning with ID `{warning_id}` not found for {member.display_name}.")

    warnings[guild_id][user_id] = new_warnings_list
    if not warnings[guild_id][user_id]: # Remove user entry if no warnings left
        del warnings[guild_id][user_id]
    if not warnings[guild_id]: # Remove guild entry if no users with warnings left
        del warnings[guild_id]

    save_warnings()

    embed = discord.Embed(
        title="Warning Removed",
        description=f"Successfully removed warning ID **`{warning_id}`** for **{member.display_name}** (`{removed_reason}`).",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await send_mod_log(ctx.guild, "Warning Removed", f"Warning `{warning_id}` removed for {member.mention} by {ctx.author.mention}", discord.Color.green(), ctx.author, member)


@bot.command(name="lockdown")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def lockdown_channel(ctx, *, reason: str = "No reason provided"):
    """
    Locks down the current channel, preventing @everyone from sending messages.
    Usage: !lockdown [reason]
    """
    # Get the @everyone role
    everyone_role = ctx.guild.default_role
    
    # Check current permissions
    if channel_overwrite := everyone_role.overwrites_for(ctx.channel):
        if channel_overwrite.send_messages is False:
            return await ctx.send("This channel is already locked down.")

    try:
        await ctx.channel.set_permissions(everyone_role, send_messages=False, reason=reason)
        embed = discord.Embed(
            title="Channel Locked Down",
            description=f"This channel has been locked down. No one can send messages here.\nReason: `{reason}`",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, "Channel Lockdown", f"Channel {ctx.channel.mention} locked down by {ctx.author.mention} for: `{reason}`", discord.Color.red(), ctx.author, ctx.channel)
    except discord.Forbidden:
        await ctx.send("I don't have permission to modify channel permissions. Please ensure my role is higher than the `@everyone` role.")
    except Exception as e:
        await ctx.send(f"An error occurred while locking down the channel: `{e}`")


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unlock_channel(ctx, *, reason: str = "No reason provided"):
    """
    Unlocks a previously locked channel, allowing @everyone to send messages.
    Usage: !unlock [reason]
    """
    everyone_role = ctx.guild.default_role
    
    # Check current permissions
    if channel_overwrite := everyone_role.overwrites_for(ctx.channel):
        if channel_overwrite.send_messages is None or channel_overwrite.send_messages is True:
            return await ctx.send("This channel is not currently locked down by me.")

    try:
        # Pass None to reset the permission, allowing it to inherit from category/guild
        await ctx.channel.set_permissions(everyone_role, send_messages=None, reason=reason)
        embed = discord.Embed(
            title="Channel Unlocked",
            description=f"This channel has been unlocked. Messages can now be sent.\nReason: `{reason}`",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, "Channel Unlocked", f"Channel {ctx.channel.mention} unlocked by {ctx.author.mention} for: `{reason}`", discord.Color.green(), ctx.author, ctx.channel)
    except discord.Forbidden:
        await ctx.send("I don't have permission to modify channel permissions.")
    except Exception as e:
        await ctx.send(f"An error occurred while unlocking the channel: `{e}`")

@bot.command(name="softban")
@commands.has_permissions(kick_members=True) # Softban is a kick + delete messages
@commands.bot_has_permissions(kick_members=True, manage_messages=True)
async def softban_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Kicks a user and removes their messages, but doesn't add them to the ban list (they can rejoin).
    Usage: !softban <@user> [reason]
    """
    if member == ctx.author:
        return await ctx.send("You cannot softban yourself.")
    if member == bot.user:
        return await ctx.send("I cannot softban myself.")
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("You cannot softban someone with an equal or higher role than yourself.")
    if ctx.guild.me.top_role <= member.top_role:
        return await ctx.send("I cannot softban this user as their role is equal to or higher than my top role.")

    try:
        # Ban for 1 day to clear messages, then immediately unban
        await member.ban(reason=f"Softban by {ctx.author.name}: {reason}", delete_message_days=1)
        await asyncio.sleep(1) # Give a moment for the ban to register before unban
        await ctx.guild.unban(member, reason=f"Softban unban by {ctx.author.name}")

        embed = discord.Embed(
            title="User Softbanned",
            description=f"**{member.display_name}** has been softbanned (kicked and messages cleared) for: `{reason}`.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, "User Softbanned", f"{member.mention} softbanned by {ctx.author.mention} for: `{reason}`", discord.Color.orange(), ctx.author, member)
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions for softban. Make sure I have 'Ban Members' and 'Manage Messages'.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred during softban for {member.display_name}: `{e}`")


@bot.command(name="nick")
@commands.has_permissions(manage_nicknames=True)
@commands.bot_has_permissions(manage_nicknames=True)
async def nick_command(ctx, member: discord.Member, *, new_nickname: str = None):
    """
    Changes a user's nickname. If no nickname is provided, it resets their nickname.
    Usage: !nick <@user> [new_nickname]
    """
    if member == bot.user:
        return await ctx.send("I cannot change my own nickname using this command.")
    if member == ctx.author and new_nickname:
        if ctx.author.top_role >= ctx.guild.me.top_role:
            return await ctx.send("I cannot change your nickname if your highest role is above or equal to mine.")
    if ctx.guild.me.top_role <= member.top_role:
        return await ctx.send("I cannot change the nickname of a user whose top role is equal to or higher than mine.")

    try:
        old_nick = member.nick
        await member.edit(nick=new_nickname, reason=f"Nickname changed by {ctx.author.name}")
        
        embed = discord.Embed(
            title="Nickname Updated",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")

        if new_nickname:
            embed.description = f"**{member.display_name}**'s nickname changed to **`{new_nickname}`**."
            embed.add_field(name="Old Nickname", value=f"`{old_nick if old_nick else 'None'}`", inline=True)
            embed.add_field(name="New Nickname", value=f"`{new_nickname}`", inline=True)
        else:
            embed.description = f"**{member.display_name}**'s nickname has been **reset**."
            embed.add_field(name="Old Nickname", value=f"`{old_nick if old_nick else 'None'}`", inline=True)
            embed.add_field(name="New Nickname", value="`None` (reset)", inline=True)
        
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, "Nickname Changed", f"{member.mention} nickname changed by {ctx.author.mention}", discord.Color.blue(), ctx.author, member)

    except discord.Forbidden:
        await ctx.send("I don't have permission to change nicknames. Ensure my role has 'Manage Nicknames' and is higher than the target user's role.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while changing nickname: `{e}`")


@bot.command(name="voicekick")
@commands.has_permissions(move_members=True)
@commands.bot_has_permissions(move_members=True)
async def voicekick_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Disconnects a user from their current voice channel.
    Usage: !voicekick <@user> [reason]
    """
    if not member.voice or not member.voice.channel:
        return await ctx.send(f"**{member.display_name}** is not in a voice channel.")
    if member == ctx.author:
        return await ctx.send("You cannot voicekick yourself.")
    if member == bot.user:
        return await ctx.send("I cannot voicekick myself.")
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("You cannot voicekick someone with an equal or higher role than yourself.")
    if ctx.guild.me.top_role <= member.top_role:
        return await ctx.send("I cannot voicekick this user as their role is equal to or higher than my top role.")

    try:
        old_channel_name = member.voice.channel.name
        await member.move_to(None, reason=reason) # Move to None disconnects them

        embed = discord.Embed(
            title="Voice Channel Kicked",
            description=f"**{member.display_name}** has been disconnected from voice channel **`#{old_channel_name}`**.\nReason: `{reason}`",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, "Voice Kicked", f"{member.mention} voice-kicked by {ctx.author.mention} from `#{old_channel_name}` for: `{reason}`", discord.Color.red(), ctx.author, member)
    except discord.Forbidden:
        await ctx.send("I don't have permission to move members. Please ensure my role has 'Move Members' and is higher than the target user's role.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while voicekicking {member.display_name}: `{e}`")

@bot.command(name="tempmute")
@commands.has_permissions(manage_roles=True)
@commands.bot_has_permissions(manage_roles=True)
async def tempmute_command(ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
    """
    Mutes a user for a specified duration (e.g., 30m, 1h, 2d).
    Usage: !tempmute <@user> <duration> [reason]
    Duration examples: 30s, 5m, 1h, 2d (seconds, minutes, hours, days)
    """
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        await ctx.send("**Error:** The 'Muted' role was not found. Please create a role named `Muted` with no permissions and try again.")
        return

    if muted_role in member.roles:
        return await ctx.send(f"**{member.display_name}** is already muted.")

    if member == ctx.author or member == bot.user:
        return await ctx.send("You cannot mute yourself or the bot.")
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("You cannot mute someone with an equal or higher role than yourself.")
    if ctx.guild.me.top_role <= member.top_role:
        return await ctx.send("I cannot mute this user as their role is equal to or higher than my top role.")

    # Time parsing logic
    time_unit_map = {
        's': 1,      # seconds
        'm': 60,     # minutes
        'h': 3600,   # hours
        'd': 86400   # days
    }
    match = re.fullmatch(r'(\d+)([smhd])', duration.lower())
    if not match:
        return await ctx.send("Invalid duration format. Use a number followed by s, m, h, or d (e.g., `30m`, `1h`).")

    amount = int(match.group(1))
    unit = match.group(2)
    delay_seconds = amount * time_unit_map[unit]

    if delay_seconds <= 0:
        return await ctx.send("Mute duration must be positive.")
    
    # Discord mute max duration is 28 days for timeouts, but for role-based mute, there's no inherent API limit.
    # We can set a reasonable limit here for bot's management.
    if delay_seconds > (28 * 86400): # Max 28 days
        return await ctx.send("Mute duration cannot exceed 28 days.")

    try:
        await member.add_roles(muted_role, reason=f"Tempmute by {ctx.author.name}: {reason} for {duration}")
        
        embed = discord.Embed(
            title="Member Temporarily Muted",
            description=f"**{member.display_name}** has been muted for **`{duration}`**.\nReason: `{reason}`",
            color=discord.Color.light_grey(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, "User Temp Muted", f"{member.mention} temp muted by {ctx.author.mention} for `{duration}`: `{reason}`", discord.Color.light_grey(), ctx.author, member)

        await asyncio.sleep(delay_seconds)

        # Check if user is still muted by the role before unmuting
        if muted_role in member.roles:
            try:
                await member.remove_roles(muted_role, reason="Tempmute duration expired")
                unmute_embed = discord.Embed(
                    title="Member Unmuted (Automatic)",
                    description=f"Unmuted **{member.display_name}** (tempmute duration expired).",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                unmute_embed.set_footer(text="made by summers 2000")
                await ctx.send(embed=unmute_embed)
                await send_mod_log(ctx.guild, "User Unmuted", f"{member.mention} automatically unmuted after `{duration}`", discord.Color.blue(), bot.user, member)
            except discord.Forbidden:
                print(f"WARNING: Bot unable to auto-unmute {member.display_name} due to insufficient permissions.")
            except Exception as ex:
                print(f"ERROR: An error occurred during auto-unmute for {member.display_name}: {ex}")
        else:
            print(f"{member.display_name} was manually unmuted before tempmute duration expired.")

    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to manage roles. Make sure my role is higher than the 'Muted' role and the user's role.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to tempmute {member.display_name}: `{e}`")

@bot.command(name="reactionrole")
@commands.has_permissions(manage_roles=True, manage_messages=True)
@commands.bot_has_permissions(manage_roles=True, add_reactions=True, read_message_history=True)
@commands.guild_only()
async def reaction_role_setup(ctx, message_id: int, emoji: str, role: discord.Role):
    """
    Sets up a reaction role on a specific message.
    When a user reacts with the specified emoji, they get the designated role.
    Usage: !reactionrole <message_id> <emoji> <@role>
    """
    try:
        target_message = await ctx.channel.fetch_message(message_id)
    except discord.NotFound:
        return await ctx.send(f"Message with ID `{message_id}` not found in this channel.")
    except discord.Forbidden:
        return await ctx.send("I don't have permission to read message history in this channel.")
    except Exception as e:
        return await ctx.send(f"An error occurred while fetching the message: `{e}`")

    # Add the reaction to the message so users know what to react with
    try:
        await target_message.add_reaction(emoji)
    except discord.HTTPException:
        return await ctx.send(f"Failed to add reaction `{emoji}` to the message. Please ensure it's a valid emoji.")
    except Exception as e:
        return await ctx.send(f"An unexpected error occurred while adding reaction: `{e}`")

    guild_id = ctx.guild.id
    if guild_id not in reaction_roles:
        reaction_roles[guild_id] = {}
    if message_id not in reaction_roles[guild_id]:
        reaction_roles[guild_id][message_id] = {}
    
    reaction_roles[guild_id][message_id][emoji] = role.id
    save_reaction_roles()

    embed = discord.Embed(
        title="Reaction Role Setup!",
        description=f"Reaction role set up successfully:\n"
                    f"**Message:** [Link to Message]({target_message.jump_url})\n"
                    f"**Emoji:** {emoji}\n"
                    f"**Role:** {role.mention}",
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await send_mod_log(ctx.guild, "Reaction Role Created", f"Reaction role set up by {ctx.author.mention} on message `{message_id}` for emoji `{emoji}` and role `{role.name}`.", discord.Color.purple(), ctx.author, target_message)

# --- Anti-Nuke System ---

def is_whitelisted(user_id, member_roles):
    """Checks if a user is whitelisted from anti-nuke actions."""
    if user_id == bot.user.id or user_id in MOD_WHITELIST_USERS:
        return True
    for role_id in MOD_WHITELIST_ROLES:
        if any(r.id == role_id for r in member_roles):
            return True
    return False

async def log_anti_nuke_event(guild, action_type, actor, target_info, details, countermeasure_taken):
    """Logs an anti-nuke event and sends it to the mod log channel."""
    timestamp = datetime.now(timezone.utc)
    log_entry = {
        "timestamp": timestamp,
        "guild_id": guild.id,
        "action_type": action_type,
        "actor_id": actor.id if actor else None,
        "actor_name": actor.display_name if actor else "Unknown",
        "target_info": target_info,
        "details": details,
        "countermeasure_taken": countermeasure_taken
    }
    ANTI_NUKE_LOGS.append(log_entry)
    # Keep last 50 logs
    if len(ANTI_NUKE_LOGS) > 50:
        ANTI_NUKE_LOGS.pop(0)
    save_anti_nuke_logs()

    # Also send to general mod log channel if configured
    title = f"🚨 Anti-Nuke Alert: {action_type.replace('_', ' ').title()} 🚨"
    description = (
        f"**Actor:** {actor.mention if actor else 'Unknown User'} (`{actor.id if actor else 'N/A'}`)\n"
        f"**Target:** {target_info}\n"
        f"**Details:** {details}\n"
        f"**Countermeasure:** {countermeasure_taken}"
    )
    await send_mod_log(guild, title, description, discord.Color.dark_red(), actor, target_info)

async def check_nuke_activity(guild, user, activity_type, target_info):
    """Checks if a user's activity triggers a nuke threshold."""
    if not ANTI_NUKE_ENABLED:
        return

    if is_whitelisted(user.id, user.roles if isinstance(user, discord.Member) else []):
        return # Whitelisted users bypass checks

    threshold = NUKE_THRESHOLDS.get(activity_type)
    if not threshold:
        return # No threshold defined for this activity type

    guild_id = guild.id
    user_id = user.id

    SUSPICIOUS_ACTIVITY.setdefault(guild_id, {}).setdefault(user_id, {}).setdefault(activity_type, [])
    
    # Add current timestamp to the activity list
    SUSPICIOUS_ACTIVITY[guild_id][user_id][activity_type].append(datetime.now(timezone.utc))

    # Clean up old activities
    time_limit = datetime.now(timezone.utc) - timedelta(seconds=threshold["time_period"])
    SUSPICIOUS_ACTIVITY[guild_id][user_id][activity_type] = [
        t for t in SUSPICIOUS_ACTIVITY[guild_id][user_id][activity_type] if t >= time_limit
    ]

    # Check if threshold is met
    if len(SUSPICIOUS_ACTIVITY[guild_id][user_id][activity_type]) >= threshold["count"]:
        # Threshold met! Trigger countermeasures.
        countermeasure = "No action (Safe Mode Active)" if SAFE_MODE_ENABLED else "Revoked permissions and alerted mods."
        
        await log_anti_nuke_event(
            guild, activity_type, user, target_info,
            f"Threshold met: {len(SUSPICIOUS_ACTIVITY[guild_id][user_id][activity_type])} {activity_type.replace('_', ' ')}s in {threshold['time_period']}s.",
            countermeasure
        )

        if not SAFE_MODE_ENABLED:
            # Attempt to revoke dangerous permissions from the user
            try:
                # Fetch user's current permissions in the guild
                member_in_guild = guild.get_member(user_id)
                if member_in_guild:
                    await member_in_guild.edit(
                        kick_members=False, ban_members=False, manage_channels=False,
                        manage_roles=False, administrator=False, reason=f"Anti-Nuke: Triggered {activity_type} threshold"
                    )
                    print(f"Anti-Nuke: Revoked dangerous permissions from {user.display_name} in {guild.name}.")
            except discord.Forbidden:
                print(f"WARNING: Anti-Nuke: Bot forbidden from revoking permissions from {user.display_name}. Bot's role might be too low.")
            except Exception as e:
                print(f"ERROR: Anti-Nuke: Error revoking permissions for {user.display_name}: {e}")
            
            # Send alert to guild owner or specific admin channel (if one exists)
            owner = guild.owner
            if owner:
                try:
                    await owner.send(f"🚨 **ANTI-NUKE ALERT IN {guild.name}!** 🚨\n"
                                     f"User {user.mention} (`{user.id}`) has triggered a {activity_type.replace('_', ' ')} threshold.\n"
                                     f"Details: {details}. Permissions have been attempted to be revoked. Please review immediately!")
                except discord.Forbidden:
                    print(f"WARNING: Anti-Nuke: Bot forbidden from sending DM alert to guild owner {owner.id}.")
            
            # Reset activity for this user and type to avoid re-triggering immediately
            SUSPICIOUS_ACTIVITY[guild_id][user_id][activity_type] = []
        else:
            await guild.owner.send(f"⚠️ **ANTI-NUKE SAFE MODE ALERT IN {guild.name}!** ⚠️\n"
                                   f"User {user.mention} (`{user.id}`) has triggered a {activity_type.replace('_', ' ')} threshold.\n"
                                   f"Safe mode is ON. No automated actions taken, but please review immediately!")


# Anti-Nuke event listeners
@bot.event
async def on_guild_channel_delete(channel):
    if not ANTI_NUKE_ENABLED: return
    # Need to get who deleted it from audit logs
    guild = channel.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        if (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5 and entry.target.id == channel.id:
            await check_nuke_activity(guild, entry.user, "channel_delete", f"Channel: {channel.name} (`{channel.id}`)")
            return

@bot.event
async def on_member_ban(guild, user):
    if not ANTI_NUKE_ENABLED: return
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        if (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5 and entry.target.id == user.id:
            await check_nuke_activity(guild, entry.user, "member_ban", f"User: {user.name} (`{user.id}`)")
            return

@bot.event
async def on_member_remove(member): # This fires on kick or leave
    if not ANTI_NUKE_ENABLED: return
    guild = member.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5 and entry.target.id == member.id:
            await check_nuke_activity(guild, entry.user, "member_kick", f"User: {member.name} (`{member.id}`)")
            return

@bot.event
async def on_guild_role_update(before, after):
    if not ANTI_NUKE_ENABLED: return
    # Only check for permission escalation
    if before.permissions.administrator == after.permissions.administrator and \
       before.permissions.manage_roles == after.permissions.manage_roles and \
       before.permissions.manage_channels == after.permissions.manage_channels:
        return # No critical permission change

    guild = after.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
        if (datetime.now(timezone.utc) - entry.created_at).total_seconds() < 5 and entry.target.id == after.id:
            # Check if permissions were added/escalated
            if entry.changes and any(c.key == 'permissions' and c.new.administrator for c in entry.changes):
                await check_nuke_activity(guild, entry.user, "role_permission_escalation", f"Role: {after.name} (`{after.id}`)")
            return

# --- Anti-Nuke Commands ---
@bot.group(name="antinuke", invoke_without_command=True)
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def antinuke_group(ctx):
    """
    Manages the anti-nuke system.
    Usage: !antinuke <enable/disable/status/setthreshold/whitelist/log/setmodlog>
    """
    status = "Enabled" if ANTI_NUKE_ENABLED else "Disabled"
    safe_mode = "ON" if SAFE_MODE_ENABLED else "OFF"
    await ctx.send(f"Anti-Nuke system is currently **{status}**.\nSafe Mode is **{safe_mode}**.")

@antinuke_group.command(name="enable")
async def antinuke_enable(ctx):
    global ANTI_NUKE_ENABLED
    if ANTI_NUKE_ENABLED:
        return await ctx.send("Anti-Nuke system is already enabled.")
    ANTI_NUKE_ENABLED = True
    save_anti_nuke_config()
    await ctx.send("Anti-Nuke system **enabled**.")
    await send_mod_log(ctx.guild, "Anti-Nuke Status", f"Anti-Nuke system **enabled** by {ctx.author.mention}", discord.Color.green(), ctx.author)

@antinuke_group.command(name="disable")
async def antinuke_disable(ctx):
    global ANTI_NUKE_ENABLED
    if not ANTI_NUKE_ENABLED:
        return await ctx.send("Anti-Nuke system is already disabled.")
    ANTI_NUKE_ENABLED = False
    save_anti_nuke_config()
    await ctx.send("Anti-Nuke system **disabled**.")
    await send_mod_log(ctx.guild, "Anti-Nuke Status", f"Anti-Nuke system **disabled** by {ctx.author.mention}", discord.Color.red(), ctx.author)

@antinuke_group.command(name="status")
async def antinuke_status(ctx):
    status = "Enabled" if ANTI_NUKE_ENABLED else "Disabled"
    safe_mode = "ON" if SAFE_MODE_ENABLED else "OFF"
    
    whitelist_roles_names = [ctx.guild.get_role(r_id).name for r_id in MOD_WHITELIST_ROLES if ctx.guild.get_role(r_id)]
    whitelist_users_names = [(await bot.fetch_user(u_id)).display_name for u_id in MOD_WHITELIST_USERS if await bot.fetch_user(u_id)] # Await fetch for accuracy

    embed = discord.Embed(
        title="Anti-Nuke System Status",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    embed.add_field(name="System Status", value=f"`{status}`", inline=True)
    embed.add_field(name="Safe Mode", value=f"`{safe_mode}`", inline=True)
    
    thresholds_str = ""
    for action, config in NUKE_THRESHOLDS.items():
        thresholds_str += f"`{action.replace('_', ' ').title()}`: `{config['count']}` in `{config['time_period']}`s\n"
    embed.add_field(name="Threat Thresholds", value=thresholds_str if thresholds_str else "`None configured`", inline=False)

    embed.add_field(name="Whitelisted Roles", value=f"`{', '.join(whitelist_roles_names) if whitelist_roles_names else 'None'}`", inline=False)
    embed.add_field(name="Whitelisted Users", value=f"`{', '.join(whitelist_users_names) if whitelist_users_names else 'None'}`", inline=False)
    embed.add_field(name="Moderation Log Channel", value=f"{bot.get_channel(MOD_LOG_CHANNEL_ID).mention if MOD_LOG_CHANNEL_ID else '`None`'}", inline=False)

    await ctx.send(embed=embed)

@antinuke_group.command(name="safe_mode")
async def safe_mode_toggle(ctx, status: str):
    global SAFE_MODE_ENABLED
    status = status.lower()
    if status == "on":
        if SAFE_MODE_ENABLED:
            return await ctx.send("Safe Mode is already ON.")
        SAFE_MODE_ENABLED = True
        save_anti_nuke_config()
        await ctx.send("Anti-Nuke Safe Mode **activated**. Automated countermeasures are paused.")
        await send_mod_log(ctx.guild, "Anti-Nuke Safe Mode", f"Safe Mode **activated** by {ctx.author.mention}", discord.Color.orange(), ctx.author)
    elif status == "off":
        if not SAFE_MODE_ENABLED:
            return await ctx.send("Safe Mode is already OFF.")
        SAFE_MODE_ENABLED = False
        save_anti_nuke_config()
        await ctx.send("Anti-Nuke Safe Mode **deactivated**. Automated countermeasures are active.")
        await send_mod_log(ctx.guild, "Anti-Nuke Safe Mode", f"Safe Mode **deactivated** by {ctx.author.mention}", discord.Color.green(), ctx.author)
    else:
        await ctx.send("Invalid status. Please use `on` or `off`.")

@antinuke_group.command(name="setthreshold")
async def set_nuke_threshold(ctx, action_type: str, count: int, time_period_seconds: int):
    """
    Configures thresholds for suspicious activity.
    Usage: !antinuke setthreshold <action_type> <count> <time_period_seconds>
    Action types: channel_delete, member_ban, member_kick, role_permission_escalation
    """
    valid_actions = ["channel_delete", "member_ban", "member_kick", "role_permission_escalation"]
    if action_type.lower() not in valid_actions:
        return await ctx.send(f"Invalid action type. Must be one of: `{', '.join(valid_actions)}`")
    if count <= 0 or time_period_seconds <= 0:
        return await ctx.send("Count and time period must be positive integers.")
    
    NUKE_THRESHOLDS[action_type.lower()] = {"count": count, "time_period": time_period_seconds}
    save_anti_nuke_config()
    await ctx.send(f"Threshold for `{action_type}` updated: `{count}` actions within `{time_period_seconds}` seconds.")
    await send_mod_log(ctx.guild, "Anti-Nuke Threshold Updated", f"Threshold for `{action_type}` set to `{count}` in `{time_period_seconds}s` by {ctx.author.mention}", discord.Color.blue(), ctx.author)

@antinuke_group.command(name="whitelist")
async def antinuke_whitelist(ctx, type: str, entity: discord.Role | discord.Member):
    """
    Manages the anti-nuke whitelist.
    Usage: !antinuke whitelist <add/remove> <@role/@user>
    """
    global MOD_WHITELIST_ROLES, MOD_WHITELIST_USERS
    
    if type.lower() not in ["add", "remove"]:
        return await ctx.send("Invalid type. Must be `add` or `remove`.")

    if isinstance(entity, discord.Role):
        if type.lower() == "add":
            if entity.id in MOD_WHITELIST_ROLES:
                return await ctx.send(f"Role {entity.mention} is already whitelisted.")
            MOD_WHITELIST_ROLES.append(entity.id)
            await ctx.send(f"Role {entity.mention} added to whitelist.")
        else: # remove
            if entity.id not in MOD_WHITELIST_ROLES:
                return await ctx.send(f"Role {entity.mention} is not in the whitelist.")
            MOD_WHITELIST_ROLES.remove(entity.id)
            await ctx.send(f"Role {entity.mention} removed from whitelist.")
    elif isinstance(entity, discord.Member):
        if type.lower() == "add":
            if entity.id in MOD_WHITELIST_USERS:
                return await ctx.send(f"User {entity.mention} is already whitelisted.")
            MOD_WHITELIST_USERS.append(entity.id)
            await ctx.send(f"User {entity.mention} added to whitelist.")
        else: # remove
            if entity.id not in MOD_WHITELIST_USERS:
                return await ctx.send(f"User {entity.mention} is not in the whitelist.")
            MOD_WHITELIST_USERS.remove(entity.id)
            await ctx.send(f"User {entity.mention} removed from whitelist.")
    else:
        return await ctx.send("Invalid entity. Please mention a role or a user.")
    
    save_anti_nuke_config()
    await send_mod_log(ctx.guild, "Anti-Nuke Whitelist Update", f"{entity.mention} {type.lower()}ed to anti-nuke whitelist by {ctx.author.mention}", discord.Color.blue(), ctx.author)

@antinuke_group.command(name="log")
async def nuke_log_command(ctx):
    """
    View a dedicated log of all anti-nuke system activities.
    Usage: !antinuke log
    """
    if not ANTI_NUKE_LOGS:
        return await ctx.send("No anti-nuke logs available yet.")

    embed = discord.Embed(
        title="🚨 Anti-Nuke System Logs 🚨",
        color=discord.Color.dark_red(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    # Display logs in reverse chronological order
    for entry in reversed(ANTI_NUKE_LOGS):
        actor_mention = f"<@{entry['actor_id']}>" if entry['actor_id'] else entry['actor_name']
        
        embed.add_field(
            name=f"{entry['action_type'].replace('_', ' ').title()} ({entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')})",
            value=(
                f"**Actor:** {actor_mention} (`{entry['actor_id'] or 'N/A'}`)\n"
                f"**Target:** {entry['target_info']}\n"
                f"**Details:** `{entry['details']}`\n"
                f"**Countermeasure:** `{entry['countermeasure_taken']}`"
            ),
            inline=False
        )
    
    await ctx.send(embed=embed)

@antinuke_group.command(name="setmodlog")
@commands.has_permissions(administrator=True)
async def set_mod_log_channel(ctx, channel: discord.TextChannel):
    """
    Designates a specific channel where all moderation actions performed by the bot will be logged.
    Usage: !antinuke setmodlog <#channel>
    """
    global MOD_LOG_CHANNEL_ID
    MOD_LOG_CHANNEL_ID = channel.id
    save_anti_nuke_config()
    await ctx.send(f"Moderation logs will now be sent to {channel.mention}.")
    await send_mod_log(ctx.guild, "Moderation Log Channel Set", f"Moderation log channel set to {channel.mention} by {ctx.author.mention}", discord.Color.blue(), ctx.author, channel)

# --- Updated Help Command ---
@bot.command(name="cmds", aliases=["commands", "help"])
async def help_command(ctx):
    """
    Displays a list of all available commands.
    Usage: !cmds
    """
    embed = discord.Embed(
        title="Bot Commands",
        description="Here's a list of all available commands and their usage:",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="made by summers 2000")

    # --- Moderation Commands (Split into multiple fields) ---
    moderation_commands_desc_1 = (
        f"`!ban <@user> [reason]`: Bans a member from the server.\n"
        f"`!unban <user_id>`: Unbans a user by their ID.\n"
        f"`!kick <@user> [reason]`: Kicks a member from the server.\n"
        f"`!mute <@user> [duration_minutes] [reason]`: Mutes a member. Requires a 'Muted' role.\n"
        f"`!unmute <@user>`: Unmutes a member.\n"
        f"`!slowmode <seconds>`: Sets slowmode for the channel (0 to disable).\n"
        f"`!clear <amount>`: Deletes a specified number of messages (max 100).\n"
        f"`!auditlog <action>`: Views recent server audit log entries.\n"
        f"`!warn <@user> [reason]`: Issues a warning to a user."
    )
    moderation_commands_desc_2 = (
        f"`!warnings [@user]`: Displays a list of warnings for a user.\n"
        f"`!warn_remove <@user> <id>`: Removes a specific warning.\n"
        f"`!lockdown [reason]`: Locks down the current channel.\n"
        f"`!unlock [reason]`: Unlocks a previously locked channel.\n"
        f"`!softban <@user> [reason]`: Kicks a user and removes messages, but doesn't ban.\n"
        f"`!nick <@user> [nickname]`: Changes or resets a user's nickname.\n"
        f"`!voicekick <@user> [reason]`: Disconnects a user from a voice channel.\n"
        f"`!tempmute <@user> <duration> [reason]`: Mutes a user for a duration (e.g., 30m, 1h).\n"
        f"`!reactionrole <msg_id> <emoji> <@role>`: Sets up a reaction role."
    )
    embed.add_field(name="__Moderation Commands__", value=moderation_commands_desc_1, inline=False)
    embed.add_field(name="\u200b", value=moderation_commands_desc_2, inline=False) # \u200b is a zero-width space for an empty field name

    # --- Utility Commands ---
    utility_commands_desc = (
        f"`!uptime`: Shows how long the bot has been online.\n"
        f"`!remindme <time> <message>`: Sets a personal reminder (e.g., `1h Check crops`).\n"
        f"`!remindme_list`: Lists your active reminders.\n"
        f"`!remindme_clear`: Clears all your reminders.\n"
        f"`!avatar [@user]`: Displays a user's avatar.\n"
        f"`!ping`: Shows the bot's latency.\n"
        f"`!define <word>`: Get the definition of a word.\n"
        f"`!serverinfo`: Displays server information.\n"
        f"`!userinfo [@user]`: Displays detailed user information.\n"
        f"`!channelinfo [#channel]`: Displays channel details.\n"
        f"`!roleinfo <role_name>`: Shows information about a role."
    )
    embed.add_field(name="__Utility Commands__", value=utility_commands_desc, inline=False)

    # --- Game & Fun Commands (Combined and split) ---
    game_fun_commands_desc_1 = (
        f"`!c4 <@opponent>`: Starts a game of Connect4.\n"
        f"`!tictactoe <@opponent>`: Starts a game of Tic-Tac-Toe.\n"
        f"`!gamestats`: Shows your game statistics.\n"
        f"`!c4leaderboard`: Shows the Connect4 leaderboard.\n"
        f"`!tttleaderboard`: Shows the Tic-Tac-Toe leaderboard.\n"
        f"`!roll [number]`: Rolls a dice (default 100).\n"
        f"`!lotto <buy|draw|status>`: Interact with the server lottery.\n"
        f"`!blackjack <bet>`: Play a game of Blackjack.\n"
        f"`!slots <bet>`: Play a game of Slots."
    )
    game_fun_commands_desc_2 = (
        f"`!8ball <question>`: Get a random answer to a yes/no question.\n"
        f"`!fact`: Fetches a random fact.\n"
        f"`!joke`: Fetches a random joke.\n"
        f"`!ship <@user1> <@user2>`: Calculates compatibility.\n"
        f"`!poll \"Question\" \"Opt1\" ...`: Creates a reaction poll.\n"
        f"`!quote_add \"text\" - [author]`: Adds a quote.\n"
        f"`!quote_random`: Fetches a random quote."
    )
    embed.add_field(name="__Game & Fun Commands__", value=game_fun_commands_desc_1, inline=False)
    embed.add_field(name="\u200b", value=game_fun_commands_desc_2, inline=False)

    # --- Economy Commands (Split into multiple fields) ---
    economy_commands_desc_1 = (
        f"`!balance`: Checks your coin balance.\n"
        f"`!daily`: Claims your daily coin bonus.\n"
        f"`!daily_streak`: Displays your daily claim streak.\n"
        f"`!transfer <@user> <amount>`: Sends coins to another user.\n"
        f"`!shop`: Views items available for purchase.\n"
        f"`!buy <item> [qty]`: Buys an item from the shop.\n"
        f"`!sell <item> [qty]`: Sells an item from your inventory."
    )
    economy_commands_desc_2 = (
        f"`!inventory`: Views your current items.\n"
        f"`!use <item>`: Uses a consumable item.\n"
        f"`!craft <recipe>`: Crafts an item.\n"
        f"`!recipes`: Views available crafting recipes.\n"
        f"`!iteminfo <item>`: Gets info about an item.\n"
        f"`!richest`: Shows the leaderboard of richest users.\n"
        f"`!coinflip <amount> [h/t]`: Bets coins on a coin flip."
    )
    embed.add_field(name="__Economy Commands__", value=economy_commands_desc_1, inline=False)
    embed.add_field(name="\u200b", value=economy_commands_desc_2, inline=False)

    # --- Anti-Nuke and Ban Request Commands ---
    security_commands_desc = (
        f"`!banrequest`: Initiates a ban request via DM.\n"
        f"`!antinuke <subcommand>`: Manages the anti-nuke system. Use `!antinuke` for details."
    )
    embed.add_field(name="__Security & Special Commands__", value=security_commands_desc, inline=False)


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
    import traceback
    traceback.print_exc() # Print full traceback for debugging
    exit(1) # Exit with error code
