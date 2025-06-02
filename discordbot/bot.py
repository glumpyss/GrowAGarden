import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

autostock_channel = None
last_stock = None

def stocks_are_equal(stock1, stock2):
    # Simple comparison of seed stocks (you can expand to other categories)
    return stock1 == stock2

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
    embed.set_footer(text=f"Requested by {author}", icon_url=author.avatar.url if author.avatar else None)
    return embed

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def autostock(ctx, arg=None):
    global autostock_channel, last_stock
    if arg not in ("on", "off"):
        await ctx.send("Usage: `!autostock on` or `!autostock off`")
        return

    if arg == "on":
        autostock_channel = ctx.channel
        last_stock = None  # reset last stock so first update always sends
        autostock_task.start(ctx)
        await ctx.send(f"Autostock enabled in {ctx.channel.mention}")
    else:
        autostock_task.cancel()
        autostock_channel = None
        last_stock = None
        await ctx.send("Autostock disabled.")

@tasks.loop(seconds=5)
async def autostock_task(ctx):
    global last_stock, autostock_channel
    if autostock_channel is None:
        autostock_task.cancel()
        return

    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                await autostock_channel.send(f"❌ Failed to fetch stock. Status code: {response.status}")
                return
            data = await response.json()
            if not data.get("success", False):
                await autostock_channel.send("❌ API returned unsuccessful response.")
                return

            current_seed_stock = data.get("seedsStock", [])
            # Compare last seed stock with current (can add other categories if needed)
            if last_stock is None or not stocks_are_equal(last_stock, current_seed_stock):
                last_stock = current_seed_stock
                embed = create_stock_embed(data, ctx.author)
                await autostock_channel.send(embed=embed)
import os
bot.run(os.getenv("DISCORD_TOKEN"))


