import discord
import random
import hashlib
import os # Import the os module to access environment variables

# Retrieve the bot token from environment variables.
# It's highly recommended to use environment variables for sensitive information like API tokens.
# Set an environment variable named DISCORD_TOKEN before running the bot.
# Example: export DISCORD_TOKEN='YOUR_ACTUAL_BOT_TOKEN_HERE' (on Linux/macOS)
# Or: $env:DISCORD_TOKEN='YOUR_ACTUAL_BOT_TOKEN_HERE' (on PowerShell)
TOKEN = os.getenv('DISCORD_TOKEN')

# Check if the token was loaded successfully
if TOKEN is None:
    print("Error: DISCORD_TOKEN environment variable not set.")
    print("Please set the DISCORD_TOKEN environment variable with your bot's token.")
    exit(1) # Exit the script if the token is not found

# Set up intents (permissions) for your bot.
# For commands, you usually need at least Message Content, Guilds, and GuildMessages.
# You can enable these in the Discord Developer Portal under your bot's settings -> Bot -> Privileged Gateway Intents.
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.guilds = True           # Required to interact with guilds (servers)
intents.guild_messages = True   # Required to read messages in guilds

# Initialize the bot client
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    """
    Event that fires when the bot successfully connects to Discord.
    """
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

@bot.event
async def on_message(message):
    """
    Event that fires every time a message is sent in a channel the bot can see.
    This is where we'll process commands.
    """
    # Ignore messages sent by the bot itself to prevent infinite loops
    if message.author == bot.user:
        return

    # Convert the message content to lowercase for easier command parsing
    content = message.content.lower()

    # Check if the message starts with the '!ship' command
    if content.startswith('!ship'):
        # Split the message into parts, e.g., "!ship name1 name2 name3"
        parts = message.content.split(' ')

        # The command should have at least 3 parts: '!ship', 'name1', 'name2' (and potentially more names)
        if len(parts) >= 3:
            # Extract all names after the '!ship' command
            names = parts[1:]

            # Combine all names for consistent hashing, ensuring the order doesn't matter
            # Sort the lowercase names alphabetically to ensure the combination is always the same
            sorted_names_lower = sorted([name.lower() for name in names])
            seed_string = "".join(sorted_names_lower)

            # Generate a consistent "shipping" percentage using a hash of the names
            # This ensures that the same group of names always gets the same percentage.
            seed_value = sum(ord(char) for char in seed_string)
            shipping_percentage = seed_value % 101 # Ensures a value between 0 and 100 inclusive

            # Create a fun message based on the percentage
            if shipping_percentage < 20:
                emoji = "💔"
                remark = "Hmm, maybe just friends. This group has some... interesting dynamics."
            elif shipping_percentage < 50:
                emoji = "😐"
                remark = "There's a spark, but it might need some fanning. Teamwork makes the dream work!"
            elif shipping_percentage < 75:
                emoji = "💖"
                remark = "A strong connection! This group could be something special."
            elif shipping_percentage < 90:
                emoji = "💞"
                remark = "Wow! A match made in heaven for this group!"
            else:
                emoji = "❤️‍🔥"
                remark = "Soulmates confirmed for the whole group! Get ready for fireworks!"

            # Construct the list of names for the embed description
            names_display = ' & '.join(names)

            # Create a Discord Embed
            embed = discord.Embed(
                title=f"{emoji} Group Compatibility Report {emoji}", # Title of the embed
                description=f"**{names_display}** are {shipping_percentage}% compatible! {remark}", # Main content
                color=discord.Color.from_rgb(255, 105, 180) # A nice pink color for shipping!
            )

            # Set the footer text
            embed.set_footer(text="made by summers 2000")

            # Send the embed message to the channel
            await message.channel.send(embed=embed)
        else:
            # If the command format is incorrect, send a usage message
            await message.channel.send(
                "Usage: `!ship <name1> <name2> [name3...]` (e.g., `!ship Alice Bob Carol`)"
            )

# Run the bot with your token
bot.run(DISCORD_TOKEN)
