import discord
from discord.ext import commands
from discord import app_commands
import os
from config import EMBED_COLOR, URL, FULL, HALF, EMPTY, SHOW_WIN_RATE
from utils import (
    debug, PlayerDataFetcher, create_basic_embed, prepare_player_avatar_attachment, cleanup_temp_file
)
from ui import add_player_fields_to_embed


class Players(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = bot.http_session
        self.player_fetcher = PlayerDataFetcher(self.session, URL)

    async def cog_unload(self):
        return None

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

        avatar_file, avatar_image_url, temp_avatar_path = await prepare_player_avatar_attachment(
            self.session,
            avatar_url,
            player_id
        )
        files = [avatar_file]
        embed.set_image(url=avatar_image_url)

        if os.path.exists(skill_img_path):
            skill_file = discord.File(skill_img_path, filename=f"{skill_level}.PNG")
            files.append(skill_file)
            embed.set_thumbnail(url=f"attachment://{skill_level}.PNG")

        embed.set_footer(
            text=f"Player ID: {player_id} | Requested by {interaction.user.name}",
            icon_url=interaction.user.avatar.url
        )

        debug(f"Sending embed with {len(files)} file(s)")

        try:
            await interaction.followup.send(embed=embed, files=files)
        finally:
            cleanup_temp_file(temp_avatar_path)
    
    # TODO: LPBK Avatars
    @app_commands.command(name="get_avatar", description="Get a player's avatar by their username.")
    @app_commands.describe(
        username="The username of the player you want to view.",
        type="Which avatar image to fetch."
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Full Avatar", value="secondary"),
        app_commands.Choice(name="Mod Head", value="primary"),
    ])
    async def get_avatar(
        self,
        interaction: discord.Interaction,
        username: str,
        type: app_commands.Choice[str]
    ):
        await interaction.response.defer()

        player_id = await self.player_fetcher.get_player_id(username)
        if not player_id:
            return await interaction.followup.send(f"Could not find player `{username}`.")

        avatar_url = await self.player_fetcher.get_player_avatar(
            player_id,
            primary=(type.value == "primary")
        )
        if not avatar_url:
            return await interaction.followup.send(
                f"Could not fetch {type.value} avatar for player ID `{player_id}`."
            )

        avatar_file, avatar_image_url, temp_avatar_path = await prepare_player_avatar_attachment(
            self.session,
            avatar_url,
            player_id
        )

        try:
            await interaction.followup.send(file=avatar_file)
        finally:
            cleanup_temp_file(temp_avatar_path)


async def setup(bot):
    await bot.add_cog(Players(bot))