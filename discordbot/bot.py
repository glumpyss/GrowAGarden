import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import copy
import os
import time

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

autostock_channel = None
autostock_enabled = False
previous_stock = None
logging_channel = None
start_time = time.time()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    check_stock.start()

@bot.command()
@commands.has_permissions(administrator=True)
async def loggingchannel(ctx):
    guild = ctx.guild
    existing = discord.utils.get(guild.text_channels, name="bot-logs")
    if existing:
        await ctx.send("✅ Logging channel already exists.")
        return
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    try:
        channel = await guild.create_text_channel("bot-logs", overwrites=overwrites)
        global logging_channel
        logging_channel = channel
        await ctx.send("✅ Logging channel created.")
    except Exception as e:
        await ctx.send(f"❌ Failed to create logging channel. Error: {e}")

async def log_error(message):
    global logging_channel
    if logging_channel:
        await logging_channel.send(f"⚠️ Error: {message}")


def format_items(items):
    if not items:
        return "None"
    return "\n".join(f"**{item.get('name', 'Unknown')}**: {item.get('value', 0)}" for item in items)

def create_stock_embed(data, author=None):
    embed = discord.Embed(
        title="🌱 Grow A Garden - Stock",
        color=discord.Color.green()
    )
    embed.add_field(name="Seeds", value=format_items(data.get("seedsStock", [])), inline=True)
    embed.add_field(name="Gear", value=format_items(data.get("gearStock", [])), inline=True)
    embed.add_field(name="Eggs", value=format_items(data.get("eggStock", [])), inline=True)
    embed.add_field(name="Bees", value=format_items(data.get("BeeStock", [])), inline=True)
    embed.add_field(name="Cosmetics", value=format_items(data.get("cosmeticsStock", [])), inline=True)
    embed.add_field(name="Credits", value="Bot by **summer 2000**", inline=True)
    embed.add_field(name="How often does stock change?", value="Every 5 minutes", inline=False)
    if author:
        embed.set_footer(text=f"Requested by {author}", icon_url=author.avatar.url if author.avatar else None)
    return embed

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def seeds(ctx):
    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data.get("success", False):
                        await ctx.send("❌ API returned unsuccessful response.")
                        await log_error("Unsuccessful API response in !seeds.")
                        return
                    embed = create_stock_embed(data, ctx.author)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"❌ Failed to fetch stock. Status code: {response.status}")
                    await log_error(f"Stock fetch failed with status code {response.status}.")
        except Exception as e:
            await ctx.send("❌ An error occurred while fetching stock.")
            await log_error(f"Exception in !seeds: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def autostock(ctx, mode: str):
    global autostock_channel, autostock_enabled
    if mode.lower() == "on":
        autostock_channel = ctx.channel
        autostock_enabled = True
        await ctx.send("✅ Auto stock updates enabled.")
    elif mode.lower() == "off":
        autostock_enabled = False
        await ctx.send("❌ Auto stock updates disabled.")
    else:
        await ctx.send("Usage: `!autostock on` or `!autostock off`")

@tasks.loop(seconds=5)
async def check_stock():
    global previous_stock
    if not autostock_enabled or autostock_channel is None:
        return

    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    new_seed_stock = data.get("seedsStock", [])
                    if previous_stock != new_seed_stock:
                        previous_stock = copy.deepcopy(new_seed_stock)
                        embed = create_stock_embed(data)
                        await autostock_channel.send(embed=embed)
                else:
                    await log_error(f"Auto stock failed with status code {response.status}.")
        except Exception as e:
            await log_error(f"Exception in auto stock check: {e}")

@bot.command()
async def uptime(ctx):
    uptime_seconds = int(time.time() - start_time)
    minutes, seconds = divmod(uptime_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    formatted = f"{days}d {hours}h {minutes}m {seconds}s"
    await ctx.send(f"🕒 Uptime: {formatted}")

# Custom help command
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Help Menu",
        description="Here are the available commands:",
        color=discord.Color.blue()
    )
    embed.add_field(name="!seeds", value="Shows current Grow A Garden stock info. (10s cooldown)", inline=False)
    embed.add_field(name="!autostock on/off", value="Toggle automatic stock updates in this channel. Requires Manage Roles permission.", inline=False)
    embed.add_field(name="!loggingchannel", value="Creates a hidden error logging channel. Requires Administrator.", inline=False)
    embed.add_field(name="!uptime", value="Displays how long the bot has been running.", inline=False)
    embed.set_footer(text=f"Bot by summer 2000")
    await ctx.send(embed=embed)

bot.run(os.getenv("DISCORD_TOKEN"))


