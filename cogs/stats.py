import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import math
from typing import Any, Callable

from utils import *


def build_players_online_embed(
    players: list[dict],
    interaction: discord.Interaction,
    current_page: int,
    total_pages: int,
    total_results: int,
) -> discord.Embed:
    embed = discord.Embed(
        title="Players Online",
        description=f"Total: **{total_results}** | Page: **{current_page}/{total_pages}**",
        color=discord.Color.green(),
    )

    for player in players:
        username = player.get("username")
        user_id = player.get("id")
        presence = rename_presence(player.get("presence"))
        platform = player.get("platform")
        is_rpcn = player.get("IsRpcn")
        rpcn_label = "RPCN" if is_rpcn else "PSN"

        embed.add_field(
            name=f"{username} `{user_id}`",
            value=f"Presence: {presence}\nPlatform: {platform} | Network: {rpcn_label}",
            inline=False,
        )

    embed.set_footer(
        text=f"Requested by: {interaction.user}",
        icon_url=interaction.user.display_avatar.url,
    )
    return embed


def normalize_players_payload(data: Any) -> tuple[list[dict], int]:
    if isinstance(data, list):
        return data, len(data)

    if isinstance(data, dict):
        players = data.get("creations", [])
        return players, data.get("total", len(players))

    return [], 0


class PlayersOnlineView(discord.ui.View):
    def __init__(
        self,
        interaction: discord.Interaction,
        fetch_function: Callable[..., Any],
        fetch_kwargs: dict,
        per_page: int,
        current_page: int,
        total_pages: int,
        total_results: int,
    ) -> None:
        super().__init__(timeout=120)
        self.interaction = interaction
        self.fetch_function = fetch_function
        self.fetch_kwargs = fetch_kwargs
        self.per_page = per_page
        self.current_page = current_page
        self.total_pages = total_pages
        self.total_results = total_results
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.previous_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages

    async def _update_page(self, interaction: discord.Interaction, page: int) -> None:
        data = await asyncio.to_thread(
            self.fetch_function,
            **self.fetch_kwargs,
            page=page,
            per_page=self.per_page,
        )

        if isinstance(data, str):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        players, total_results = normalize_players_payload(data)
        if not players:
            await interaction.edit_original_response(content="No players found.", embed=None, view=None)
            return

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(self.total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_buttons()

        embed = build_players_online_embed(
            players,
            self.interaction,
            self.current_page,
            self.total_pages,
            self.total_results,
        )
        await interaction.edit_original_response(content=None, embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("Only the original user can change pages.", ephemeral=True)
            return

        await interaction.response.defer()
        if self.current_page <= 1:
            return
        await self._update_page(interaction, self.current_page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("Only the original user can change pages.", ephemeral=True)
            return

        await interaction.response.defer()
        if self.current_page >= self.total_pages:
            return
        await self._update_page(interaction, self.current_page + 1)


async def send_paginated_players_online(
    interaction: discord.Interaction,
    fetch_function: Callable,
    fetch_kwargs: dict,
    per_page: int = 10,
) -> None:
    await interaction.response.defer()
    data = await asyncio.to_thread(fetch_function, **fetch_kwargs, page=1, per_page=per_page)

    if isinstance(data, str):
        await interaction.followup.send(data, ephemeral=True)
        return

    players, total_results = normalize_players_payload(data)
    if not players:
        await interaction.followup.send("No players found.", ephemeral=True)
        return

    total_pages = max(1, math.ceil(total_results / per_page))

    embed = build_players_online_embed(players, interaction, 1, total_pages, total_results)
    view = PlayersOnlineView(
        interaction=interaction,
        fetch_function=fetch_function,
        fetch_kwargs=fetch_kwargs,
        per_page=per_page,
        current_page=1,
        total_pages=total_pages,
        total_results=total_results,
    )

    await interaction.followup.send(embed=embed, view=view)


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


    @app_commands.command(name="players_online", description="Get players online count and their presence.")
    @app_commands.describe(is_mnr="Is MNR?")
    async def players_online(self, interaction: discord.Interaction, is_mnr: bool | None = None) -> None:
        await send_paginated_players_online(
            interaction=interaction,
            fetch_function=get_players_online_presence,
            fetch_kwargs={
                "is_mnr": is_mnr,
            },
        )
        
    @app_commands.command(name="server_stats", description="Get the server stats.")
    async def server_stats(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        instance_name, players_online_count, total_players_count, creations_count = await asyncio.gather(
            asyncio.to_thread(get_instance_name),
            asyncio.to_thread(get_players_online_count),
            asyncio.to_thread(get_total_players_count),
            asyncio.to_thread(get_total_creations_count),
        )

        if isinstance(creations_count, str):
            await interaction.followup.send(creations_count, ephemeral=True)
            return

        embed = discord.Embed(
            title=instance_name,
            description=(
                f"Players Online: **{players_online_count}**\n"
                f"Total Players: **{total_players_count}** | Total Creations: **{creations_count.get('totalMNR')}**\n"
                f"Total Mods: **{creations_count.get('totalMods')}**\n"
                f"Total Karts: **{creations_count.get('totalKarts')}**\n"
                f"Total Tracks: **{creations_count.get('totalTracks')}**"
            ),
            color=discord.Color.blue(),
        )
        
        if self.bot.user is not None:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            
        embed.set_footer(
            text=f"Requested by: {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.followup.send(embed=embed)
        

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
