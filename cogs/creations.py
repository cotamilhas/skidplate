import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import xml.etree.ElementTree as ET
from config import EMBED_COLOR, URL, DEBUG_MODE
from config import FULL, HALF, EMPTY


def rating_to_stars(rating: float) -> str:
    try:
        rating = float(rating)
    except:
        return str(rating)
    
    rating = max(0.0, min(5.0, rating))

    full = int(rating)
    half = 1 if (rating - full) >= 0.5 else 0
    empty = 5 - full - half

    return f"{FULL * full}{HALF * half}{EMPTY * empty}"

def debug(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")

class Creations(commands.Cog):
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

    async def fetch_creations(
        self,
        player_creation_type: str,
        per_page: int = 3,
        page: int = 1,
        sort_column: str = "points_today",
        sort_order: str = "desc",
        platform: str = "PS3",
    ) -> list[dict] | None:
        url = (
            f"{URL}/player_creations.xml"
            f"?page={page}&per_page={per_page}"
            f"&sort_column={sort_column}"
            f"&player_creation_type={player_creation_type}"
            f"&platform={platform}&sort_order={sort_order}"
        )

        root = await self.fetch_xml(url)
        if root is None:
            return None

        pc_root = root.find(".//player_creations")
        if pc_root is None:
            debug("player_creations element not found")
            return None

        creations = []
        for elem in pc_root.findall("player_creation"):
            try:
                cid = elem.attrib.get("id")
                name = elem.attrib.get("name", "Unknown")
                username = elem.attrib.get("username", "Unknown")
                points_today = elem.attrib.get("points_today", "0")
                points = elem.attrib.get("points", "0")
                rating = elem.attrib.get("star_rating", "N/A")
                downloads = elem.attrib.get("downloads", "0")
                description = elem.attrib.get("description", "")
                thumbnail = f"{URL}/player_creations/{cid}/preview_image.png" if cid else None

                creations.append({
                    "id": cid,
                    "name": name,
                    "username": username,
                    "points_today": points_today,
                    "points": points,
                    "star_rating": rating,
                    "downloads": downloads,
                    "description": description,
                    "thumbnail": thumbnail
                })
            except Exception as e:
                debug(f"Error parsing player_creation element: {e}")
                continue

        return creations

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
                
            rating_stars = rating_to_stars(rating)

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
        creations = await self.fetch_creations(player_creation_type="CHARACTER", per_page=3, page=1)
        if creations is None:
            await interaction.followup.send("Failed to fetch top mods.")
            return
        await self.send_top_embed(interaction, creations, title="Top Mods — Top 3")

    @app_commands.command(name="topkarts", description="Top 3 most downloaded karts today (PS3).")
    async def topkarts(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.fetch_creations(player_creation_type="KART", per_page=3, page=1)
        if creations is None:
            await interaction.followup.send("Failed to fetch top karts.")
            return
        await self.send_top_embed(interaction, creations, title="Top Karts")

    @app_commands.command(name="toptracks", description="Top 3 most downloaded tracks today (PS3).")
    async def toptracks(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.fetch_creations(player_creation_type="TRACK", per_page=3, page=1)
        if creations is None:
            await interaction.followup.send("Failed to fetch top tracks.")
            return
        await self.send_top_embed(interaction, creations, title="Top Tracks")


async def setup(bot):
    await bot.add_cog(Creations(bot))