import discord
import os
import asyncio
import yt_dlp # For downloading and extracting audio from YouTube
import collections # For using deque for the queue

# Suppress warnings from yt-dlp
yt_dlp.utils.bug_reports_message = lambda: ''

# Configuration for yt-dlp to extract audio
YDL_OPTIONS = {
    'format': 'bestaudio/best', # Select the best audio format
    'extractaudio': True,       # Extract audio
    'audioformat': 'mp3',       # Convert to mp3
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', # Output file template
    'restrictfilenames': True,  # Keep filenames simple
    'noplaylist': True,         # Do not download playlists
    'nocheckcertificate': True, # Do not check SSL certificates
    'ignoreerrors': False,      # Do not ignore errors
    'logtostderr': False,       # Do not log to stderr
    'quiet': True,              # Suppress console output
    'no_warnings': True,        # Suppress warnings
    'default_search': 'auto',   # Auto search if no URL is provided
    'source_address': '0.0.0.0' # Bind to a specific address
}

# FFmpeg options for Discord.py audio
# '-before_opus' is important for preventing issues with opus encoding
FFMPEG_OPTIONS = {
    'options': '-vn -filter:a "volume=0.25"', # No video, set volume to 25%
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss 0' # Reconnect options, start from beginning
}

# Retrieve the bot token from environment variables.
TOKEN = os.getenv('DISCORD_TOKEN')

# Check if the token was loaded successfully.
if TOKEN is None:
    print("Error: DISCORD_TOKEN environment variable not set.")
    print("Please set the DISCORD_TOKEN environment variable with your bot's token in your Railway project settings.")
    exit(1)

# Set up intents (permissions) for your bot.
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.voice_states = True # Required for detecting voice channel changes and joining/leaving

# Initialize the bot client
bot = discord.Client(intents=intents)

# A dictionary to store state for each guild (server) the bot is in.
# This allows the bot to manage separate music queues and voice clients for different guilds.
bot_guild_states = {}

class GuildState:
    """
    Represents the state of the bot in a specific guild.
    Manages the voice client, song queue, and playback status.
    """
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.voice_client = None
        self.song_queue = collections.deque() # Use deque for efficient appending and popping
        self.current_song = None
        self.audio_player = None
        self.loop = bot.loop # Get the event loop

        self.play_next_song_event = asyncio.Event()

    async def _play_next_song(self):
        """
        Internal function to play the next song in the queue.
        This runs in a separate task.
        """
        while True:
            # Wait until a song is added to the queue or current song finishes
            await self.play_next_song_event.wait()
            self.play_next_song_event.clear() # Reset the event

            if not self.song_queue:
                self.current_song = None
                continue

            self.current_song = self.song_queue.popleft()
            source_url = self.current_song['url']

            try:
                # Create FFmpeg audio source from the URL
                audio_source = discord.FFmpegPCMAudio(source_url, **FFMPEG_OPTIONS)
                self.voice_client.play(audio_source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.play_next_song_after_callback, e))
                await self.current_song['channel'].send(f"Now playing: **{self.current_song['title']}**")
            except Exception as e:
                print(f"Error playing song {self.current_song['title']}: {e}")
                await self.current_song['channel'].send(f"Could not play **{self.current_song['title']}**. Skipping...")
                self.play_next_song_event.set() # Trigger next song if playback fails

    def play_next_song_after_callback(self, error):
        """
        Callback function for when a song finishes playing.
        Schedules the playing of the next song.
        """
        if error:
            print(f"Player error: {error}")
        self.current_song = None # Clear current song after it finishes
        self.play_next_song_event.set() # Signal that the next song can be played

    async def add_song(self, url, channel, title):
        """Adds a song to the queue."""
        song_info = {'url': url, 'channel': channel, 'title': title}
        self.song_queue.append(song_info)
        if not self.voice_client.is_playing() and not self.voice_client.is_paused():
            self.play_next_song_event.set() # Start playing if nothing is playing

    async def leave_voice(self):
        """Leaves the current voice channel and clears the queue."""
        if self.voice_client and self.voice_client.is_connected():
            self.song_queue.clear() # Clear the queue
            if self.voice_client.is_playing():
                self.voice_client.stop() # Stop current playback
            await self.voice_client.disconnect()
            self.voice_client = None
            self.current_song = None
            self.play_next_song_event.clear() # Ensure event is cleared when leaving

    async def join_voice_channel(self, channel):
        """Connects the bot to a voice channel."""
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()
            # Start the background task for playing songs
            self.loop.create_task(self._play_next_song())
        return self.voice_client

@bot.event
async def on_ready():
    """
    Event that fires when the bot successfully connects to Discord.
    Initializes GuildState for each guild the bot is in.
    """
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    for guild in bot.guilds:
        bot_guild_states[guild.id] = GuildState(bot, guild)
        print(f"Initialized state for guild: {guild.name} (ID: {guild.id})")

@bot.event
async def on_message(message):
    """
    Event that fires every time a message is sent in a channel the bot can see.
    This is where we'll process commands.
    """
    # Ignore messages sent by the bot itself to prevent infinite loops.
    if message.author == bot.user:
        return

    # Get the guild state for the current message's guild.
    # If the bot somehow receives a message from a guild it hasn't initialized, handle it.
    if message.guild is None or message.guild.id not in bot_guild_states:
        print(f"Received message from uninitialized guild or DM: {message.guild.name if message.guild else 'DM'}")
        return

    guild_state = bot_guild_states[message.guild.id]

    content = message.content.lower()

    # --- Ship Command ---
    if content.startswith('!ship'):
        parts = message.content.split(' ')

        if len(parts) >= 3:
            names = parts[1:]
            sorted_names_lower = sorted([name.lower() for name in names])
            seed_string = "".join(sorted_names_lower)
            seed_value = sum(ord(char) for char in seed_string)
            shipping_percentage = seed_value % 101

            if shipping_percentage < 30:
                emoji = "💔"
                remark = "You are just not meant for each other, give up. You're cooked."
            elif shipping_percentage < 60:
                emoji = "😐"
                remark = "There's some potential, you just have to give all your time to each other. You're not cooked."
            elif shipping_percentage < 85:
                emoji = "💖"
                remark = "This is a strong connection, twin, you all are not cooked."
            elif shipping_percentage < 95:
                emoji = "💞"
                remark = "You're just made for each other, twin, you're gonna die together."
            else:
                emoji = "❤️‍🔥"
                remark = "You're just soulmates, you might as well kiss, gang. You're forever."

            names_display = ' & '.join(names)

            embed = discord.Embed(
                title=f"{emoji} Group Compatibility Report {emoji}",
                description=f"**{names_display}** are {shipping_percentage}% compatible! {remark}",
                color=discord.Color.from_rgb(255, 105, 180)
            )
            embed.set_footer(text="made by summers 2000")
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(
                "Usage: `!ship <name1> <name2> [name3...]` (e.g., `!ship Alice Bob Carol`)"
            )

    # --- Music Commands ---

    # !play <query/URL>
    elif content.startswith('!play '):
        if message.author.voice is None or message.author.voice.channel is None:
            await message.channel.send("You need to be in a voice channel to use this command!")
            return

        query = message.content[len('!play '):].strip()
        if not query:
            await message.channel.send("Please provide a song name or URL after `!play`.")
            return

        voice_channel = message.author.voice.channel

        try:
            await guild_state.join_voice_channel(voice_channel)

            if guild_state.voice_client is None:
                await message.channel.send("Could not connect to the voice channel.")
                return

            await message.channel.send(f"Searching for **{query}**...")

            # Use yt-dlp to extract info
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(query, download=False)
                # If a playlist or multiple results, take the first one
                if 'entries' in info:
                    info = info['entries'][0]

                video_url = info['url'] # Direct URL for audio stream
                video_title = info.get('title', 'Unknown Title')

            await guild_state.add_song(video_url, message.channel, video_title)
            await message.channel.send(f"Added **{video_title}** to the queue. Current queue length: {len(guild_state.song_queue) + (1 if guild_state.current_song else 0)}")

        except yt_dlp.DownloadError as e:
            await message.channel.send(f"Could not find or process that song. Error: `{e}`")
        except Exception as e:
            await message.channel.send(f"An error occurred: `{e}`")

    # !skip
    elif content == '!skip':
        if guild_state.voice_client and guild_state.voice_client.is_playing():
            guild_state.voice_client.stop() # This will trigger the `after` callback and play the next song
            await message.channel.send("Skipping current song.")
        else:
            await message.channel.send("No song is currently playing or there are no more songs in the queue.")

    # !stop
    elif content == '!stop':
        if guild_state.voice_client and guild_state.voice_client.is_connected():
            await guild_state.leave_voice()
            await message.channel.send("Stopped playback and left the voice channel.")
        else:
            await message.channel.send("I'm not currently in a voice channel.")

    # !pause
    elif content == '!pause':
        if guild_state.voice_client and guild_state.voice_client.is_playing():
            guild_state.voice_client.pause()
            await message.channel.send("Playback paused.")
        else:
            await message.channel.send("No song is currently playing to pause.")

    # !resume
    elif content == '!resume':
        if guild_state.voice_client and guild_state.voice_client.is_paused():
            guild_state.voice_client.resume()
            await message.channel.send("Playback resumed.")
        else:
            await message.channel.send("No song is currently paused to resume.")

    # !queue
    elif content == '!queue':
        if not guild_state.current_song and not guild_state.song_queue:
            await message.channel.send("The queue is empty.")
            return

        queue_list = []
        if guild_state.current_song:
            queue_list.append(f"**Now Playing:** {guild_state.current_song['title']}")
        for i, song in enumerate(list(guild_state.song_queue)): # Convert deque to list for iteration
            queue_list.append(f"{i+1}. {song['title']}")

        queue_embed = discord.Embed(
            title="Music Queue",
            description="\n".join(queue_list) if queue_list else "Queue is empty.",
            color=discord.Color.blue()
        )
        await message.channel.send(embed=queue_embed)

    # !leave (explicitly leave voice channel)
    elif content == '!leave':
        if guild_state.voice_client and guild_state.voice_client.is_connected():
            await guild_state.leave_voice()
            await message.channel.send("Left the voice channel.")
        else:
            await message.channel.send("I'm not currently in a voice channel.")


# Run the bot with your token.
bot.run(DISCORD_TOKEN)
