import discord
import os
from dotenv import load_dotenv

load_dotenv()

# Discord Configuration
TOKEN = os.getenv("DISCORD_TOKEN", "")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
EMBED_COLOR = discord.Color.yellow()
INTENTS = discord.Intents.all()

# API Configuration
URL = os.getenv("API_URL", "http://example.com:10050")

# Debug Mode
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Moderator Role ID
MODERATOR_ROLE_ID = int(os.getenv("MODERATOR_ROLE_ID", "0"))

# Star Emojis
USE_EMOJIS = os.getenv("USE_EMOJIS", "true").lower() == "true"

FULL = os.getenv("FULL_EMOJI", "<:full:1234567891234567890>")
HALF = os.getenv("HALF_EMOJI", "<:half:1234567891234567890>")
EMPTY = os.getenv("EMPTY_EMOJI", "<:empty:1234567891234567890>")

# Player Settings
SHOW_WIN_RATE = os.getenv("SHOW_WIN_RATE", "false").lower() == "true"