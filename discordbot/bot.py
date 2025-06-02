import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

autostock_channels = {}
last_stock = None

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    autostock_checker.start()

@bot.command()
@commands.has_permissions(manage_roles=True)
async def autostock(ctx, mode: str = None):
    if mode == "on":
        autostock_channels[ctx.guild.id] = ctx.channel.id
        await ctx.send("✅ Auto stock updates turned **on** for this channel.")
    elif mode == "off":
        autostock_channels.pop(ctx.guild.id, None)
        await ctx.send("🛑 Auto stock updates turned **off**.")
    else:
        await ctx.send("❓ Usage: `!autostock on` or `!autostock off`")

def format_items(items):
    if not items:
        return "None"
    return "\n".join(f"**{item.get('name', 'Unknown')}**: {item.get('value', 0)}" for item in items)

@tasks.loop(seconds=30)
async def autostock_checker():
    global last_stock
    url = "https://growagardenapi.vercel.app/api/stock/GetStock"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return
                data = await response.json()
                if not data.get("success"):
                    return

                current_stock = str(data.get("seedsStock")) + str(data.get("gearStock")) + str(data.get("eggStock")) + str(data.get("BeeStock")) + str(data.get("cosmeticsStock"))
                if current_stock == last_stock:
                    return  # No change in stock

                last_stock = current_stock

                embed = discord.Embed(
                    title="🌱 Grow A Garden - Stock Update",
                    color=discord.Color.green()
                )
                embed.add_field(name="Seeds", value=format_items(data.get("seedsStock", [])), inline=True)
                embed.add_field(name="Gear", value=format_items(data.get("gearStock", [])), inline=True)
                embed.add_field(name="Eggs", value=format_items(data.get("eggStock", [])), inline=True)
                embed.add_field(name="Bees", value=format_items(data.get("BeeStock", [])), inline=True)
                embed.add_field(name="Cosmetics", value=format_items(data.get("cosmeticsStock", [])), inline=True)
                embed.add_field(name="Credits", value="Bot by **summer 2000**", inline=True)

                for guild_id, channel_id in autostock_channels.items():
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=embed)

        except Exception as e:
            print(f"Error during auto-check: {e}")

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
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ Failed to fetch stock. Status code: {response.status}")
import os
bot.run(os.getenv("DISCORD_TOKEN"))


