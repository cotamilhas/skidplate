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

    async def fetch_total(self, name: str, url: str) -> str:
        debug(f"GET {name}: {url}")

        try:
            async with self.session.get(url) as resp:
                debug(f"{name} HTTP status: {resp.status}")

                if resp.status != 200:
                    debug(f"{name} failed with HTTP {resp.status}")
                    return "0"

                text = await resp.text()
                debug(f"{name} response length: {len(text)} chars")

        except Exception as e:
            debug(f"{name} request error: {repr(e)}")
            return "0"

        try:
            root = ET.fromstring(text)
            debug(f"{name} XML parsed successfully")
        except ET.ParseError as e:
            debug(f"{name} XML parse error: {e}")
            return "0"

        player_creations = root.find(".//player_creations")
        if player_creations is None:
            debug(f"{name} <player_creations> element not found")
            return "0"

        total = player_creations.get("total", "0")
        debug(f"{name} total parsed: {total}")
        return total

    async def fetch_online_players(self) -> str:
        url = f"{URL}/api/playercounts/sessioncount"
        debug(f"GET Online Players: {url}")

        try:
            async with self.session.get(url) as resp:
                debug(f"Online players HTTP status: {resp.status}")
                text = (await resp.text()).strip()
                debug(f"Online players raw response: '{text}'")
        except Exception as e:
            debug(f"Online players request error: {repr(e)}")
            return "0"

        if text.isdigit():
            debug("Online players parsed as pure digit")
            return text

        match = re.search(r"(\d+)", text)
        if match:
            debug(f"Online players extracted via regex: {match.group(1)}")
            return match.group(1)

        debug("Online players could not be parsed, defaulting to 0")
        return "0"

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
            stats[name] = await self.fetch_total(name, url)

        online_players = await self.fetch_online_players()

        debug(f"Final stats raw: {stats}")
        debug(f"Online players final value: {online_players}")

        try:
            total_mods = int(stats.get("Mods", "0"))
            total_karts = int(stats.get("Karts", "0"))
            total_tracks = int(stats.get("Tracks", "0"))
            total_creations = total_mods + total_karts + total_tracks
            debug(f"Totals calculated: {total_creations}")
        except Exception as e:
            debug(f"Error calculating totals: {e}")
            total_creations = 0

        embed = discord.Embed(
            title="Server Statistics",
            color=EMBED_COLOR
        )

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

        debug("Sending stats embed")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Stats(bot))