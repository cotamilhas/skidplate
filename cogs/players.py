import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import xml.etree.ElementTree as ET
import os
from datetime import datetime
from config import EMBED_COLOR, URL, DEBUG_MODE


def debug(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")

class Players(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    @staticmethod
    def to_discord_timestamp(iso_date: str) -> str:
        dt = datetime.fromisoformat(iso_date)
        return f"<t:{int(dt.timestamp())}:F>"

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

    async def fetch_bytes(self, url: str) -> bytes | None:
        debug(f"GET BYTES: {url}")
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    debug(f"HTTP {resp.status} while fetching bytes")
                    return None
                return await resp.read()
        except Exception as e:
            debug(f"Error loading bytes: {e}")
            return None

    async def get_player_id(self, username: str) -> str | None:
        url = f"{URL}/players/to_id.xml?username={username}"
        root = await self.fetch_xml(url)
        if root is None:
            return None

        node = root.find(".//player_id")
        if node is not None:
            debug(f"Found player ID: {node.text}")
            return node.text

        debug("player_id not found")
        return None

    async def get_player_info(self, player_id: str) -> dict | None:
        url = f"{URL}/players/{player_id}/info.xml"
        root = await self.fetch_xml(url)
        if root is None:
            return None

        player = root.find(".//player")
        if player is not None:
            debug(f"Player info: {player.attrib}")
            return player.attrib

        debug("player element not found")
        return None

    async def get_player_avatar(self, player_id: str, primary: bool = False) -> str | None:
        file = "primary.png" if primary else "secondary.png"
        url = f"{URL}/player_avatars/MNR/{player_id}/{file}"

        debug(f"Avatar URL: {url}")

        async with self.session.get(url) as resp:
            if resp.status == 200:
                return str(resp.url)

        debug("Avatar not found")
        return None

    @app_commands.command(name="player", description="Shows information about a player.")
    @app_commands.describe(username="The username of the player you want to view.")
    async def players(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        player_id = await self.get_player_id(username)
        if not player_id:
            return await interaction.followup.send(f"Could not find player `{username}`.")

        info = await self.get_player_info(player_id)
        if not info:
            return await interaction.followup.send(f"Could not fetch data for player ID `{player_id}`.")

        avatar_url = await self.get_player_avatar(player_id)
        skill_level = info.get("skill_level_id")
        skill_img_path = f"img/levels/{skill_level}.PNG"

        creation_timestamp = self.to_discord_timestamp(info["created_at"])

        embed = discord.Embed(
            title=info.get("username", username),
            description=info.get("quote", "No description."),
            color=EMBED_COLOR
        )

        embed.add_field(name="Online Races", value=info.get("online_races"))
        embed.add_field(name="Online Wins", value=info.get("online_wins"))
        embed.add_field(name="Rating", value=info.get("rating"))
        embed.add_field(name="Longest Drift", value=info.get("longest_drift"))
        embed.add_field(name="Longest Air Time", value=info.get("longest_hang_time"))
        embed.add_field(name="Longest Win Streak", value=info.get("longest_win_streak"))
        embed.add_field(name="Created At", value=creation_timestamp)

        files = []

        if avatar_url:
            avatar_bytes = await self.fetch_bytes(avatar_url)
            if avatar_bytes:
                temp_path = f"temp_avatar_{player_id}.png"
                try:
                    with open(temp_path, "wb") as f:
                        f.write(avatar_bytes)
                    files.append(discord.File(temp_path, filename="avatar.png"))
                    embed.set_image(url="attachment://avatar.png")
                except Exception as e:
                    debug(f"File write error: {e}")

        if not files:
            fallback = discord.File("img/secondary.png", filename="secondary.png")
            files.append(fallback)
            embed.set_image(url="attachment://secondary.png")

        if os.path.exists(skill_img_path):
            skill_file = discord.File(skill_img_path, filename=f"{skill_level}.PNG")
            files.append(skill_file)
            embed.set_thumbnail(url=f"attachment://{skill_level}.PNG")

        embed.set_footer(text=f"Player ID: {player_id}")

        debug(f"Sending embed with {len(files)} file(s)")

        await interaction.followup.send(embed=embed, files=files)

        temp_avatar_path = f"temp_avatar_{player_id}.png"
        if os.path.exists(temp_avatar_path):
            os.remove(temp_avatar_path)


async def setup(bot):
    await bot.add_cog(Players(bot))
