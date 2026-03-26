import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
from config import EMBED_COLOR, URL, FULL, HALF, EMPTY, SHOW_WIN_RATE
from utils import (
    debug, PlayerDataFetcher, create_basic_embed
)
from clients import XMLFetcher
from ui import add_player_fields_to_embed


class Players(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.player_fetcher = PlayerDataFetcher(self.session, URL)
        self.xml_fetcher = XMLFetcher(self.session)

    async def cog_unload(self):
        await self.session.close()

    async def fetch_bytes(self, url: str) -> bytes | None:
        return await self.xml_fetcher.fetch_bytes(url)

    @app_commands.command(name="player", description="Shows information about a player.")
    @app_commands.describe(username="The username of the player you want to view.")
    async def players(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        player_id = await self.player_fetcher.get_player_id(username)
        if not player_id:
            return await interaction.followup.send(f"Could not find player `{username}`.")

        info = await self.player_fetcher.get_player_info(player_id)
        if not info:
            return await interaction.followup.send(f"Could not fetch data for player ID `{player_id}`.")

        avatar_url = await self.player_fetcher.get_player_avatar(player_id)
        skill_level = info.get("skill_level_id")
        skill_img_path = f"img/levels/{skill_level}.PNG"

        embed = create_basic_embed(info.get("username", username), EMBED_COLOR)
        embed.description = info.get("quote", "No description.")
        
        add_player_fields_to_embed(embed, info, SHOW_WIN_RATE, FULL, HALF, EMPTY)

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

        embed.set_footer(
            text=f"Player ID: {player_id} | Requested by {interaction.user.name}",
            icon_url=interaction.user.avatar.url
        )

        debug(f"Sending embed with {len(files)} file(s)")

        await interaction.followup.send(embed=embed, files=files)

        temp_avatar_path = f"temp_avatar_{player_id}.png"
        if os.path.exists(temp_avatar_path):
            os.remove(temp_avatar_path)


async def setup(bot):
    await bot.add_cog(Players(bot))