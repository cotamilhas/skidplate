import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config import EMBED_COLOR, URL, DEBUG_MODE
import xml.etree.ElementTree as ET


def debug(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    @app_commands.command(name="stats", description="Show server statistics.")
    async def server_stats(self, interaction: discord.Interaction):
        debug("Fetching server stats")
        await interaction.response.defer()

        urls = {
            "Mods": f"{URL}/player_creations.xml?page=1&per_page=0&player_creation_type=CHARACTER&platform=PS3",
            "Karts": f"{URL}/player_creations.xml?page=1&per_page=0&player_creation_type=KART&platform=PS3",
            "Tracks": f"{URL}/player_creations.xml?page=1&per_page=0&player_creation_type=TRACK&platform=PS3"
        }

        stats = {}

        for name, url in urls.items():
            try:
                async with self.session.get(url) as resp:
                    if resp.status != 200:
                        debug(f"HTTP {resp.status} while fetching {name}")
                        stats[name] = "0"
                        continue
                    text = await resp.text()
            except Exception as e:
                debug(f"Request error for {name}: {e}")
                stats[name] = "0"
                continue

            try:
                root = ET.fromstring(text)

                player_creations = root.find('./response/player_creations')
                if player_creations is None:
                    player_creations = root.find('.//player_creations')

                stats[name] = player_creations.get('total', '0') if player_creations is not None else '0'

            except ET.ParseError as e:
                debug(f"XML parse error for {name}: {e}")
                stats[name] = "0"

        embed = discord.Embed(
            title="Server Statistics",
            color=EMBED_COLOR
        )
        
        total_mods = stats.get("Mods", "0")
        total_karts = stats.get("Karts", "0")
        total_tracks = stats.get("Tracks", "0")
        total_creations = str(int(total_mods) + int(total_karts) + int(total_tracks))
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        embed.add_field(name="Total Creations", value=total_creations, inline=False)
        embed.add_field(name="Total Mods", value=total_mods, inline=False)
        embed.add_field(name="Total Karts", value=total_karts, inline=False)
        embed.add_field(name="Total Tracks", value=total_tracks, inline=False)
        
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))
