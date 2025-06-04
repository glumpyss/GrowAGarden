import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import copy
import datetime
import os
import random
from typing import Optional

# Bot setup with improved configuration
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
        self.start_time = datetime.datetime.utcnow()

    async def setup_hook(self):
        # Start background tasks
        self.check_stock.start()

bot = GardenBot()

# API interaction
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

# Stock related commands
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

@tasks.loop(seconds=5)
async def check_stock():
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
            bot.last_update_time = datetime.datetime.utcnow()
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

# Add the rest of your commands here (weather, faq, moderation commands, etc.)
# Make sure to implement proper error handling for each

# Run the bot
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("No Discord token found in environment variables")
    bot.run(token)
