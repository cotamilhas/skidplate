import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config import EMBED_COLOR, URL, FULL, HALF, EMPTY

class Karting(commands.Cog):
    A = "b"

async def setup(bot):
    await bot.add_cog(Karting(bot))