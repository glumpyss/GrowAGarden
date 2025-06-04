import os # <--- IMPORTANT: Added this import for environment variables
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta

# --- Bot Setup ---
# Define Intents: Crucial for your bot to receive events from Discord.
# You MUST enable these in your Discord Developer Portal under your bot's settings.
# 1. PRESENCE INTENT
# 2. SERVER MEMBERS INTENT
# 3. MESSAGE CONTENT INTENT
intents = discord.Intents.default()
intents.members = True          # Required for moderation commands (ban, kick, mute, unmute)
intents.message_content = True  # Required for reading command messages (e.g., !stock, !clear)
intents.presences = True        # Good practice for member presence updates, though not strictly required for current commands

bot = commands.Bot(command_prefix=("!", ":"), intents=intents)

# --- Global Variables for Autostock ---
AUTOSTOCK_ENABLED = False
LAST_STOCK_DATA = None
STOCK_API_URL = "https://growagardenapi.vercel.app/api/stock/GetStock"

# !!! IMPORTANT !!!
# Set this to the ID of the channel where you want autostock updates to be sent.
# You can get a channel's ID by right-clicking on it in Discord and selecting "Copy ID".
# Make sure Developer Mode is enabled in Discord settings (User Settings -> Advanced).
AUTOSTOCK_CHANNEL_ID = YOUR_AUTOSTOCK_CHANNEL_ID_HERE # <-- REPLACE WITH YOUR CHANNEL ID (e.g., 123456789012345678)

STOCK_LOGS = [] # Stores a history of stock changes

# --- Helper Function for API Calls ---
async def fetch_stock_data():
    """Fetches stock data from the GrowAGarden API."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(STOCK_API_URL) as response:
                response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"API Error: Error fetching stock data: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during API fetch: {e}")
            return None

# --- Helper Function to Create Stock Embed ---
def create_stock_embed(data, title="Current Stock Information"):
    """Creates a Discord Embed for stock data."""
    embed = discord.Embed(
        title=title,
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="GrowAGarden Bot")

    if not data:
        embed.description = "No stock information available."
        return embed

    # Add fields for each item in stock
    for item in data:
        # Ensure all expected keys exist before accessing to prevent KeyError
        if all(key in item for key in ['name', 'category', 'price', 'quantity', 'image']):
            embed.add_field(name=f"{item['name']} ({item['category'].capitalize()})",
                            value=(f"Price: {item['price']}\n"
                                   f"Quantity: {item['quantity']}"),
                            inline=True)
        else:
            # Log missing keys for debugging purposes
            print(f"Warning: Item missing expected keys in API response: {item}")
            embed.add_field(name="Incomplete Item Data", value=str(item), inline=True)
    return embed

# --- Events ---
@bot.event
async def on_ready():
    """Event that fires when the bot successfully connects to Discord."""
    print(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    print("Bot is ready to receive commands!")
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
        await ctx.send(f"**Error:** Missing arguments. Please check the command usage. Example: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"**Error:** Invalid argument provided. Please check the command usage. Example: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.CommandNotFound):
        # Silently ignore if command is not found, or respond with a "Command not found" message
        # await ctx.send("Unknown command. Type `!help` for a list of commands.")
        pass
    elif isinstance(error, commands.MissingPermissions):
        missing_perms = [p.replace('_', ' ').title() for p in error.missing_permissions]
        await ctx.send(f"**Error:** You don't have the necessary permissions to use this command. You need: `{', '.join(missing_perms)}`")
    elif isinstance(error, commands.BotMissingPermissions):
        missing_perms = [p.replace('_', ' ').title() for p in error.missing_permissions]
        await ctx.send(f"**Error:** I don't have the necessary permissions to perform this action. Please ensure I have: `{', '.join(missing_perms)}`")
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command cannot be used in private messages.")
    else:
        # For unhandled errors, print to console and optionally send a generic message
        print(f"An unhandled error occurred in command '{ctx.command.name}': {error}")
        await ctx.send(f"**An unexpected error occurred:** `{error}`. Please try again later or contact an administrator.")

# --- Stock Commands ---

@bot.command(name="seeds")
async def get_seeds(ctx):
    """
    Displays current stock information for seeds.
    Usage: !seeds
    """
    await ctx.send("Fetching seed information...")
    all_stock_data = await fetch_stock_data()
    if not all_stock_data:
        await ctx.send("Could not retrieve stock information. Please try again later.")
        return

    seed_data = [item for item in all_stock_data if item.get('category', '').lower() == 'seeds']
    if not seed_data:
        await ctx.send("No seed stock information available at this time.")
        return

    embed = create_stock_embed(seed_data, title="Current Seed Stock")
    await ctx.send(embed=embed)

@bot.command(name="stock")
async def get_stock_by_category(ctx, category: str = None):
    """
    Displays current stock information for a specific category.
    Usage: !stock [category] (e.g., !stock seeds)
    Available categories: seeds, eggs, bees, cosmetics, gear
    """
    if category is None:
        await ctx.send("Please specify a category. Available categories: `seeds`, `eggs`, `bees`, `cosmetics`, `gear`.")
        return

    valid_categories = ['seeds', 'eggs', 'bees', 'cosmetics', 'gear']
    category = category.lower()

    if category not in valid_categories:
        await ctx.send(f"Invalid category. Available categories: {', '.join(valid_categories)}")
        return

    await ctx.send(f"Fetching {category} stock information...")
    all_stock_data = await fetch_stock_data()
    if not all_stock_data:
        await ctx.send("Could not retrieve stock information. Please try again later.")
        return

    filtered_stock_data = [item for item in all_stock_data if item.get('category', '').lower() == category]
    if not filtered_stock_data:
        await ctx.send(f"No {category} stock information available at this time.")
        return

    embed = create_stock_embed(filtered_stock_data, title=f"Current {category.capitalize()} Stock")
    await ctx.send(embed=embed)

@bot.command(name="autostock")
@commands.has_permissions(manage_channels=True) # Requires "Manage Channels" permission to use
async def autostock_toggle(ctx, status: str = None):
    """
    Toggles automatic stock updates.
    Usage: !autostock on/off
    """
    global AUTOSTOCK_ENABLED, AUTOSTOCK_CHANNEL_ID

    if status is None:
        current_status = "enabled" if AUTOSTOCK_ENABLED else "disabled"
        channel_info = f" in <#{AUTOSTOCK_CHANNEL_ID}>" if AUTOSTOCK_ENABLED and AUTOSTOCK_CHANNEL_ID else ""
        await ctx.send(f"Auto-stock is currently **{current_status}**{channel_info}. Please specify `on` or `off` to toggle.")
        return

    status = status.lower()
    if status == "on":
        if AUTOSTOCK_ENABLED:
            await ctx.send("Auto-stock is already enabled.")
            return

        # Ensure a valid channel ID is set for autostock
        if AUTOSTOCK_CHANNEL_ID is None or AUTOSTOCK_CHANNEL_ID == YOUR_AUTOSTOCK_CHANNEL_ID_HERE:
            await ctx.send(f"**Warning:** `AUTOSTOCK_CHANNEL_ID` is not properly configured in the bot's code. Please set it to a valid channel ID.")
            return

        AUTOSTOCK_ENABLED = True
        # AUTOSTOCK_CHANNEL_ID is meant to be set in the code initially, not dynamically via command
        # If you wanted it to set the current channel, you'd do: AUTOSTOCK_CHANNEL_ID = ctx.channel.id
        # But for persistent autostock in one channel, it's best set in the global variable above.
        await ctx.send(f"Auto-stock updates are now **enabled** and will be sent to <#{AUTOSTOCK_CHANNEL_ID}>.")
        # Trigger an immediate check when turned on, to send current stock
        await autostock_checker()
    elif status == "off":
        if not AUTOSTOCK_ENABLED:
            await ctx.send("Auto-stock is already disabled.")
            return
        AUTOSTOCK_ENABLED = False
        await ctx.send("Auto-stock updates are now **disabled**.")
    else:
        await ctx.send("Invalid status. Please use `on` or `off`.")

@tasks.loop(minutes=5) # Checks every 5 minutes
async def autostock_checker():
    """Background task to check for new stock updates."""
    global LAST_STOCK_DATA, AUTOSTOCK_ENABLED, AUTOSTOCK_CHANNEL_ID, STOCK_LOGS

    if not AUTOSTOCK_ENABLED or AUTOSTOCK_CHANNEL_ID is None:
        return

    current_stock_data = await fetch_stock_data()

    if current_stock_data is None:
        print("Autostock: Failed to fetch current stock data. Skipping update.")
        return

    # Helper to normalize stock data for comparison (order-independent comparison)
    def normalize_stock_data(data):
        if not data:
            return frozenset() # Use frozenset for efficient comparison of lists of dicts
        # Convert each dictionary to a frozenset of its items, then put them in a frozenset
        # This makes comparison robust to order and content
        return frozenset(frozenset(d.items()) for d in data)

    normalized_current = normalize_stock_data(current_stock_data)
    normalized_last = normalize_stock_data(LAST_STOCK_DATA)

    # Check if stock data has genuinely changed or if it's the first run
    if LAST_STOCK_DATA is None or normalized_current != normalized_last:
        channel = bot.get_channel(AUTOSTOCK_CHANNEL_ID)
        if channel:
            embed = create_stock_embed(current_stock_data, title="New Stock Update!")
            try:
                await channel.send(embed=embed)
                print(f"Autostock: New stock detected and sent to channel {channel.name} ({channel.id}).")

                # Log the stock change
                stock_time = datetime.now()
                # Get seed names for logging
                seed_names = [item['name'] for item in current_stock_data if item.get('category', '').lower() == 'seeds' and 'name' in item]
                seeds_in_stock_str = ", ".join(seed_names) if seed_names else "No seeds in stock"
                STOCK_LOGS.append({'time': stock_time, 'seeds_in_stock': seeds_in_stock_str})

                # Keep only the last 10 logs (or adjust as needed)
                if len(STOCK_LOGS) > 10:
                    STOCK_LOGS.pop(0)

            except discord.Forbidden:
                print(f"Autostock: Bot does not have permission to send messages in channel {channel.name} ({channel.id}).")
            except Exception as e:
                print(f"Autostock: An error occurred while sending embed: {e}")
        else:
            print(f"Autostock: Configured channel with ID {AUTOSTOCK_CHANNEL_ID} not found or accessible.")

        LAST_STOCK_DATA = current_stock_data # Update the last known stock data

@autostock_checker.before_loop
async def before_autostock_checker():
    """Waits for the bot to be ready before starting the autostock loop."""
    await bot.wait_until_ready() # Ensures bot is connected before fetching data

@bot.command(name="restocklogs")
async def restock_logs(ctx):
    """
    Displays the logs of past stock changes.
    Usage: !restocklogs
    """
    if not STOCK_LOGS:
        await ctx.send("No stock logs available yet.")
        return

    embed = discord.Embed(
        title="Recent Stock Change Logs",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="GrowAGarden Bot")

    # Display logs in reverse order (most recent first)
    for log in reversed(STOCK_LOGS):
        time_str = log['time'].strftime("%Y-%m-%d %H:%M:%S UTC")
        embed.add_field(
            name=f"Stock changed at {time_str}",
            value=f"Seeds in stock: {log['seeds_in_stock']}",
            inline=False
        )
    await ctx.send(embed=embed)


# --- Moderation Commands ---

@bot.command(name="ban")
@commands.has_permissions(ban_members=True) # Requires "Ban Members" permission
@commands.bot_has_permissions(ban_members=True) # Bot must also have "Ban Members" permission
async def ban_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Bans a member from the server.
    Usage: !ban <@user> [reason]
    """
    if member == ctx.author:
        await ctx.send("You cannot ban yourself.")
        return
    if member == bot.user:
        await ctx.send("I cannot ban myself.")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot ban someone with an equal or higher role than yourself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("I cannot ban this user as their role is equal to or higher than my top role.")
        return

    try:
        await member.ban(reason=reason)
        await ctx.send(f"Banned **{member.display_name}** for: `{reason}`")
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban this user. Make sure my role is higher than theirs and I have 'Ban Members' permission.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to ban: {e}")

@bot.command(name="kick")
@commands.has_permissions(kick_members=True) # Requires "Kick Members" permission
@commands.bot_has_permissions(kick_members=True) # Bot must also have "Kick Members" permission
async def kick_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Kicks a member from the server.
    Usage: !kick <@user> [reason]
    """
    if member == ctx.author:
        await ctx.send("You cannot kick yourself.")
        return
    if member == bot.user:
        await ctx.send("I cannot kick myself.")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot kick someone with an equal or higher role than yourself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("I cannot kick this user as their role is equal to or higher than my top role.")
        return

    try:
        await member.kick(reason=reason)
        await ctx.send(f"Kicked **{member.display_name}** for: `{reason}`")
    except discord.Forbidden:
        await ctx.send("I don't have permission to kick this user. Make sure my role is higher than theirs and I have 'Kick Members' permission.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to kick: {e}")

@bot.command(name="mute")
@commands.has_permissions(manage_roles=True) # Requires "Manage Roles" permission
@commands.bot_has_permissions(manage_roles=True) # Bot must also have "Manage Roles" permission
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
        await ctx.send("Error: 'Muted' role not found. Please create a role named 'Muted' with no permissions and try again.")
        return

    if muted_role in member.roles:
        await ctx.send(f"**{member.display_name}** is already muted.")
        return

    if member == ctx.author:
        await ctx.send("You cannot mute yourself.")
        return
    if member == bot.user:
        await ctx.send("I cannot mute myself.")
        return
    if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You cannot mute someone with an equal or higher role than yourself.")
        return
    if ctx.guild.me.top_role <= member.top_role:
        await ctx.send("I cannot mute this user as their role is equal to or higher than my top role.")
        return

    try:
        await member.add_roles(muted_role, reason=reason)
        mute_message = f"Muted **{member.display_name}** for: `{reason}`"
        await ctx.send(mute_message)

        if duration_minutes > 0:
            await ctx.send(f"This mute will last for {duration_minutes} minutes.")
            await asyncio.sleep(duration_minutes * 60)
            # After duration, check if user is still muted and unmute
            if muted_role in member.roles:
                await member.remove_roles(muted_role, reason="Mute duration expired")
                await ctx.send(f"Unmuted **{member.display_name}** (mute duration expired).")
            else:
                print(f"{member.display_name} was manually unmuted before duration expired.")

    except discord.Forbidden:
        await ctx.send("I don't have permission to manage roles. Make sure my role is higher than the 'Muted' role and the user's role.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to mute: {e}")


@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True) # Requires "Manage Roles" permission
@commands.bot_has_permissions(manage_roles=True) # Bot must also have "Manage Roles" permission
async def unmute_command(ctx, member: discord.Member):
    """
    Unmutes a member by removing the 'Muted' role.
    Usage: !unmute <@user>
    """
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

    if not muted_role:
        await ctx.send("Error: 'Muted' role not found. Please create a role named 'Muted'.")
        return

    if muted_role not in member.roles:
        await ctx.send(f"**{member.display_name}** is not muted.")
        return

    try:
        await member.remove_roles(muted_role, reason="Unmuted by moderator")
        await ctx.send(f"Unmuted **{member.display_name}**.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to manage roles. Make sure my role is higher than the 'Muted' role.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to unmute: {e}")

@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True) # Requires "Manage Channels" permission
@commands.bot_has_permissions(manage_channels=True) # Bot must also have "Manage Channels" permission
async def slowmode_command(ctx, seconds: int):
    """
    Sets slowmode for the current channel.
    Usage: !slowmode <seconds> (0 to disable)
    """
    if seconds < 0 or seconds > 21600: # Discord's limit is 6 hours (21600 seconds)
        await ctx.send("Slowmode duration must be between 0 and 21600 seconds.")
        return

    try:
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send("Slowmode has been disabled in this channel.")
        else:
            await ctx.send(f"Slowmode set to `{seconds}` seconds in this channel.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to manage channels.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to set slowmode: {e}")

@bot.command(name="clear", aliases=["purge"])
@commands.has_permissions(manage_messages=True) # Requires "Manage Messages" permission
@commands.bot_has_permissions(manage_messages=True) # Bot must also have "Manage Messages" permission
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
        # Send a confirmation message that deletes itself after a few seconds
        await ctx.send(f"Successfully deleted `{len(deleted) - 1}` messages.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("I don't have permission to manage messages in this channel.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to clear messages: {e} (Messages older than 14 days cannot be bulk deleted).")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")


# --- Run the Bot ---
# Get the bot token from an environment variable (e.g., DISCORD_TOKEN in Railway)
# This is the correct way to retrieve your token when deploying.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if DISCORD_TOKEN is None:
    print("\n\n!!! CRITICAL ERROR: DISCORD_TOKEN environment variable is not set. !!!")
    print("Please ensure you have set the 'DISCORD_TOKEN' environment variable in Railway.")
    print("The bot cannot start without a token.")
    exit(1) # Exit the script if no token is found

try:
    bot.run(DISCORD_TOKEN)
except discord.LoginFailure:
    print("\n\n!!! LOGIN FAILED: Invalid token or connection issue. !!!")
    print("Please check your DISCORD_TOKEN environment variable in Railway. It might be incorrect or expired.")
    print("If you recently reset your token, make sure you updated it in Railway.")
except discord.HTTPException as e:
    print(f"\n\n!!! HTTP EXCEPTION DURING LOGIN: {e} !!!")
    print("This often indicates a problem with Discord's API or your network connection.")
except Exception as e:
    print(f"\n\n!!! AN UNEXPECTED ERROR OCCURRED DURING BOT STARTUP: {e} !!!")
