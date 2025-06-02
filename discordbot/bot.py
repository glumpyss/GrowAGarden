import discord
from discord.ext import commands
import aiohttp
import json
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

INVITE_CODE = "CodeZDi43ASDd3XA28Xn13"
WHITELIST_FILE = "whitelisted_guilds.json"

# Load whitelist from file or create empty set
if os.path.exists(WHITELIST_FILE):
    with open(WHITELIST_FILE, "r") as f:
        whitelisted_guilds = set(json.load(f))
else:
    whitelisted_guilds = set()

def save_whitelist():
    with open(WHITELIST_FILE, "w") as f:
        json.dump(list(whitelisted_guilds), f)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def activate(ctx, code: str):
    if code == INVITE_CODE:
        whitelisted_guilds.add(ctx.guild.id)
        save_whitelist()
        await ctx.send("✅ Bot activated for this server!")
    else:
        await ctx.send("❌ Invalid invite code.")

@bot.check
async def globally_block_if_not_activated(ctx):
    if ctx.guild is None:
        return False  # block commands in DMs if you want
    if ctx.command.name == "activate":
        return True  # always allow activate command
    return ctx.guild.id in whitelisted_guilds

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

                def format_items(items):
                    if not items:
                        return "None"
                    return "\n".join(f"**{item.get('name', 'Unknown')}**: {item.get('value', 0)}" for item in items)

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


