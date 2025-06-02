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

# Moderation commands

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ {member} has been kicked. Reason: {reason if reason else 'No reason provided.'}")
    except Exception as e:
        await ctx.send(f"❌ Could not kick {member}. Error: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ {member} has been banned. Reason: {reason if reason else 'No reason provided.'}")
    except Exception as e:
        await ctx.send(f"❌ Could not ban {member}. Error: {e}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    try:
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(f"🧹 Deleted {len(deleted)} messages.", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Could not delete messages. Error: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member):
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if role is None:
        # Create Muted role if it doesn't exist
        role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(role, speak=False, send_messages=False, read_message_history=True, read_messages=False)
    await member.add_roles(role)
    await ctx.send(f"🔇 {member} has been muted.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    role = discord.utils.get(ctx.guild.roles, name="Muted")
    if role:
        await member.remove_roles(role)
        await ctx.send(f"🔊 {member} has been unmuted.")
    else:
        await ctx.send("❌ Muted role does not exist.")

# Help command
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="Bot Commands Help",
        color=discord.Color.blue()
    )
    embed.add_field(name="!seeds", value="Show current Grow A Garden stock.", inline=False)
    embed.add_field(name="!autostock on/off", value="Toggle automatic stock updates. Requires Manage Roles permission.", inline=False)
    embed.add_field(name="Moderation Commands:", value="(Require appropriate permissions)", inline=False)
    embed.add_field(name="!kick @user [reason]", value="Kick a user.", inline=False)
    embed.add_field(name="!ban @user [reason]", value="Ban a user.", inline=False)
    embed.add_field(name="!clear <number>", value="Delete recent messages.", inline=False)
    embed.add_field(name="!mute @user", value="Mute a user.", inline=False)
    embed.add_field(name="!unmute @user", value="Unmute a user.", inline=False)
    await ctx.send(embed=embed)

import os
bot.run(os.getenv("DISCORD_TOKEN"))


