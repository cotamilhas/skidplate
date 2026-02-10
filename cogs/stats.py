import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config import EMBED_COLOR, URL, DEBUG_MODE
import xml.etree.ElementTree as ET
import re


def debug(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    async def fetch_xml(self, url: str) -> ET.Element | None:
        debug(f"GET XML: {url}")
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    debug(f"HTTP {resp.status} while fetching XML")
                    return None
                text = await resp.text()
        except Exception as e:
            debug(f"Request error: {e}")
            return None

        try:
            return ET.fromstring(text)
        except ET.ParseError as e:
            debug(f"XML parse error: {e}")
            return None

    async def fetch_text(self, url: str) -> str | None:
        debug(f"GET TEXT: {url}")
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    debug(f"HTTP {resp.status} while fetching text")
                    return None
                return await resp.text()
        except Exception as e:
            debug(f"Request error: {e}")
            return None

    @app_commands.command(name="stats", description="Show server statistics.")
    async def server_stats(self, interaction: discord.Interaction):
        debug("Fetching server stats")
        await interaction.response.defer()

        urls = {
            "Mods": f"{URL}/player_creations.xml?page=1&per_page=0&player_creation_type=CHARACTER&platform=PS3",
            "Karts": f"{URL}/player_creations.xml?page=1&per_page=0&player_creation_type=KART&platform=PS3",
            "Tracks": f"{URL}/player_creations.xml?page=1&per_page=0&player_creation_type=TRACK&platform=PS3",
        }

        online_players_url = f"{URL}/api/playercounts/sessioncount"
        
        stats = {}

        for name, url in urls.items():
            debug(f"Fetching {name} count")
            root = await self.fetch_xml(url)
            if root is None:
                debug(f"Failed to parse {name} XML")
                stats[name] = "0"
                continue

            player_creations = root.find('.//player_creations')
            if player_creations is not None:
                total = player_creations.get('total', '0')
                stats[name] = total
                debug(f"{name}: {total}")
            else:
                debug(f"player_creations element not found for {name}")
                stats[name] = "0"

        debug(f"Fetching online players from: {online_players_url}")
        online_text = await self.fetch_text(online_players_url)
        
        if online_text is not None:
            online_text = online_text.strip()
            debug(f"Online players raw response: '{online_text}'")
            
            if online_text.isdigit():
                online_players = online_text
            else:
                match = re.search(r"(\d+)", online_text)
                online_players = match.group(1) if match else "0"
                debug(f"Extracted online players: {online_players}")
        else:
            debug("Failed to fetch online players")
            online_players = "0"

        embed = discord.Embed(
            title="Server Statistics",
            color=EMBED_COLOR
        )

        total_mods = stats.get("Mods", "0")
        total_karts = stats.get("Karts", "0")
        total_tracks = stats.get("Tracks", "0")
        total_creations = int(total_mods) + int(total_karts) + int(total_tracks)

        debug(f"Final stats - Mods: {total_mods}, Karts: {total_karts}, Tracks: {total_tracks}, Total: {total_creations}, Online: {online_players}")

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="Players Online", value=online_players, inline=False)
        embed.add_field(name="Total Creations", value=total_creations, inline=False)
        embed.add_field(name="Total Mods", value=total_mods, inline=True)
        embed.add_field(name="Total Karts", value=total_karts, inline=True)
        embed.add_field(name="Total Tracks", value=total_tracks, inline=True)

        embed.set_footer(
            text=f"Requested by {interaction.user.name}",
            icon_url=interaction.user.avatar.url
        )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))