import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import copy
import datetime
from datetime import UTC
import os
import random
from typing import Optional

# Task definition needs to be before the bot class
@tasks.loop(seconds=5)
async def check_stock(bot):
    """Background task to check for stock updates"""
    if not bot.autostock_enabled or not bot.autostock_channel:
        return

    try:
        data = await GardenAPI.fetch_stock()
        if not data:
            return

        new_stock = data.get("seedsStock", [])
        if bot.previous_stock != new_stock:
            bot.previous_stock = copy.deepcopy(new_stock)
            bot.last_update_time = datetime.datetime.now(UTC)
            bot.restock_log.append((
                bot.last_update_time.strftime('%Y-%m-%d %H:%M:%S'),
                [item.get('name', 'Unknown') for item in new_stock]
            ))
            
            embed = create_stock_embed(data)
            content = f"<@&{bot.ping_role_id}>" if bot.ping_role_id else ""
            await bot.autostock_channel.send(content=content, embed=embed)
            
    except Exception as e:
        if bot.log_channel:
            await bot.log_channel.send(f"❗ **AutoStock Error:** {e}")

class GardenBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=["!", ";"], intents=intents, help_command=None)
        
        # Bot state
        self.autostock_channel = None
        self.autostock_enabled = False
        self.previous_stock = None
        self.last_update_time = None
        self.restock_log = []
        self.ping_role_id = None
        self.autorole_id = None
        self.log_channel = None
        self.start_time = datetime.datetime.now(UTC)

    async def setup_hook(self):
        check_stock.start(self)

bot = GardenBot()

# API interaction class
class GardenAPI:
    BASE_URL = "https://growagardenapi.vercel.app/api"
    
    @staticmethod
    async def fetch_stock():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{GardenAPI.BASE_URL}/stock/GetStock") as response:
                if response.status == 200:
                    return await response.json()
                return None

    @staticmethod
    async def fetch_weather():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{GardenAPI.BASE_URL}/GetWeather") as response:
                if response.status == 200:
                    return await response.json()
                return None

# Utility functions
def format_items(items):
    if not items:
        return "No items in stock"
    return "\n".join(f"**{item.get('name', 'Unknown')}**: {item.get('value', 0)}" for item in items)

def create_stock_embed(data, author=None):
    embed = discord.Embed(title="🌱 Grow A Garden - Full Stock", color=discord.Color.green())
    categories = {
        "Seeds": "seedsStock",
        "Gear": "gearStock",
        "Eggs": "eggStock",
        "Bees": "BeeStock",
        "Cosmetics": "cosmeticsStock"
    }
    
    for title, key in categories.items():
        items = data.get(key, [])
        if items:
            embed.add_field(name=title, value=format_items(items), inline=False)
            
    if author:
        embed.set_footer(text=f"Requested by {author}", 
                        icon_url=author.avatar.url if author.avatar else None)
    return embed

# Event handlers
@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=".gg/sacrificed"
        )
    )
    print(f"Logged in as {bot.user}")

@bot.event
async def on_member_join(member):
    if bot.autorole_id:
        role = member.guild.get_role(bot.autorole_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto role")
            except discord.HTTPException:
                if bot.log_channel:
                    await bot.log_channel.send(f"Failed to add auto-role to {member.mention}")

# Commands
@bot.command(name="stock")
@commands.cooldown(1, 5, commands.BucketType.user)
async def stock(ctx, category: Optional[str] = None):
    """Show the current stock, optionally filtered by category"""
    async with ctx.typing():
        data = await GardenAPI.fetch_stock()
        
        if not data or not data.get("success", False):
            await ctx.send("❌ Failed to fetch stock information.")
            return

        categories = {
            "seeds": "seedsStock",
            "gear": "gearStock",
            "eggs": "eggStock",
            "bees": "BeeStock",
            "cosmetics": "cosmeticsStock"
        }

        if category:
            category = category.lower()
            if category not in categories:
                await ctx.send("❌ Invalid category. Choose from: seeds, gear, eggs, bees, cosmetics")
                return
                
            items = data.get(categories[category], [])
            embed = discord.Embed(
                title=f"🌱 Grow A Garden - {category.capitalize()} Stock",
                description=format_items(items),
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Requested by {ctx.author}")
        else:
            embed = create_stock_embed(data, ctx.author)
            
        await ctx.send(embed=embed)

@bot.command(name="seeds")
@commands.cooldown(1, 5, commands.BucketType.user)
async def seeds(ctx):
    """Show current seed stock"""
    await stock(ctx, "seeds")

@bot.command(name="autostock")
@commands.has_permissions(manage_roles=True)
async def autostock(ctx, mode: Optional[str] = None):
    """Configure automatic stock updates"""
    if mode is None:
        status = "enabled" if bot.autostock_enabled else "disabled"
        await ctx.send(f"ℹ️ Auto stock is currently **{status}**")
        return

    mode = mode.lower()
    if mode == "on":
        bot.autostock_channel = ctx.channel
        bot.autostock_enabled = True
        await ctx.send(f"✅ Auto stock updates enabled in {ctx.channel.mention}")
    elif mode == "off":
        bot.autostock_enabled = False
        await ctx.send("❌ Auto stock updates disabled")
    else:
        await ctx.send("Usage: `!autostock on`, `!autostock off`, or `!autostock` to check status")

@bot.command()
async def lastupdate(ctx):
    if bot.last_update_time:
        await ctx.send(f"🕒 Last stock update: {bot.last_update_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    else:
        await ctx.send("❌ No stock updates recorded yet.")

@bot.command()
async def restocklog(ctx):
    if not bot.restock_log:
        await ctx.send("📭 No restocks logged yet.")
        return
    lines = [f"{time} - {', '.join(items)}" for time, items in bot.restock_log[-5:]]
    await ctx.send("📝 **Recent Restocks:**\n" + "\n".join(f"`{line}`" for line in lines))

@bot.command()
async def uptime(ctx):
    delta = datetime.datetime.now(UTC) - bot.start_time
    await ctx.send(f"⏱️ Bot Uptime: ``{str(delta).split('.')[0]}``")

@bot.command()
@commands.has_permissions(administrator=True)
async def loggingchannel(ctx):
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    bot.log_channel = await ctx.guild.create_text_channel("bot-logs", overwrites=overwrites)
    await ctx.send("📘 Logging channel bot-logs has been created and set.")

@bot.command()
async def weather(ctx):
    try:
        data = await GardenAPI.fetch_weather()
        if data:
            weather = data.get("weather", "Unknown")
            embed = discord.Embed(
                title="🌦️ Grow A Garden - Current Weather",
                description=f"**{weather}**",
                color=discord.Color.blurple()
            )
            embed.set_footer(text=f"Requested by {ctx.author}")
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Failed to fetch weather.")
    except Exception as e:
        await ctx.send("❌ Error fetching weather.")
        if bot.log_channel:
            await bot.log_channel.send(f"🌩️ **Weather API Error:** {e}")

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
    bot.ping_role_id = role.id
    await ctx.send(f"🔔 Ping role set to {role.mention}.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def autorole(ctx, role: discord.Role):
    bot.autorole_id = role.id
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
    embed.add_field(
        name="Grow A Garden", 
        value="``!seeds``, ``!stock [category]``, ``!autostock on/off``, ``!lastupdate``, ``!restocklog``, ``!setpingrole @role``, ``!faq``, ``!weather``",
        inline=False
    )
    embed.add_field(
        name="Moderation",
        value="``!kick``, ``!ban``, ``!mute``, ``!unmute``, ``!clear [amount]``, ``!slowmode [sec]``, ``!autorole @role``",
        inline=False
    )
    embed.add_field(
        name="Utility",
        value="``!uptime``, ``!loggingchannel``, ``!ping``",
        inline=False
    )
    embed.add_field(
        name="Fun",
        value="``!8ball [question]``, ``!coinflip``",
        inline=False
    )
    embed.set_footer(text="Bot by summer 2000")
    await ctx.send(embed=embed)

@bot.command(name="8ball")
async def eightball(ctx, *, question: str):
    responses = [
        "It is certain.", "Without a doubt.", "Yes – definitely.",
        "Reply hazy, try again.", "Ask again later.",
        "Don't count on it.", "My reply is no.", "Very doubtful."
    ]
    await ctx.send(f"🎱 Question: *{question}*\nAnswer: {random.choice(responses)}")

@bot.command()
async def coinflip(ctx):
    await ctx.send(f"🪙 You flipped: **{random.choice(['Heads', 'Tails'])}**")

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument. Please check the command usage.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Please wait {error.retry_after:.2f}s before using this command again.")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("No Discord token found in environment variables")
    bot.run(token)

