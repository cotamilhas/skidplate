import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import xml.etree.ElementTree as ET
import os
from config import EMBED_COLOR, URL, DEBUG_MODE


class Creations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # TO DO

async def setup(bot):
    await bot.add_cog(Creations(bot))
