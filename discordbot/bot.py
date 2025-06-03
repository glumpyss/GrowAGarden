import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import copy
import datetime
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=["!", ";"], intents=intents, help_command=None)

autostock_channel = None
autostock_enabled = False
previous_stock = None
last_update_time = None
restock_log = []
ping_role_id = None
autorole_id = None
log_channel = None
start_time = datetime.datetime.utcnow()

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=".gg/sacrificed"))
    print(f"Logged in as {bot.user}")
    check_stock.start()

@bot.event
async def on_member_join(member):
    if autorole_id:
        role = member.guild.get_role(autorole_id)
        if role:
            await member.add_roles(role, reason="Auto role")

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
    if author:
        embed.set_footer(text=f"Requested by {author}", icon_url=author.avatar.url if author.avatar else None)
    return embed

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def seeds(ctx):
    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data.get("success", False):
                        await ctx.send("❌ API returned unsuccessful response.")
                        return
                    embed = create_stock_embed(data, ctx.author)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"❌ Failed to fetch stock. Status code: {response.status}")
    except Exception as e:
        await ctx.send("❌ Error fetching stock data.")
        if log_channel:
            await log_channel.send(f"❗ **Stock Error:** {e}")

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def stock(ctx, category: str):
    category = category.lower()
    valid = {
        "seeds": "seedsStock",
        "gear": "gearStock",
        "eggs": "eggStock",
        "bees": "BeeStock",
        "cosmetics": "cosmeticsStock"
    }
    if category not in valid:
        await ctx.send("❌ Invalid category. Choose from: seeds, gear, eggs, bees, cosmetics.")
        return

    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get(valid[category], [])
                    embed = discord.Embed(
                        title=f"🌱 Grow A Garden - {category.capitalize()} Stock",
                        description=format_items(items),
                        color=discord.Color.green()
                    )
                    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Failed to fetch stock.")
    except Exception as e:
        await ctx.send("❌ Error fetching stock data.")
        if log_channel:
            await log_channel.send(f"❗ **Stock Category Error:** {e}")

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
        await ctx.send("Usage: !autostock on or !autostock off")

@tasks.loop(seconds=5)
async def check_stock():
    global previous_stock, last_update_time, restock_log
    if not autostock_enabled or autostock_channel is None:
        return

    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    new_seed_stock = data.get("seedsStock", [])
                    if previous_stock != new_seed_stock:
                        previous_stock = copy.deepcopy(new_seed_stock)
                        last_update_time = datetime.datetime.utcnow()
                        restock_log.append((last_update_time.strftime('%Y-%m-%d %H:%M:%S'), [item.get('name', 'Unknown') for item in new_seed_stock]))
                        embed = create_stock_embed(data)
                        msg = ""
                        if ping_role_id:
                            msg = f"<@&{ping_role_id}>"
                        await autostock_channel.send(content=msg, embed=embed)
    except Exception as e:
        if log_channel:
            await log_channel.send(f"❗ **AutoStock Error:** {e}")

@bot.command()
async def lastupdate(ctx):
    if last_update_time:
        await ctx.send(f"🕒 Last stock update: {last_update_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    else:
        await ctx.send("❌ No stock updates recorded yet.")

@bot.command()
async def restocklog(ctx):
    if not restock_log:
        await ctx.send("📭 No restocks logged yet.")
        return
    lines = [f"{time} - {', '.join(items)}" for time, items in restock_log[-5:]]
    await ctx.send("📝 **Recent Restocks:**``\n" + "\n".join``(lines))

@bot.command()
async def uptime(ctx):
    delta = datetime.datetime.utcnow() - start_time
    await ctx.send(f"⏱️ Bot Uptime: ``{str(delta).split('.')[0]}``")

@bot.command()
@commands.has_permissions(administrator=True)
async def loggingchannel(ctx):
    global log_channel
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    log_channel = await ctx.guild.create_text_channel("bot-logs", overwrites=overwrites)
    await ctx.send("📘 Logging channel bot-logs has been created and set.")

@bot.command()
async def weather(ctx):
    url = "https://growagardenapi.vercel.app/api/GetWeather"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    weather = data.get("weather", "Unknown")
                    embed = discord.Embed(
                        title="🌦️ Grow A Garden - Current Weather",
                        description=f"**{weather}**",
                        color=discord.Color.blurple()
                    )
                    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Failed to fetch weather.")
    except Exception as e:
        await ctx.send("❌ Error fetching weather.")
        if log_channel:
            await log_channel.send(f"🌩️ **Weather API Error:** {e}")

@bot.command()
async def faq(ctx):
    embed = discord.Embed(
        title="❓ Grow A Garden FAQ",
        description="Answers to common questions.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Where do I buy seeds?", value="Use the in-game shop near your garden.", inline=False)
    embed.add_field(name="How often does stock change?", value="Every 5 Minutes.", inline=False)
    embed.set_footer(text="Bot by summer 2000")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_roles=True)
async def setpingrole(ctx, role: discord.Role):
    global ping_role_id
    ping_role_id = role.id
    await ctx.send(f"🔔 Ping role set to {role.mention}.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def autorole(ctx, role: discord.Role):
    global autorole_id
    autorole_id = role.id
    await ctx.send(f"👤 Auto-role set to {role.mention} for new members.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Cleared {amount} messages.", delete_after=3)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"🐢 Slowmode set to {seconds} seconds.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ Kicked {member} for: {reason or 'No reason provided.'}")
    except Exception as e:
        await ctx.send(f"❌ Could not kick {member}. Error: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ Banned {member} for: {reason or 'No reason provided.'}")
    except Exception as e:
        await ctx.send(f"❌ Could not ban {member}. Error: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *, reason=None):
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        try:
            muted_role = await ctx.guild.create_role(name="Muted")
            for channel in ctx.guild.channels:
                await channel.set_permissions(muted_role, speak=False, send_messages=False, add_reactions=False)
        except Exception as e:
            await ctx.send(f"❌ Could not create Muted role. Error: {e}")
            return
    await member.add_roles(muted_role, reason=reason)
    await ctx.send(f"🔇 Muted {member}.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(f"🔈 Unmuted {member}.")
    else:
        await ctx.send(f"❌ {member} is not muted.")

# ------- new commands

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! ``{latency}ms``")


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Help Menu",
        description="Here are the available commands:",
        color=discord.Color.blue()
    )
    embed.add_field(name="Grow A Garden", value="``!seeds``, ``!stock [category]``, ``!autostock on/off``, ``!lastupdate``, ``!restocklog``, ``!setpingrole @role``, ``!faq``,``!iteminfo``, ``!weather``", inline=False)
    embed.add_field(name="Moderation", value="```!kick``, ``!ban``, ``!mute``, ``!unmute``, ``!clear [amount]``, ``!slowmode [sec]``, ``!autorole @role``", inline=False)
    embed.add_field(name="Utility", value="``!uptime, ``!loggingchannel``, ``!ping``", inline=False)
    embed.add_field(name="Fun", value="``coming soon``", inline=False)
    embed.set_footer(text="Bot by summer 2000")
    await ctx.send(embed=embed)



# ------------------------------------------------

bot.run(os.getenv("DISCORD_TOKEN"))  
