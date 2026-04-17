import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config import EMBED_COLOR, URL
from utils import debug, fetch_total_creations, fetch_online_players


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = bot.http_session

    async def cog_unload(self):
        return None

    @app_commands.command(name="stats", description="Show server statistics.")
    async def server_stats(self, interaction: discord.Interaction):
        debug("Fetching server stats")
        await interaction.response.defer()

        creation_types = {
            "Mods": "CHARACTER",
            "Karts": "KART",
            "Tracks": "TRACK"
        }

        stats = {}

        for name, creation_type in creation_types.items():
            stats[name] = await fetch_total_creations(self.session, name, URL, creation_type)

        online_players = await fetch_online_players(self.session, URL)

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