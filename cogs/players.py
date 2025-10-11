import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import xml.etree.ElementTree as ET
import os
from config import EMBED_COLOR, URL, DEBUG_MODE


class Players(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def getPlayerId(self, username: str) -> str:
        url = URL + f"/players/to_id.xml?username={username}"
        if DEBUG_MODE:
            print(f"[DEBUG] Fetching Player ID for username: {username}")
            print(f"[DEBUG] Request URL: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    if DEBUG_MODE:
                        print(f"[DEBUG] HTTP Error {resp.status} while fetching player ID.")
                    return None

                xml_data = await resp.text()
                if DEBUG_MODE:
                    print(f"[DEBUG] XML Response (Player ID): {xml_data[:200]}...")

                try:
                    root = ET.fromstring(xml_data)
                except ET.ParseError as e:
                    if DEBUG_MODE:
                        print(f"[DEBUG] XML Parse Error: {e}")
                    return None

                player_id = root.find(".//player_id")
                if player_id is not None:
                    if DEBUG_MODE:
                        print(f"[DEBUG] Found player_id: {player_id.text}")
                    return player_id.text
                else:
                    if DEBUG_MODE:
                        print("[DEBUG] player_id not found in XML.")
                    return None

    async def getPlayerInfo(self, playerId: str) -> dict:
        url = URL + f"/players/{playerId}/info.xml"
        if DEBUG_MODE:
            print(f"[DEBUG] Fetching Player Info for ID: {playerId}")
            print(f"[DEBUG] Request URL: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    if DEBUG_MODE:
                        print(f"[DEBUG] HTTP Error {resp.status} while fetching player info.")
                    return None

                xml_data = await resp.text()
                if DEBUG_MODE:
                    print(f"[DEBUG] XML Response (Player Info): {xml_data[:200]}...")

                try:
                    root = ET.fromstring(xml_data)
                except ET.ParseError as e:
                    if DEBUG_MODE:
                        print(f"[DEBUG] XML Parse Error: {e}")
                    return None

                player_elem = root.find(".//player")
                if player_elem is not None:
                    if DEBUG_MODE:
                        print(f"[DEBUG] Player attributes: {player_elem.attrib}")
                    return player_elem.attrib
                else:
                    if DEBUG_MODE:
                        print("[DEBUG] Element <player> not found.")
                    return None

    @app_commands.command(name="player", description="Shows information about a player.")
    @app_commands.describe(username="The username of the player you want to view.")
    async def players(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        playerId = await self.getPlayerId(username)
        if not playerId:
            await interaction.followup.send(f"Could not find player `{username}`.")
            return

        playerInfo = await self.getPlayerInfo(playerId)
        if not playerInfo:
            await interaction.followup.send(f"Could not get information for player with ID `{playerId}`.")
            return

        embed = discord.Embed(
            title=f"{playerInfo.get('username', username)}",
            color=EMBED_COLOR,
            description=playerInfo.get("quote", "No description.")
        )

        skillLevel = playerInfo.get("skill_level_id", "N/A")
        imageSkillLevel = f"img/levels/{skillLevel}.PNG"

        if DEBUG_MODE:
            print(f"[DEBUG] Skill Level: {skillLevel}")
            print(f"[DEBUG] Checking if image exists: {imageSkillLevel}")

        
        embed.add_field(name="Online Races", value=playerInfo.get("online_races", "0"))
        embed.add_field(name="Online Wins", value=playerInfo.get("online_wins", "0"))
        embed.add_field(name="Rating", value=playerInfo.get("rating", "N/A"))
        embed.add_field(name="Created at", value=playerInfo.get("created_at", "N/A"))

        embed.set_footer(text=f"Player ID: {playerId}")

        if os.path.exists(imageSkillLevel):
            file = discord.File(imageSkillLevel, filename=f"{skillLevel}.PNG")
            embed.set_thumbnail(url=f"attachment://{skillLevel}.PNG")

            if DEBUG_MODE:
                print(f"[DEBUG] Sending embed + image for player ID {playerId}")
            await interaction.followup.send(embed=embed, file=file)
        else:
            if DEBUG_MODE:
                print(f"[DEBUG] Sending embed (no image) for player ID {playerId}")
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Players(bot))
