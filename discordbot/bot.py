import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta

# --- Bot Setup ---
intents = discord.Intents.default()
intents.members = True  # Required for moderation commands
intents.message_content = True # Required to read command content

bot = commands.Bot(command_prefix=("!", ":"), intents=intents)

# --- Global Variables for Autostock ---
AUTOSTOCK_ENABLED = False
LAST_STOCK_DATA = None
STOCK_API_URL = "https://growagardenapi.vercel.app/api/stock/GetStock"
AUTOSTOCK_CHANNEL_ID = None  # Set this to the channel ID where autostock updates should be sent
STOCK_LOGS = [] # Stores a history of stock changes

# --- Helper Function for API Calls ---
async def fetch_stock_data():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(STOCK_API_URL) as response:
                response.raise_for_status() # Raise an exception for bad status codes
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error fetching stock data: {e}")
            return None

# --- Helper Function to Create Stock Embed ---
def create_stock_embed(data, title="Current Stock Information"):
    embed = discord.Embed(
        title=title,
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="GrowAGarden Bot")

    if not data:
        embed.description = "No stock information available."
        return embed

    for item in data:
        # Check for necessary keys to avoid KeyError
        if all(key in item for key in ['name', 'category', 'price', 'quantity', 'image']):
            embed.add_field(name=f"{item['name']} ({item['category'].capitalize()})",
                            value=(f"Price: {item['price']}\n"
                                   f"Quantity: {item['quantity']}"),
                            inline=True)
        else:
            print(f"Missing expected keys in item: {item}")
            # Optionally, you can add a field indicating malformed data
            # embed.add_field(name="Malformed Item", value=str(item), inline=True)
    return embed

# --- Events ---
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    autostock_checker.start() # Start the autostock task when the bot is ready

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing arguments. Please check the command usage. Example: `{ctx.prefix}{ctx.command.name} [argument]`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument provided. Please check the command usage.")
    elif isinstance(error, commands.CommandNotFound):
        # We can ignore this error if we don't want to respond to every non-existent command
        pass
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have the necessary permissions to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"I don't have the necessary permissions to perform this action. Please ensure I have: {', '.join(error.missing_permissions)}")
    else:
        print(f"An unhandled error occurred: {error}")
        await ctx.send(f"An error occurred: {error}")

# --- Commands ---

@bot.command(name="seeds")
async def get_seeds(ctx):
    """
    Displays current stock information for seeds.
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
@commands.has_permissions(manage_channels=True) # Example permission check
async def autostock_toggle(ctx, status: str = None):
    """
    Toggles automatic stock updates.
    Usage: !autostock on/off
    """
    global AUTOSTOCK_ENABLED, AUTOSTOCK_CHANNEL_ID

    if status is None:
        await ctx.send(f"Auto-stock is currently {'enabled' if AUTOSTOCK_ENABLED else 'disabled'}.")
        await ctx.send("Please specify `on` or `off` to toggle.")
        return

    status = status.lower()
    if status == "on":
        if AUTOSTOCK_ENABLED:
            await ctx.send("Auto-stock is already enabled.")
            return

        AUTOSTOCK_ENABLED = True
        AUTOSTOCK_CHANNEL_ID = ctx.channel.id # Set the channel to the current channel
        await ctx.send(f"Auto-stock updates are now **enabled** in this channel.")
        # Trigger an immediate check when turned on
        await autostock_checker()
    elif status == "off":
        if not AUTOSTOCK_ENABLED:
            await ctx.send("Auto-stock is already disabled.")
            return
        AUTOSTOCK_ENABLED = False
        await ctx.send("Auto-stock updates are now **disabled**.")
    else:
        await ctx.send("Invalid status. Please use `on` or `off`.")

@tasks.loop(minutes=5)
async def autostock_checker():
    global LAST_STOCK_DATA, AUTOSTOCK_ENABLED, AUTOSTOCK_CHANNEL_ID, STOCK_LOGS

    if not AUTOSTOCK_ENABLED or AUTOSTOCK_CHANNEL_ID is None:
        return

    current_stock_data = await fetch_stock_data()

    if current_stock_data is None:
        print("Autostock: Failed to fetch current stock data.")
        return

    # Convert lists of dictionaries to a sortable/comparable format (e.g., tuples of sorted items)
    # This ensures that the order of items in the API response doesn't trigger a false positive.
    def normalize_stock_data(data):
        if not data:
            return tuple()
        # Sort each item by name, then sort the list of items
        sorted_items = sorted([tuple(sorted(d.items())) for d in data], key=lambda x: x[0])
        return tuple(sorted_items)

    normalized_current = normalize_stock_data(current_stock_data)
    normalized_last = normalize_stock_data(LAST_STOCK_DATA)

    if LAST_STOCK_DATA is None or normalized_current != normalized_last:
        channel = bot.get_channel(AUTOSTOCK_CHANNEL_ID)
        if channel:
            embed = create_stock_embed(current_stock_data, title="New Stock Update!")
            await channel.send(embed=embed)
            print("Autostock: New stock detected and sent.")

            # Log the stock change
            stock_time = datetime.now()
            seed_names = ", ".join([item['name'] for item in current_stock_data if item.get('category', '').lower() == 'seeds'])
            STOCK_LOGS.append({'time': stock_time, 'seeds_in_stock': seed_names if seed_names else "No seeds in stock"})
            # Keep only the last 10 logs for example
            if len(STOCK_LOGS) > 10:
                STOCK_LOGS.pop(0)

        else:
            print(f"Autostock: Channel with ID {AUTOSTOCK_CHANNEL_ID} not found.")

        LAST_STOCK_DATA = current_stock_data # Update the last known stock data

@autostock_checker.before_loop
async def before_autostock_checker():
    await bot.wait_until_ready() # Ensure bot is ready before starting the loop

@bot.command(name="restocklogs")
async def restock_logs(ctx):
    """
    Displays the logs of past stock changes.
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

    for log in reversed(STOCK_LOGS): # Show most recent first
        time_str = log['time'].strftime("%Y-%m-%d %H:%M:%S")
        embed.add_field(
            name=f"Stock changed at {time_str} UTC",
            value=f"Seeds in stock: {log['seeds_in_stock']}",
            inline=False
        )
    await ctx.send(embed=embed)


# --- Moderation Commands ---

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Bans a member from the server.
    Usage: !ban <user> [reason]
    """
    try:
        await member.ban(reason=reason)
        await ctx.send(f"Banned {member.display_name} for: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban this user. Make sure my role is higher than theirs.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to ban: {e}")

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_command(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    """
    Kicks a member from the server.
    Usage: !kick <user> [reason]
    """
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Kicked {member.display_name} for: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to kick this user. Make sure my role is higher than theirs.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to kick: {e}")

@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute_command(ctx, member: discord.Member, duration_minutes: int = 0, *, reason: str = "No reason provided"):
    """
    Mutes a member by assigning a 'Muted' role.
    Usage: !mute <user> [duration_minutes] [reason]
    Duration in minutes. If 0 or omitted, mute is permanent until unmuted.
    """
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

    if not muted_role:
        await ctx.send("Error: 'Muted' role not found. Please create a role named 'Muted' with no permissions.")
        return

    if muted_role in member.roles:
        await ctx.send(f"{member.display_name} is already muted.")
        return

    try:
        await member.add_roles(muted_role, reason=reason)
        await ctx.send(f"Muted {member.display_name} for: {reason}")

        if duration_minutes > 0:
            await ctx.send(f"This mute will last for {duration_minutes} minutes.")
            await asyncio.sleep(duration_minutes * 60)
            if muted_role in member.roles: # Check if they are still muted
                await member.remove_roles(muted_role, reason="Mute duration expired")
                await ctx.send(f"Unmuted {member.display_name} (mute duration expired).")
            else:
                print(f"{member.display_name} was manually unmuted before duration expired.")

    except discord.Forbidden:
        await ctx.send("I don't have permission to manage roles. Make sure my role is higher than the 'Muted' role and the user's role.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to mute: {e}")


@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
async def unmute_command(ctx, member: discord.Member):
    """
    Unmutes a member by removing the 'Muted' role.
    Usage: !unmute <user>
    """
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

    if not muted_role:
        await ctx.send("Error: 'Muted' role not found. Please create a role named 'Muted'.")
        return

    if muted_role not in member.roles:
        await ctx.send(f"{member.display_name} is not muted.")
        return

    try:
        await member.remove_roles(muted_role, reason="Unmuted by moderator")
        await ctx.send(f"Unmuted {member.display_name}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to manage roles. Make sure my role is higher than the 'Muted' role.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to unmute: {e}")

@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
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
            await ctx.send(f"Slowmode set to {seconds} seconds in this channel.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to manage channels.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to set slowmode: {e}")

@bot.command(name="clear", aliases=["purge"])
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int):
    """
    Clears a specified amount of messages from the channel.
    Usage: !clear <amount>
    """
    if amount <= 0:
        await ctx.send("Please specify a positive number of messages to delete.")
        return

    try:
        # Add 1 to amount to delete the command message itself
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Successfully deleted {len(deleted) - 1} messages.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("I don't have permission to manage messages.")
    except discord.HTTPException as e:
        await ctx.send(f"An error occurred while trying to clear messages: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")


# --- Run the Bot ---
# Replace "YOUR_BOT_TOKEN_HERE" with your actual bot token
os.getenv("DISCORD_TOKEN")

