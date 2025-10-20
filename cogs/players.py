import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import xml.etree.ElementTree as ET
import os
from datetime import datetime
from config import EMBED_COLOR, URL, DEBUG_MODE

class Players(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def toDiscordTimestamp(self, isoDate):
        dt = datetime.fromisoformat(isoDate)
        timestamp = int(dt.timestamp())
        return f"<t:{timestamp}:F>"

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

                data = await resp.text()
                if DEBUG_MODE:
                    print(f"[DEBUG] XML Response (Player ID): {data[:200]}...")

                try:
                    root = ET.fromstring(data)
                except ET.ParseError as e:
                    if DEBUG_MODE:
                        print(f"[DEBUG] XML Parse Error: {e}")
                    return None

                playerId = root.find(".//player_id")
                if playerId is not None:
                    if DEBUG_MODE:
                        print(f"[DEBUG] Found playerId: {playerId.text}")
                    return playerId.text
                else:
                    if DEBUG_MODE:
                        print("[DEBUG] playerId not found in XML.")
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

                data = await resp.text()
                if DEBUG_MODE:
                    print(f"[DEBUG] XML Response (Player Info): {data[:200]}...")

                try:
                    root = ET.fromstring(data)
                except ET.ParseError as e:
                    if DEBUG_MODE:
                        print(f"[DEBUG] XML Parse Error: {e}")
                    return None

                playerElem = root.find(".//player")
                if playerElem is not None:
                    if DEBUG_MODE:
                        print(f"[DEBUG] Player attributes: {playerElem.attrib}")
                    return playerElem.attrib
                else:
                    if DEBUG_MODE:
                        print("[DEBUG] Element <player> not found.")
                    return None
                
    async def getPlayerAvatar(self, playerId: str) -> str:
        url = URL + f"/player_avatars/MNR/{playerId}/secondary.png"
        if DEBUG_MODE:
            print(f"[DEBUG] Fetching Player Avatar for ID: {playerId}")
            print(f"[DEBUG] Request URL: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    if DEBUG_MODE:
                        print(f"[DEBUG] HTTP Error {resp.status} while fetching player avatar.")
                    return None

                avatarUrl = str(resp.url)
                if DEBUG_MODE:
                    print(f"[DEBUG] Avatar URL: {avatarUrl}")

                return avatarUrl
            
    async def getPlayerHeadAvatar(self, playerId: str) -> str:
        url = URL + f"/player_avatars/MNR/{playerId}/primary.png"
        if DEBUG_MODE:
            print(f"[DEBUG] Fetching Player Avatar for ID: {playerId}")
            print(f"[DEBUG] Request URL: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    if DEBUG_MODE:
                        print(f"[DEBUG] HTTP Error {resp.status} while fetching player avatar.")
                    return None

                avatarHeadUrl = str(resp.url)
                if DEBUG_MODE:
                    print(f"[DEBUG] Avatar URL: {avatarHeadUrl}")

                return avatarHeadUrl

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

        playerAvatar = await self.getPlayerAvatar(playerId)
        date = playerInfo.get("created_at")
        profileCreationDate = await self.toDiscordTimestamp(date)

        embed = discord.Embed(
            title=f"{playerInfo.get('username', username)}",
            color=EMBED_COLOR,
            description=playerInfo.get("quote", "No description.")
        )

        skillLevel = playerInfo.get("skill_level_id")
        imageSkillLevel = f"img/levels/{skillLevel}.PNG"

        embed.add_field(name="Online Races", value=playerInfo.get("online_races"))
        embed.add_field(name="Online Wins", value=playerInfo.get("online_wins"))
        embed.add_field(name="Rating", value=playerInfo.get("rating"))
        embed.add_field(name="Created at", value=profileCreationDate)

        files = []

        if playerAvatar:
            async with aiohttp.ClientSession() as session:
                async with session.get(playerAvatar) as resp:
                    if resp.status == 200:
                        avatar_bytes = await resp.read()
                        avatar_path = f"temp_avatar_{playerId}.png"
                        with open(avatar_path, "wb") as f:
                            f.write(avatar_bytes)
                        avatar_file = discord.File(avatar_path, filename="avatar.png")
                        embed.set_image(url="attachment://avatar.png")
                        files.append(avatar_file)
                    else:
                        fallback = discord.File("img/secondary.png", filename="secondary.png")
                        embed.set_image(url="attachment://secondary.png")
                        files.append(fallback)
        else:
            fallback = discord.File("img/secondary.png", filename="secondary.png")
            embed.set_image(url="attachment://secondary.png")
            files.append(fallback)

        if os.path.exists(imageSkillLevel):
            skill_file = discord.File(imageSkillLevel, filename=f"{skillLevel}.PNG")
            embed.set_thumbnail(url=f"attachment://{skillLevel}.PNG")
            files.append(skill_file)

        embed.set_footer(text=f"Player ID: {playerId}")

        if DEBUG_MODE:
            print(f"[DEBUG] Sending embed for player {username} with {len(files)} file(s) attached")

        await interaction.followup.send(embed=embed, files=files)

        if os.path.exists(f"temp_avatar_{playerId}.png"):
            os.remove(f"temp_avatar_{playerId}.png")


async def setup(bot):
    await bot.add_cog(Players(bot))
