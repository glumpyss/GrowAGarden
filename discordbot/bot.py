import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

autostock_channels = {}  # channel_id -> task

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

def format_items(items):
    if not items:
        return "None"
    return "\n".join(f"**{item.get('name', 'Unknown')}**: {item.get('value', 0)}" for item in items)

async def fetch_stock_embed():
    url = "https://growagardenapi.vercel.app/api/stock/GetStock"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if not data.get("success", False):
                    return None

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
                return embed
            else:
                return None

@bot.command()
async def seeds(ctx):
    embed = await fetch_stock_embed()
    if embed:
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Failed to fetch stock.")

async def send_stock_embed(channel):
    while True:
        embed = await fetch_stock_embed()
        if embed:
            await channel.send(embed=embed)
        await asyncio.sleep(300)  # 5 minutes

@bot.command()
@commands.has_permissions(manage_roles=True)
async def autostock(ctx, mode: str):
    channel_id = ctx.channel.id

    if mode.lower() == "on":
        if channel_id in autostock_channels:
            await ctx.send("⚠️ Auto stock is already enabled in this channel.")
        else:
            task = asyncio.create_task(send_stock_embed(ctx.channel))
            autostock_channels[channel_id] = task
            await ctx.send("✅ Auto stock enabled! You'll get stock updates every 5 minutes here.")

    elif mode.lower() == "off":
        task = autostock_channels.pop(channel_id, None)
        if task:
            task.cancel()
            await ctx.send("🛑 Auto stock disabled.")
        else:
            await ctx.send("⚠️ Auto stock isn't enabled in this channel.")

    else:
        await ctx.send("❌ Usage: `!autostock on` or `!autostock off`")

@autostock.error
async def autostock_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need the **Manage Roles** permission to use this command.")
import os
bot.run(os.getenv("DISCORD_TOKEN"))


