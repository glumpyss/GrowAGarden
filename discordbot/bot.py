import os
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json

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

STOCK_LOGS = [] # Stores a history of stock changes

# Bot start time for uptime command
BOT_START_TIME = datetime.utcnow()

# --- Game States ---
active_c4_games = {} # {channel_id: Connect4Game instance}
active_tictactoe_games = {} # {channel_id: TicTacToeGame instance}

# --- DM Notification Specifics ---
DM_NOTIFY_ROLE_ID = 1302076375922118696  # The specific role ID for DM notifications
DM_NOTIFICATION_LOG_CHANNEL_ID = 1379734424895361054 # Channel to log stock changes for DM notifications
DM_NOTIFIED_USERS = {} # {user_id: True/False (enabled/disabled)}

# Define which items to monitor for DM notifications, by category
DM_MONITORED_CATEGORIES = {
    "seedsStock": ["Beanstalk Seed", "Pepper Seed", "Mushroom Seed"],
    "gearStock": ["Watering Can", "Shovel", "Axe"] # Example gear items to monitor
}
# Stores the last known status of monitored items for DM notifications, per category
LAST_KNOWN_DM_ITEM_STATUS = {category: set() for category in DM_MONITORED_CATEGORIES.keys()}

DM_USERS_FILE = 'dm_users.json' # File to persist DM_NOTIFIED_USERS

# --- Helper Functions for DM Notification Persistence ---
def load_dm_users():
    """Loads DM notification user data from a JSON file."""
    global DM_NOTIFIED_USERS
    if os.path.exists(DM_USERS_FILE):
        with open(DM_USERS_FILE, 'r') as f:
            try:
                data = json.load(f)
                # Convert string keys back to int for user IDs
                DM_NOTIFIED_USERS = {int(k): v for k, v in data.items()}
                print(f"Loaded {len(DM_NOTIFIED_USERS)} DM notification users.")
            except json.JSONDecodeError:
                print(f"Error decoding {DM_USERS_FILE}. Starting with empty DM user list.")
                DM_NOTIFIED_USERS = {}
    else:
        DM_NOTIFIED_USERS = {}
        print(f"{DM_USERS_FILE} not found. Starting with empty DM user list.")

def save_dm_users():
    """Saves DM notification user data to a JSON file."""
    with open(DM_USERS_FILE, 'w') as f:
        # Convert int keys to string for JSON serialization
        json.dump({str(k): v for k, v in DM_NOTIFIED_USERS.items()}, f, indent=4)
    print(f"Saved {len(DM_NOTIFIED_USERS)} DM notification users.")


# --- Helper Function for API Calls ---
async def fetch_api_data(url, method='GET', json_data=None):
    """Fetches data from a given API URL."""
    async with aiohttp.ClientSession() as session:
        try:
            if method == 'GET':
                async with session.get(url) as response:
                    print(f"API Response Status ({url}): {response.status}")
                    response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                    try:
                        json_data = await response.json()
                        return json_data
                    except aiohttp.ContentTypeError:
                        text_data = await response.text()
                        print(f"API Error: Content-Type is not application/json for {url}. Raw text: {text_data}")
                        return None
            elif method == 'POST':
                async with session.post(url, json=json_data) as response:
                    print(f"API Response Status ({url}): {response.status}")
                    response.raise_for_status()
                    try:
                        json_data = await response.json()
                        return json_data
                    except aiohttp.ContentTypeError:
                        text_data = await response.text()
                        print(f"API Error: Content-Type is not application/json for {url}. Raw text: {text_data}")
                        return None
        except aiohttp.ClientError as e:
            print(f"API Client Error (network/connection issue) for {url}: {e}")
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

    # Start the autostock task when the bot is ready
    if not autostock_checker.is_running():
        autostock_checker.start()
        print("Autostock checker task started.")
    else:
        print("Autostock checker task is already running.")

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
    elif status == "off":
        if not AUTOSTOCK_ENABLED:
            await ctx.send("Auto-stock is already disabled.")
            return
        AUTOSTOCK_ENABLED = False
        AUTOSTOCK_CHANNEL_ID = None # Clear the channel ID when turned off
        await ctx.send("Auto-stock updates are now **disabled**.")
    else:
        await ctx.send("Invalid status provided. Please use `on` or `off`.")

@tasks.loop(minutes=5) # Checks every 5 minutes
async def autostock_checker():
    """Background task to check for new stock updates."""
    global AUTOSTOCK_ENABLED, LAST_STOCK_DATA, AUTOSTOCK_CHANNEL_ID, STOCK_LOGS, LAST_KNOWN_DM_ITEM_STATUS

    # --- General Autostock Update ---
    if AUTOSTOCK_ENABLED and AUTOSTOCK_CHANNEL_ID is not None:
        current_stock_data = await fetch_api_data(STOCK_API_URL)

        if current_stock_data is None:
            print("Autostock: Failed to fetch current stock data. Skipping update for this cycle.")
            # Don't return here, as DM notifications might still work if API was only temporarily down
        else:
            # Helper to normalize the ENTIRE stock data for comparison (order-independent comparison of all items)
            def normalize_full_stock_data(data):
                if not data:
                    return frozenset()

                normalized_items = []
                for category_key, items_list in data.items():
                    # Skip 'lastSeen' as it's metadata, not actual stock
                    if category_key == 'lastSeen':
                        continue
                    if isinstance(items_list, list):
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
                channel = bot.get_channel(AUTOSTOCK_CHANNEL_ID)
                if channel:
                    # Create a single embed for all relevant stock types
                    embed = create_stock_embed(current_stock_data, title="New Shop Stock Update!")
                    try:
                        await channel.send(embed=embed)
                        print(f"Autostock: New stock detected and sent to channel {channel.name} ({channel.id}).")

                        # Log the stock change (can be expanded to log more details)
                        stock_time = datetime.now()
                        # Get names for logging from a few categories
                        log_details = []
                        for cat_key in ['seedsStock', 'eggStock', 'gearStock', 'cosmeticsStock', 'honeyStock']:
                            items = current_stock_data.get(cat_key, [])
                            if items:
                                item_names = [item.get('name', 'Unknown') for item in items]
                                log_details.append(f"{cat_key.replace('Stock', '').capitalize()}: {', '.join(item_names)}")
                        
                        log_entry = " | ".join(log_details) if log_details else "No new stock items detected for log."
                        STOCK_LOGS.append({'time': stock_time, 'details': log_entry})

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

                # Always update LAST_STOCK_DATA with the full, new data after comparison and potential notification
                LAST_STOCK_DATA = current_stock_data

    # --- DM Notification Specific Logic ---
    if current_stock_data: # Only proceed if we successfully fetched stock data
        for category_key, monitored_items_list in DM_MONITORED_CATEGORIES.items():
            category_stock = current_stock_data.get(category_key, [])
            
            currently_available_dm_items = {
                item['name'] for item in category_stock
                if item['name'] in monitored_items_list and item.get('value', 0) > 0
            }

            newly_in_stock_for_dm = currently_available_dm_items - LAST_KNOWN_DM_ITEM_STATUS[category_key]

            if newly_in_stock_for_dm:
                log_channel = bot.get_channel(DM_NOTIFICATION_LOG_CHANNEL_ID)
                if log_channel:
                    log_message = f"**{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} - New DM-Monitored {category_key.replace('Stock', '').capitalize()} In Stock:**\n"
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
                    title=f"GrowAGarden Stock Alert! ({category_key.replace('Stock', '').capitalize()})",
                    description=f"The following {category_key.replace('Stock', '').lower()} you're monitoring are now in stock:",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                dm_embed.set_footer(text="made by summers 2000")

                for item_name in newly_in_stock_for_dm:
                    dm_embed.add_field(name=f"✅ {item_name}", value="Available now!", inline=False)

                for user_id, enabled in DM_NOTIFIED_USERS.items():
                    if enabled:
                        user = bot.get_user(user_id)
                        if user is None:
                            try:
                                user = await bot.fetch_user(user_id)
                            except discord.NotFound:
                                print(f"DM User {user_id} not found. Skipping DM.")
                                continue
                            except Exception as e:
                                print(f"Error fetching DM user {user_id}: {e}. Skipping DM.")
                                continue

                        if user:
                            try:
                                await user.send(embed=dm_embed)
                                print(f"Sent DM notification to {user.name} ({user.id}) for new {category_key.replace('Stock', '').lower()}.")
                            except discord.Forbidden:
                                print(f"Could not send DM to {user.name} ({user.id}). User has DMs disabled or blocked bot.")
                            except Exception as e:
                                print(f"An unexpected error occurred while sending DM to {user.name} ({user.id}): {e}")

            # Update the last known status for this category
            LAST_KNOWN_DM_ITEM_STATUS[category_key] = currently_available_dm_items


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
        await ctx.send("No stock logs available yet. The autostock feature needs to be `on` for a while to gather logs.")
        return

    embed = discord.Embed(
        title="Recent Stock Change Logs",
        description="Showing the latest stock changes:",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000") # Footer for this embed

    # Display logs in reverse order (most recent first)
    for log in reversed(STOCK_LOGS):
        time_str = log['time'].strftime("%Y-%m-%d %H:%M:%S UTC")
        embed.add_field(
            name=f"Change detected at {time_str}",
            value=f"{log['details']}",
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

        if not restock_data or 'timeUntilRestock' not in restock_data:
            await ctx.send("Apologies, I couldn't retrieve the next restock time. The API might be down or returned no data.")
            return

        time_until_restock = restock_data['timeUntilRestock']
        human_readable_time = restock_data.get('humanReadableTime', 'N/A')

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
        title="GrowAGarden Bot Commands",
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
        f"`!restock`: Shows the next planned restock time." # Changed to !restock
    )
    embed.add_field(name="__Stock & Auto-Stock Commands__", value=stock_commands_desc, inline=False)

    # --- Moderation Commands ---
    moderation_commands_desc = (
        f"`!ban <@user> [reason]`: Bans a member from the server.\n"
        f"`!unban <user_id>`: Unbans a user by their ID.\n"
        f"`!kick <@user> [reason]`: Kicks a member from the server.\n"
        f"`!mute <@user> [duration_minutes] [reason]`: Mutes a member. Requires a 'Muted' role.\n"
        f"`!unmute <@user>`: Unmutes a member.\n"
        f"`!slowmode <seconds>`: Sets slowmode for the channel (0 to disable).\n"
        f"`!clear <amount>` (or `!purge`): Deletes a specified number of messages (max 100)."
    )
    embed.add_field(name="__Moderation Commands__", value=moderation_commands_desc, inline=False)

    # --- Utility Commands ---
    utility_commands_desc = (
        f"`!weather`: Displays current in-game weather conditions (e.g., Rain, Sunny).\n" # Updated description
        f"`!uptime`: Shows how long the bot has been online.\n"
        f"`!rblxusername <username>`: Finds a Roblox player's profile by username.\n"
        f"`!cmds` (or `!commands`, `!help`): Displays this help message."
    )
    embed.add_field(name="__Utility Commands__", value=utility_commands_desc, inline=False)

    # --- Game Commands ---
    game_commands_desc = (
        f"`!c4 <@opponent>`: Starts a game of Connect4.\n"
        f"`!tictactoe <@opponent>`: Starts a game of Tic-Tac-Toe."
    )
    embed.add_field(name="__Game Commands__", value=game_commands_desc, inline=False)

    # --- DM Notification Commands ---
    dm_notify_commands_desc = (
        f"`!seedstockdm`: Toggles DM notifications for Beanstalk, Pepper, and Mushroom seeds. (Role ID: `{DM_NOTIFY_ROLE_ID}` required)\n"
        f"`!gearstockdm`: Toggles DM notifications for monitored gear items. (Role ID: `{DM_NOTIFY_ROLE_ID}` required)"
    )
    embed.add_field(name="__DM Notification Commands__", value=dm_notify_commands_desc, inline=False)


    await ctx.send(embed=embed)

# --- DM Notification Command for Seeds ---
@bot.command(name="seedstockdm")
@commands.guild_only()
async def seed_stock_dm_toggle(ctx):
    """
    Toggles DM notifications for Beanstalk, Pepper, and Mushroom seeds.
    Only works for users with a specific role ID.
    Usage: !seedstockdm
    """
    # Check if the user has the required role
    required_role = discord.utils.get(ctx.guild.roles, id=DM_NOTIFY_ROLE_ID)
    if not required_role or required_role not in ctx.author.roles:
        embed = discord.Embed(
            title="Permission Denied",
            description=f"You need the role with ID `{DM_NOTIFY_ROLE_ID}` to use this command.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed, delete_after=10)
        return

    # DM_NOTIFIED_USERS stores a boolean for each user, indicating if ANY DM notification is enabled.
    # The specific items they monitor are defined in DM_MONITORED_CATEGORIES.
    # For now, this toggle will simply enable/disable ALL DM notifications for the user.
    # If more granular control is needed (e.g., enable seeds but disable gear for a user),
    # DM_NOTIFIED_USERS would need to store a dictionary of preferences per user.
    # For this request, I'll keep the current simple toggle logic for the user.

    if DM_NOTIFIED_USERS.get(ctx.author.id, False):
        DM_NOTIFIED_USERS[ctx.author.id] = False
        status_message = "disabled"
        color = discord.Color.red()
    else:
        DM_NOTIFIED_USERS[ctx.author.id] = True
        status_message = "enabled"
        color = discord.Color.green()

    save_dm_users() # Save the updated state

    embed = discord.Embed(
        title="DM Notification Status",
        description=f"Your DM notifications for monitored seeds and gear have been **{status_message}**.",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await ctx.author.send(f"Your GrowAGarden stock DM notifications are now **{status_message}**.")

# --- DM Notification Command for Gear ---
@bot.command(name="gearstockdm")
@commands.guild_only()
async def gear_stock_dm_toggle(ctx):
    """
    Toggles DM notifications for specific gear items.
    Only works for users with a specific role ID.
    Usage: !gearstockdm
    """
    # Check if the user has the required role
    required_role = discord.utils.get(ctx.guild.roles, id=DM_NOTIFY_ROLE_ID)
    if not required_role or required_role not in ctx.author.roles:
        embed = discord.Embed(
            title="Permission Denied",
            description=f"You need the role with ID `{DM_NOTIFY_ROLE_ID}` to use this command.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="made by summers 2000")
        await ctx.send(embed=embed, delete_after=10)
        return

    # This command uses the same global DM_NOTIFIED_USERS toggle.
    # If more granular control is needed (e.g., enable seeds but disable gear for a user),
    # DM_NOTIFIED_USERS would need to store a dictionary of preferences per user.
    # For this request, I'll keep the current simple toggle logic for the user.

    if DM_NOTIFIED_USERS.get(ctx.author.id, False):
        DM_NOTIFIED_USERS[ctx.author.id] = False
        status_message = "disabled"
        color = discord.Color.red()
    else:
        DM_NOTIFIED_USERS[ctx.author.id] = True
        status_message = "enabled"
        color = discord.Color.green()

    save_dm_users() # Save the updated state

    embed = discord.Embed(
        title="DM Notification Status",
        description=f"Your DM notifications for monitored seeds and gear have been **{status_message}**.",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="made by summers 2000")
    await ctx.send(embed=embed)
    await ctx.author.send(f"Your GrowAGarden stock DM notifications are now **{status_message}**.")


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
                    await reaction.message.clear_reactions()
                except discord.Forbidden:
                    pass # Bot might not have permission

                if game._check_win():
                    game.winner = game.current_turn_emoji
                    await game.update_game_message()
                    del active_c4_games[channel_id] # Game over, remove from active games
                    await reaction.message.channel.send(f"Congratulations, {user.mention}! You won the Connect4 game!")
                elif game._check_draw():
                    game.draw = True
                    await game.update_game_message()
                    del active_c4_games[channel_id]
                    await reaction.message.channel.send("The Connect4 game is a draw!")
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
                    await reaction.message.clear_reactions()
                except discord.Forbidden:
                    pass
                await reaction.message.channel.send(f"{user.mention}, {error_msg} Please choose another spot.", delete_after=5)

                if game._check_win():
                    game.winner = game.current_turn_emoji
                    await game.update_game_message()
                    del active_tictactoe_games[channel_id] # Game over, remove from active games
                    await reaction.message.channel.send(f"Congratulations, {user.mention}! You won the Tic-Tac-Toe game!")
                elif game._check_draw():
                    game.draw = True
                    await game.update_game_message()
                    del active_tictactoe_games[channel_id]
                    await reaction.message.channel.send("The Tic-Tac-Toe game is a draw!")
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
