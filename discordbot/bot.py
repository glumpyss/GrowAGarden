import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import copy

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

autostock_channel = None
autostock_enabled = False
previous_stock = None

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    check_stock.start()

def format_items(items):
    if not items:
        return "None"
    return "\n".join(f"**{item.get('name', 'Unknown')}**: {item.get('value', 0)}" for item in items)

def create_stock_embed(data, author):
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
async def seeds(ctx):
    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
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
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                new_seed_stock = data.get("seedsStock", [])

                if previous_stock != new_seed_stock:
                    previous_stock = copy.deepcopy(new_seed_stock)
                    embed = create_stock_embed(data, None)
                    await autostock_channel.send(embed=embed)
import os
bot.run(os.getenv("DISCORD_TOKEN"))


