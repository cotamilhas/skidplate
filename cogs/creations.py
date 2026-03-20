import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config import EMBED_COLOR, URL, DEBUG_MODE, FULL, HALF, EMPTY
from utils import debug, rating_to_stars, CreationDataFetcher


class Creations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.creation_fetcher = CreationDataFetcher(self.session, URL)

    async def cog_unload(self):
        await self.session.close()

    async def send_top_embed(
        self,
        interaction: discord.Interaction,
        creations: list[dict],
        title: str
    ):
        if not creations:
            await interaction.followup.send("No creations found.")
            return

        embed = discord.Embed(
            title=title,
            color=EMBED_COLOR
        )

        first = creations[0]
        if first.get("thumbnail"):
            embed.set_thumbnail(url=first["thumbnail"])

        for i, c in enumerate(creations, start=1):
            name = c.get("name", "Unknown")
            username = c.get("username", "Unknown")
            points_today = c.get("points_today", "0")
            points = c.get("points", "0")
            rating = c.get("star_rating", "N/A")
            downloads = c.get("downloads", "0")
            desc = c.get("description", "")

            if desc:
                desc = desc.strip()
                short = desc if len(desc) <= 250 else desc[:250].rstrip() + "..."
            else:
                short = "No description provided."
                
            rating_stars = rating_to_stars(rating, FULL, HALF, EMPTY)

            field_value = (
                f"Creator: **{username}**\n"
                f"Points Today: **{points_today}** | Total Points: **{points}**\n"
                f"Rating: **{rating_stars}** | Total Downloads: **{downloads}**\n"
                f"> {short}"
            )

            embed.add_field(
                name=f"#{i} {name}",
                value=field_value,
                inline=False
            )

        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="topmods", description="Top 3 most downloaded mods today (PS3).")
    async def topmods(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.creation_fetcher.fetch_creations(
            player_creation_type="CHARACTER", 
            per_page=3, 
            page=1
        )
        if creations is None:
            await interaction.followup.send("Failed to fetch top mods.")
            return
        await self.send_top_embed(interaction, creations, title="Top Mods — Top 3")

    @app_commands.command(name="topkarts", description="Top 3 most downloaded karts today (PS3).")
    async def topkarts(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.creation_fetcher.fetch_creations(
            player_creation_type="KART", 
            per_page=3, 
            page=1
        )
        if creations is None:
            await interaction.followup.send("Failed to fetch top karts.")
            return
        await self.send_top_embed(interaction, creations, title="Top Karts — Top 3")

    @app_commands.command(name="toptracks", description="Top 3 most downloaded tracks today (PS3).")
    async def toptracks(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.creation_fetcher.fetch_creations(
            player_creation_type="TRACK", 
            per_page=3, 
            page=1
        )
        if creations is None:
            await interaction.followup.send("Failed to fetch top tracks.")
            return
        await self.send_top_embed(interaction, creations, title="Top Tracks — Top 3")


async def setup(bot):
    await bot.add_cog(Creations(bot))