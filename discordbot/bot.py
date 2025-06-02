import discord
from discord.ext import commands, tasks
import aiohttp

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

autostock_enabled = False
autostock_channel = None
last_full_stock = None

def stock_changed(old, new):
    return old != new

def format_items(items):
    if not items:
        return "None"
    return "\n".join(f"**{item['name']}**: {item['value']}" for item in items)

def create_embed(data, author):
    embed = discord.Embed(title="🌱 Grow A Garden - Stock", color=discord.Color.green())
    embed.add_field(name="Seeds", value=format_items(data.get("seedsStock", [])), inline=True)
    embed.add_field(name="Gear", value=format_items(data.get("gearStock", [])), inline=True)
    embed.add_field(name="Eggs", value=format_items(data.get("eggStock", [])), inline=True)
    embed.add_field(name="Bees", value=format_items(data.get("BeeStock", [])), inline=True)
    embed.add_field(name="Cosmetics", value=format_items(data.get("cosmeticsStock", [])), inline=True)
    embed.add_field(name="Credits", value="Bot by **summer 2000**", inline=True)
    embed.set_footer(text=f"Requested by {author}", icon_url=author.avatar.url if author.avatar else None)
    return embed

@bot.command()
@commands.has_permissions(manage_roles=True)
async def autostock(ctx, toggle: str = None):
    global autostock_enabled, autostock_channel

    if toggle not in ["on", "off"]:
        await ctx.send("Usage: `!autostock on` or `!autostock off`")
        return

    if toggle == "on":
        autostock_enabled = True
        autostock_channel = ctx.channel
        stock_checker.start()
        await ctx.send("✅ Autostock has been turned **on**.")
    else:
        autostock_enabled = False
        stock_checker.stop()
        await ctx.send("🛑 Autostock has been turned **off**.")

@tasks.loop(seconds=5)
async def stock_checker():
    global last_full_stock, autostock_channel, autostock_enabled

    if not autostock_enabled or autostock_channel is None:
        return

    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return
            data = await response.json()

            if not data.get("success"):
                return

            # Compare entire stock
            current_stock = {
                "seeds": data.get("seedsStock", []),
                "gear": data.get("gearStock", []),
                "eggs": data.get("eggStock", []),
                "bees": data.get("BeeStock", []),
                "cosmetics": data.get("cosmeticsStock", [])
            }

            if last_full_stock != current_stock:
                last_full_stock = current_stock
                embed = create_embed(data, autostock_channel.guild.me)
                await autostock_channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

import os
bot.run(os.getenv("DISCORD_TOKEN"))


