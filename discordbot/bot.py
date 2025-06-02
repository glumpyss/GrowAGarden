import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import copy

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

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
                    embed = create_stock_embed(data)
                    await autostock_channel.send(embed=embed)

# Moderation commands
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ Kicked {member} for: {reason if reason else 'No reason provided.'}")
    except Exception as e:
        await ctx.send(f"❌ Could not kick {member}. Error: {e}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ Banned {member} for: {reason if reason else 'No reason provided.'}")
    except Exception as e:
        await ctx.send(f"❌ Could not ban {member}. Error: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *, reason=None):
    guild = ctx.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if muted_role is None:
        try:
            muted_role = await guild.create_role(name="Muted", reason="Mute role needed for muting members.")
            for channel in guild.channels:
                await channel.set_permissions(muted_role, speak=False, send_messages=False, add_reactions=False)
        except Exception as e:
            await ctx.send(f"❌ Failed to create 'Muted' role. Error: {e}")
            return
    try:
        await member.add_roles(muted_role, reason=reason)
        await ctx.send(f"✅ Muted {member} for: {reason if reason else 'No reason provided.'}")
    except Exception as e:
        await ctx.send(f"❌ Could not mute {member}. Error: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    guild = ctx.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if muted_role is None:
        await ctx.send("❌ No 'Muted' role found.")
        return
    try:
        await member.remove_roles(muted_role)
        await ctx.send(f"✅ Unmuted {member}.")
    except Exception as e:
        await ctx.send(f"❌ Could not unmute {member}. Error: {e}")

# Custom help command
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Help Menu",
        description="Here are the available commands:",
        color=discord.Color.blue()
    )
    embed.add_field(name="!seeds", value="Shows current Grow A Garden stock info.", inline=False)
    embed.add_field(name="!autostock on/off", value="Toggle automatic stock updates in this channel. Requires Manage Roles permission.", inline=False)
    embed.add_field(name="!kick @user [reason]", value="Kick a member. Requires Kick Members permission.", inline=False)
    embed.add_field(name="!ban @user [reason]", value="Ban a member. Requires Ban Members permission.", inline=False)
    embed.add_field(name="!mute @user [reason]", value="Mute a member. Requires Manage Roles permission.", inline=False)
    embed.add_field(name="!unmute @user", value="Unmute a member. Requires Manage Roles permission.", inline=False)
    embed.set_footer(text=f"Bot by summer 2000")
    await ctx.send(embed=embed)

import os
bot.run(os.getenv("DISCORD_TOKEN"))


