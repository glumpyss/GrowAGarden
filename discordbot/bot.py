import os
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json # Import json for explicit JSONDecodeError handling

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

# --- Global Variables for Autostock ---
AUTOSTOCK_ENABLED = False
LAST_STOCK_DATA = None
STOCK_API_URL = "https://growagardenapi.vercel.app/api/stock/GetStock"

# AUTOSTOCK_CHANNEL_ID will be set dynamically when the !autostock on command is used.
AUTOSTOCK_CHANNEL_ID = None

STOCK_LOGS = [] # Stores a history of stock changes

# --- Helper Function for API Calls ---
async def fetch_stock_data():
    """Fetches stock data from the GrowAGarden API."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(STOCK_API_URL) as response:
                print(f"API Response Status: {response.status}")
                print(f"API Response Content-Type: {response.headers.get('Content-Type')}")

                # Raise an exception for bad status codes (4xx or 5xx)
                # This will catch typical HTTP errors
                response.raise_for_status()

                try:
                    # Attempt to parse as JSON
                    json_data = await response.json()
                    print(f"API Response (JSON parsed): {json_data}")
                    return json_data
                except aiohttp.ContentTypeError:
                    # This occurs if the server returns a non-JSON Content-Type, but response.json() was called
                    text_data = await response.text()
                    print(f"API Error: Content-Type is not application/json. Raw text: {text_data}")
                    return None
                except json.JSONDecodeError as json_err:
                    # This occurs if the content is not valid JSON, even if Content-Type is application/json
                    text_data = await response.text()
                    print(f"API Error: JSON decoding failed ({json_err}). Raw text: {text_data}")
                    return None
                except Exception as parse_err:
                    # Catch any other unexpected errors during JSON parsing
                    text_data = await response.text()
                    print(f"API Error: Unexpected parsing error ({parse_err}). Raw text: {text_data}")
                    return None

        except aiohttp.ClientError as e:
            print(f"API Client Error (network/connection issue): {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during API fetch process: {e}")
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
        embed.description = "No stock information available at this time."
        return embed

    # Add fields for each item in stock
    for item in data:
        # Ensure all expected keys exist before accessing to prevent KeyError
        required_keys = ['name', 'category', 'price', 'quantity', 'image']
        # The 'get' method is called here. If 'item' is a string, this will fail.
        if all(key in item for key in required_keys):
            embed.add_field(
                name=f"{item['name']} ({item['category'].capitalize()})",
                value=(f"Price: {item['price']}\n"
                       f"Quantity: {item['quantity']}"),
                inline=True
            )
        else:
            # Log and indicate if an item has incomplete data
            missing_keys = [key for key in required_keys if key not in item]
            print(f"Warning: Item missing expected keys ({missing_keys}) in API response: {item}")
            embed.add_field(
                name="Incomplete Item Data",
                value=f"One or more items in the stock list were missing information. Check bot logs for details.",
                inline=False
            )
            # Only add one such warning field to avoid spam
            break
    return embed

# --- Events ---
@bot.event
async def on_ready():
    """Event that fires when the bot successfully connects to Discord."""
    print(f"Bot logged in as {bot.user.name} (ID: {bot.user.id})")
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
        await ctx.send(f"**Oops!** You're missing an argument. Correct usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"**Invalid input!** One of your arguments was incorrect. Correct usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
    elif isinstance(error, commands.CommandNotFound):
        # We can ignore this error if we don't want to respond to every non-existent command
        pass
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
    else:
        # For any other unhandled errors, log them and notify the user
        print(f"An unhandled error occurred in command '{ctx.command.name}': {error}")
        await ctx.send(f"**An unexpected error occurred:** `{error}`. My apologies! Please try again later or contact an administrator.")

# --- Stock Commands ---

@bot.command(name="seeds")
@commands.cooldown(1, 10, commands.BucketType.channel) # 1 use per 10 seconds per channel
async def get_seeds(ctx):
    """
    Displays current stock information for seeds.
    Usage: !seeds
    """
    try:
        await ctx.send("Fetching seed information... please wait a moment.")
        all_stock_data = await fetch_stock_data()
        if not all_stock_data:
            await ctx.send("Apologies, I couldn't retrieve stock information from the API. It might be down or experiencing issues, or returned no data. Please try again later!")
            return

        seed_data = [item for item in all_stock_data if item.get('category', '').lower() == 'seeds']
        if not seed_data:
            await ctx.send("Currently, there are no seed stock items available.")
            return

        embed = create_stock_embed(seed_data, title="Current Seed Stock")
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in !seeds command: {e}")
        await ctx.send(f"An unexpected error occurred while processing the `!seeds` command: `{e}`")

@bot.command(name="stock")
@commands.cooldown(1, 10, commands.BucketType.channel) # 1 use per 10 seconds per channel
async def get_stock_by_category(ctx, category: str = None):
    """
    Displays current stock information for a specific category.
    Usage: !stock [category] (e.g., !stock seeds)
    Available categories: seeds, eggs, bees, cosmetics, gear
    """
    if category is None:
        await ctx.send("Please specify a category. Available categories: `seeds`, `eggs`, `bees`, `cosmetics`, `gear`.\nExample: `!stock seeds`")
        return

    valid_categories = ['seeds', 'eggs', 'bees', 'cosmetics', 'gear']
    category = category.lower()

    if category not in valid_categories:
        await ctx.send(f"**Invalid category!** Available categories are: {', '.join(valid_categories)}. Please choose one of these.")
        return

    try:
        await ctx.send(f"Fetching {category} stock information... please wait a moment.")
        all_stock_data = await fetch_stock_data()
        if not all_stock_data:
            await ctx.send("Apologies, I couldn't retrieve stock information from the API. It might be down or experiencing issues, or returned no data. Please try again later!")
            return

        filtered_stock_data = [item for item in all_stock_data if item.get('category', '').lower() == category]
        if not filtered_stock_data:
            await ctx.send(f"Currently, there are no `{category}` stock items available.")
            return

        embed = create_stock_embed(filtered_stock_data, title=f"Current {category.capitalize()} Stock")
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in !stock command for category '{category}': {e}")
        await ctx.send(f"An unexpected error occurred while processing the `!stock {category}` command: `{e}`")

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
    # This global declaration must be the first thing in the function if you plan to modify these variables
    global AUTOSTOCK_ENABLED, LAST_STOCK_DATA, AUTOSTOCK_CHANNEL_ID, STOCK_LOGS

    if not AUTOSTOCK_ENABLED or AUTOSTOCK_CHANNEL_ID is None:
        return

    current_stock_data = await fetch_stock_data()

    if current_stock_data is None:
        print("Autostock: Failed to fetch current stock data. Skipping update for this cycle.")
        return # Returns early if data is None

    # Helper to normalize stock data for comparison (order-independent comparison)
    def normalize_stock_data(data):
        if not data:
            return frozenset()
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
                    STOCK_LOGS.pop(0) # Remove the oldest log

                LAST_STOCK_DATA = current_stock_data # Update LAST_STOCK_DATA here AFTER successful processing

            except discord.Forbidden:
                print(f"Autostock: Bot does not have permission to send messages/embeds in channel {channel.name} ({channel.id}). Please check bot permissions!")
            except Exception as e:
                print(f"Autostock: An unexpected error occurred while sending embed: {e}")
        else:
            print(f"Autostock: Configured channel with ID {AUTOSTOCK_CHANNEL_ID} not found or inaccessible. Disabling autostock.")
            AUTOSTOCK_ENABLED = False


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
    embed.set_footer(text="GrowAGarden Bot")

    # Display logs in reverse order (most recent first)
    for log in reversed(STOCK_LOGS):
        time_str = log['time'].strftime("%Y-%m-%d %H:%M:%S UTC")
        embed.add_field(
            name=f"Changed at {time_str}",
            value=f"Seeds in stock: `{log['seeds_in_stock']}`",
            inline=False
        )
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
        await ctx.send(f"Successfully banned **{member.display_name}** for: `{reason}`")
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to ban this user. Make sure my role is higher than theirs and I have the 'Ban Members' permission.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to ban **{member.display_name}**: `{e}`")

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
        await ctx.send(f"Successfully kicked **{member.display_name}** for: `{reason}`")
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
        mute_message = f"Successfully muted **{member.display_name}** for: `{reason}`"
        await ctx.send(mute_message)

        if duration_minutes > 0:
            await ctx.send(f"This mute will last for `{duration_minutes}` minutes.")
            await asyncio.sleep(duration_minutes * 60)
            # After duration, check if user is still muted and unmute
            if muted_role in member.roles: # Ensure they weren't manually unmuted already
                await member.remove_roles(muted_role, reason="Mute duration expired")
                await ctx.send(f"Unmuted **{member.display_name}** (mute duration expired).")
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
        await ctx.send(f"Successfully unmuted **{member.display_name}**.")
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
        if seconds == 0:
            await ctx.send("Slowmode has been **disabled** in this channel.")
        else:
            await ctx.send(f"Slowmode set to `{seconds}` seconds in this channel.")
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
        # Send a confirmation message that deletes itself after a few seconds
        await ctx.send(f"Successfully deleted `{len(deleted) - 1}` message(s).", delete_after=5)
    except discord.Forbidden:
        await ctx.send("I don't have sufficient permissions to manage messages in this channel. Please ensure I have 'Manage Messages' and 'Read Message History'.")
    except discord.HTTPException as e:
        if "messages older than 14 days" in str(e):
             await ctx.send("I cannot delete messages older than 14 days using this command.")
        else:
             await ctx.send(f"An API error occurred while trying to clear messages: `{e}`")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred while trying to clear messages: `{e}`")


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
    print("If you recently reset your token, make sure you updated it in Railway.")
except discord.HTTPException as e:
    print(f"\n!!! HTTP EXCEPTION DURING LOGIN: {e} !!!")
    print("This often indicates a problem with Discord's API or your network connection.")
except Exception as e:
    print(f"\n!!! AN UNEXPECTED ERROR OCCURRED DURING BOT STARTUP: {e} !!!")
