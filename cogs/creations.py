import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import math
from typing import Callable, Any

from config import URL
from utils import *


def build_creations_list_embed(
    creations: list[dict],
    interaction: discord.Interaction,
    current_page: int,
    total_pages: int,
    total_results: int
) -> discord.Embed:
    embed = discord.Embed(
        title="Search Results",
        description=f"Total: **{total_results}** | Page: **{current_page}/{total_pages}**",
        color=discord.Color.blue()
    )

    for i, c in enumerate(creations, start=1):
        id_ = c.get("id")
        name = c.get("name")
        creator = c.get("creatorUsername")
        type_ = rename_creation_type(c.get("type"))
        rating = c.get("rating")
        value = (
            f"Creator: {creator}\n"
            f"Type: {type_} | Rating: {rating}\n"
            f"Total XP: {c.get('points')} | Downloads: {c.get('downloads')} | Views: {c.get('views')}"
        )
        embed.add_field(
            name=f"{name} `{id_}`",
            value=value,
            inline=False
        )

    embed.set_footer(
        text=f"Requested by: {interaction.user}",
        icon_url=interaction.user.display_avatar.url
    )
    return embed


def build_topcreations_embed(top_creations: list[dict], interaction: discord.Interaction, title: str) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        color=discord.Color.gold()
    )

    for rank, creation in enumerate(top_creations, start=1):
        creation_id = creation.get("id")
        name = creation.get("name")
        description = creation.get("description")
        creator = creation.get("creatorUsername")
        rating = creation.get("rating")
        points = creation.get("points")
        downloads = creation.get("downloads")
        views = creation.get("views")

        embed.add_field(
            name=f"#{rank} | {name} `{creation_id}`",
            value=(
                f"By: {creator}\n"
                f"Rating: `{rating}` | XP: `{points}`\n"
                f"Total XP: `{points}` | Downloads: `{downloads}` | Views: `{views}`\n"
                f"Description: _{description}_"
            ),
            inline=False,
        )

    embed.set_footer(
        text=f"Requested by: {interaction.user}",
        icon_url=interaction.user.display_avatar.url,
    )
    return embed


def normalize_creations_payload(data: Any) -> tuple[list[dict], int]:
    if isinstance(data, list):
        return data, len(data)

    if isinstance(data, dict):
        creations = data.get("creations", [])
        return creations, data.get("total", len(creations))

    return [], 0


class CreationListView(discord.ui.View):
    def __init__(
        self,
        interaction: discord.Interaction,
        fetch_function: Callable[..., Any],
        fetch_kwargs: dict,
        per_page: int,
        current_page: int,
        total_pages: int,
        total_results: int,
    ):
        super().__init__(timeout=120)
        self.interaction = interaction
        self.fetch_function = fetch_function
        self.fetch_kwargs = fetch_kwargs
        self.per_page = per_page
        self.current_page = current_page
        self.total_pages = total_pages
        self.total_results = total_results

        self._update_buttons()

    def _update_buttons(self):
        self.previous_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages

    async def _fetch_and_update(self, interaction: discord.Interaction, page: int):
        data = await asyncio.to_thread(
            self.fetch_function,
            **self.fetch_kwargs,
            page=page,
            per_page=self.per_page,
        )

        if isinstance(data, str):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        creations, total_results = normalize_creations_payload(data)
        if not creations:
            await interaction.edit_original_response(content="No creations found.", embed=None, view=None)
            return

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(self.total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_buttons()

        embed = build_creations_list_embed(
            creations,
            self.interaction,
            self.current_page,
            self.total_pages,
            self.total_results,
        )
        await interaction.edit_original_response(content=None, embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("Only the original user can change pages.", ephemeral=True)
            return
        await interaction.response.defer()
        if self.current_page <= 1:
            return
        await self._fetch_and_update(interaction, self.current_page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("Only the original user can change pages.", ephemeral=True)
            return
        await interaction.response.defer()
        if self.current_page >= self.total_pages:
            return
        await self._fetch_and_update(interaction, self.current_page + 1)


async def send_paginated_creation_list(
    interaction: discord.Interaction,
    fetch_function: Callable,
    fetch_kwargs: dict,
    per_page: int = 6
):
    await interaction.response.defer()
    data = await asyncio.to_thread(fetch_function, **fetch_kwargs, page=1, per_page=per_page)

    if isinstance(data, str):
        await interaction.followup.send(data, ephemeral=True)
        return

    creations, total_results = normalize_creations_payload(data)
    if not creations:
        await interaction.followup.send("No creations found.", ephemeral=True)
        return

    total_pages = max(1, math.ceil(total_results / per_page))

    embed = build_creations_list_embed(creations, interaction, 1, total_pages, total_results)
    view = CreationListView(
        interaction=interaction,
        fetch_function=fetch_function,
        fetch_kwargs=fetch_kwargs,
        per_page=per_page,
        current_page=1,
        total_pages=total_pages,
        total_results=total_results,
    )

    await interaction.followup.send(embed=embed, view=view)


class Creation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="creation_id", description="Get a creation's stats by its ID.")
    @app_commands.describe(creation_id="The creation ID to get stats for")
    async def creation_id(self, interaction: discord.Interaction, creation_id: int) -> None:
        if creation_id < 10000:
            await interaction.response.send_message("Error: Creation not found.", ephemeral=True)
            return

        await interaction.response.defer()
                
        creation_stats = await asyncio.to_thread(get_creation_stats, creation_id)
        
        if isinstance(creation_stats, str):
            await interaction.followup.send(creation_stats, ephemeral=True)
            return
        
        embed = discord.Embed(title=f"{creation_stats.get('name')}")
        embed.description = f"By: _{creation_stats.get('creatorUsername')}_"
        embed.set_thumbnail(url=f"{URL}/player_creations/{creation_id}/preview_image.png")
        embed.add_field(name="Description", value=f"> {creation_stats.get('description')}", inline=False)
        
        embed.add_field(name="Rating", value=creation_stats.get("rating"), inline=True)
        embed.add_field(name="Type", value=rename_creation_type(creation_stats.get("type")), inline=True)
        embed.add_field(name="Total XP", value=creation_stats.get("points"), inline=True)
        
        embed.add_field(name="Downloads", value=creation_stats.get("downloads"), inline=True)
        embed.add_field(name="Views", value=creation_stats.get("views"), inline=True)
        
        if creation_stats.get("tags") != None:
            embed.add_field(name="Tags", value=creation_stats.get("tags"), inline=False)
            
        embed.add_field(name="Created", value=convert_datetime_to_discord_date(creation_stats.get("createdAt")), inline=False)
        
        embed.set_footer(text=f"Requested by: {interaction.user}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="creation_query", description="Search creations by name.")
    @app_commands.describe(
        creation_name="Name to search",
        creation_type="Type of creation",
        platform="Platform",
        is_mnr="Is MNR?"
    )
    @app_commands.choices(creation_type=[
        app_commands.Choice(name="Track", value="TRACK"),
        app_commands.Choice(name="Kart", value="KART"),
        app_commands.Choice(name="Mod", value="CHARACTER")
    ])
    @app_commands.choices(platform=[
        app_commands.Choice(name="PS3", value="PS3"),
        app_commands.Choice(name="PSV", value="PSV"),
        app_commands.Choice(name="PSP", value="PSP")
    ])
    async def creation_query(
        self,
        interaction: discord.Interaction,
        creation_name: str,
        creation_type: str | None = None,
        platform: str | None = None,
        is_mnr: bool | None = None,
    ):
        await send_paginated_creation_list(
            interaction,
            fetch_function=get_creations_stats_by_query,
            fetch_kwargs={
                "query": creation_name,
                "creation_type": creation_type,
                "platform": platform,
                "is_mnr": is_mnr,
            }
        )

    @app_commands.command(name="creation_player", description="Search creations by player username.")
    @app_commands.describe(
        username="Player username to search",
        creation_type="Type of creation",
        platform="Platform",
        is_mnr="Is MNR?"
    )
    @app_commands.choices(creation_type=[
            app_commands.Choice(name="Track", value="TRACK"),
            app_commands.Choice(name="Kart", value="KART"),
            app_commands.Choice(name="Mod", value="CHARACTER")
    ])
    @app_commands.choices(platform=[
            app_commands.Choice(name="PS3", value="PS3"),
            app_commands.Choice(name="PSV", value="PSV"),
            app_commands.Choice(name="PSP", value="PSP")
    ])
    async def creation_player(
        self,
        interaction: discord.Interaction,
        username: str,
        creation_type: str | None = None,
        platform: str | None = None,
        is_mnr: bool | None = None,
    ):
        await send_paginated_creation_list(
            interaction,
            fetch_function=get_creations_stats_by_username,
            fetch_kwargs={
                "username": username,
                "creation_type": creation_type,
                "platform": platform,
                "is_mnr": is_mnr,
            }
        )

    @app_commands.command(name="topmods", description="Get the top mods.")
    async def topmods(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer()
        top_mods = await asyncio.to_thread(get_topmods)

        if isinstance(top_mods, str):
            await interaction.followup.send(top_mods, ephemeral=True)
            return

        embed = build_topcreations_embed(top_mods, interaction, title="Top Mods")
        embed.set_thumbnail(url=f"{URL}/player_creations/{top_mods[0].get('id')}/preview_image.png")
        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="topkarts", description="Get the top karts.")
    async def topkarts(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer()
        top_karts = await asyncio.to_thread(get_topkarts)

        if isinstance(top_karts, str):
            await interaction.followup.send(top_karts, ephemeral=True)
            return

        embed = build_topcreations_embed(top_karts, interaction, title="Top Karts")
        embed.set_thumbnail(url=f"{URL}/player_creations/{top_karts[0].get('id')}/preview_image.png")
        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="toptracks", description="Get the top tracks.")
    async def toptracks(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer()
        top_tracks = await asyncio.to_thread(get_toptracks)

        if isinstance(top_tracks, str):
            await interaction.followup.send(top_tracks, ephemeral=True)
            return

        embed = build_topcreations_embed(top_tracks, interaction, title="Top Tracks")
        embed.set_thumbnail(url=f"{URL}/player_creations/{top_tracks[0].get('id')}/preview_image.png")
        await interaction.followup.send(embed=embed)
        

async def setup(bot: commands.Bot):
    await bot.add_cog(Creation(bot))
