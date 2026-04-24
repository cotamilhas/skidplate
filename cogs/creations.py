import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config import EMBED_COLOR, URL, FULL, HALF, EMPTY
from utils import (
    create_basic_embed,
    CreationDataFetcher,
    debug
)
from ui import (
    add_top_creation_fields_to_embed,
    add_creation_fields_to_embed,
    build_creation_search_results_embed
)
from ui.pagination import BasePaginatorView
import xml.etree.ElementTree as ET


class SearchResultsPaginator(BasePaginatorView):
    page_modal_title = "Go to Search Results Page"

    def __init__(
        self,
        search_query: str,
        interaction_user_id: int,
        requester_name: str,
        requester_avatar_url: str | None,
        fetcher,
        player_creation_type: str = "CHARACTER",
        platform: str = "PS3",
        search_mode: str = "name",
        game: str = None,
        start_page: int = 1
    ):
        super().__init__(interaction_user_id, per_page=10, start_page=start_page)
        self.search_query = search_query
        self.requester_name = requester_name
        self.requester_avatar_url = requester_avatar_url
        self.fetcher = fetcher
        self.player_creation_type = player_creation_type
        self.platform = platform
        self.search_mode = search_mode
        self.game = game

    async def fetch_page(self, page: int):
        if self.search_mode == "player":
            result = await self.fetcher.search_creations_by_player(
                username=self.search_query,
                player_creation_type=self.player_creation_type,
                platform=self.platform,
                page=page,
                game=self.game
            )
        else:
            result = await self.fetcher.search_creations(
                search_query=self.search_query,
                player_creation_type=self.player_creation_type,
                platform=self.platform,
                page=page,
                game=self.game
            )

        if result is None or not result.get("creations"):
            return None, None, None, "Failed to load page."

        items = result.get("creations", [])
        total_pages = result.get("total_pages")
        total = result.get("total")

        if not isinstance(items, list):
            return None, None, None, "Unexpected search response format."
        if not isinstance(total_pages, int):
            total_pages = None
        if not isinstance(total, int):
            total = len(items)

        return items, total, total_pages, None

    async def build_embed(self) -> discord.Embed:
        return build_creation_search_results_embed(
            search_query=self.search_query,
            current_page=self.current_page,
            total_pages=self.total_pages or 1,
            total_results=self.total_items or len(self.items),
            creations=self.items,
            full_emoji=FULL,
            half_emoji=HALF,
            empty_emoji=EMPTY,
            footer_text=f"Requested by {self.requester_name}",
            footer_icon_url=self.requester_avatar_url,
            show_hearts=self.game == "LBPK"
        )


class Creations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = bot.http_session
        self.creation_fetcher = CreationDataFetcher(self.session, URL)

    async def cog_unload(self):
        return None

    async def send_top_embed(
        self,
        interaction: discord.Interaction,
        creations: list[dict],
        title: str,
        show_hearts: bool = False
    ):
        if not creations:
            await interaction.followup.send("No creations found.")
            return

        embed = discord.Embed(
            title=title, 
            color=EMBED_COLOR
        )
        add_top_creation_fields_to_embed(embed, creations, FULL, HALF, EMPTY, show_hearts=show_hearts)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="topmods", description="Top 5 most downloaded mods today (PS3).")
    async def topmods(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.creation_fetcher.fetch_creations(
            player_creation_type="CHARACTER", 
            per_page=5, 
            page=1
        )
        if creations is None:
            await interaction.followup.send("Failed to fetch top mods.")
            return
        await self.send_top_embed(interaction, creations, title="Top Mods — Top 5")

    @app_commands.command(name="topkarts", description="Top 5 most downloaded karts today (PS3).")
    async def topkarts(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.creation_fetcher.fetch_creations(
            player_creation_type="KART", 
            per_page=5, 
            page=1
        )
        if creations is None:
            await interaction.followup.send("Failed to fetch top karts.")
            return
        await self.send_top_embed(interaction, creations, title="Top Karts — Top 5")

    @app_commands.command(name="toptracks", description="Top 5 most downloaded tracks today (PS3).")
    async def toptracks(self, interaction: discord.Interaction):
        await interaction.response.defer()
        creations = await self.creation_fetcher.fetch_creations(
            player_creation_type="TRACK", 
            per_page=5, 
            page=1
        )
        if creations is None:
            await interaction.followup.send("Failed to fetch top tracks.")
            return
        await self.send_top_embed(interaction, creations, title="Top Tracks — Top 5")

    @app_commands.command(name="creation_id", description="Search for a creation by ID")
    @app_commands.describe(id="The creation ID to search for")
    async def creation_id(self, interaction: discord.Interaction, id: int):
        await interaction.response.defer()
        
        if id < 10000:
            await interaction.followup.send("Please provide a valid creation ID.")
            return

        creation_info = await self.creation_fetcher.get_creation_info(id)
        if creation_info is None:
            await interaction.followup.send("Failed to fetch creation.")
            return
        if creation_info == {}:
            await interaction.followup.send(f"Creation with ID {id} not found.")
            return

        embed = create_basic_embed(creation_info.get("name", "Unknown"), EMBED_COLOR)
        embed.description = f"by **{creation_info.get('username', 'Unknown')}**"
        add_creation_fields_to_embed(embed, creation_info, FULL, HALF, EMPTY)
        
        thumbnail_url = f"{URL}player_creations/{id}/preview_image.png"
        embed.set_thumbnail(url=thumbnail_url)
        
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="creation_query", description="Search for creations by name")
    @app_commands.describe(
        search="The name to search for",
        creation_type="Type of creation",
        platform="Platform (PS3, PSV or PSP)",
        game="Game (only applies to tracks)"
    )
    @app_commands.choices(
        creation_type=[
            app_commands.Choice(name="Mods", value="CHARACTER"),
            app_commands.Choice(name="Karts", value="KART"),
            app_commands.Choice(name="Tracks", value="TRACK")
        ],
        platform=[
            app_commands.Choice(name="PS3", value="PS3"),
            app_commands.Choice(name="PSP", value="PSP"),
            app_commands.Choice(name="PSV", value="PSV")
        ],
        game=[
            app_commands.Choice(name="ModNation Racers", value="MNR"),
            app_commands.Choice(name="LBP Karting", value="LBPK")
        ]
    )
    async def creation_query(
        self,
        interaction: discord.Interaction,
        search: str,
        creation_type: app_commands.Choice[str],
        platform: app_commands.Choice[str],
        game: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        if len(search) < 2:
            await interaction.followup.send("Search query must be at least 2 characters long.")
            return

        resolved_game = game.value if game else None

        result = await self.creation_fetcher.search_creations(
            search_query=search,
            player_creation_type=creation_type.value,
            platform=platform.value,
            page=1,
            game=resolved_game
        )

        if result is None:
            await interaction.followup.send("Failed to search creations.")
            return

        if not result.get("creations"):
            await interaction.followup.send(f"No creations found for '{search}'.")
            return

        paginator = SearchResultsPaginator(
            search_query=search,
            interaction_user_id=interaction.user.id,
            requester_name=interaction.user.name,
            requester_avatar_url=interaction.user.display_avatar.url,
            fetcher=self.creation_fetcher,
            player_creation_type=creation_type.value,
            platform=platform.value,
            search_mode="name",
            game=resolved_game,
            start_page=1
        )

        embed, error = await paginator.initialize()
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=paginator, ephemeral=True, wait=True)
        paginator.message = sent_message
        
    @app_commands.command(name="creation_player", description="Search for creations by player name")
    @app_commands.describe(
        username="The name of the creator to search for",
        creation_type="Type of creation (Mods, Karts, Tracks)",
        platform="Platform (PS3, PSV or PSP)",
        game="Game (only applies to tracks)"
    )
    @app_commands.choices(
        creation_type=[
            app_commands.Choice(name="Mods", value="CHARACTER"),
            app_commands.Choice(name="Karts", value="KART"),
            app_commands.Choice(name="Tracks", value="TRACK")
        ],
        platform=[
            app_commands.Choice(name="PS3", value="PS3"),
            app_commands.Choice(name="PSP", value="PSP"),
            app_commands.Choice(name="PSV", value="PSV")
        ],
        game=[
            app_commands.Choice(name="ModNation Racers", value="MNR"),
            app_commands.Choice(name="LBP Karting", value="LBPK")
        ]
    )
    async def creation_player(
        self,
        interaction: discord.Interaction,
        username: str,
        creation_type: app_commands.Choice[str],
        platform: app_commands.Choice[str],
        game: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        if len(username) < 2:
            await interaction.followup.send("Username must be at least 2 characters long.")
            return

        resolved_game = game.value if game else None

        result = await self.creation_fetcher.search_creations_by_player(
            username=username,
            player_creation_type=creation_type.value,
            platform=platform.value,
            page=1,
            game=resolved_game
        )

        if result is None:
            await interaction.followup.send("Failed to search creations.")
            return

        if not result.get("creations"):
            await interaction.followup.send(f"No creations found for '{username}'.")
            return

        paginator = SearchResultsPaginator(
            search_query=username,
            interaction_user_id=interaction.user.id,
            requester_name=interaction.user.name,
            requester_avatar_url=interaction.user.display_avatar.url,
            fetcher=self.creation_fetcher,
            player_creation_type=creation_type.value,
            platform=platform.value,
            search_mode="player",
            game=resolved_game,
            start_page=1
        )

        embed, error = await paginator.initialize()
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=paginator, ephemeral=True, wait=True)
        paginator.message = sent_message
    
    @app_commands.command(name="tophearted", description="Top 5 most hearted LBPK tracks (PS3).")
    async def top_hearted(self, interaction: discord.Interaction):
        await interaction.response.defer()

        url = f"{URL}tracks.xml"
        params = {
            "page": 1,
            "per_page": 5,
            "sort_column": "hearts",
            "sort_order": "desc",
            "platform": "PS3"
        }

        async with self.session.get(url, params=params) as resp:
            if resp.status != 200:
                await interaction.followup.send("Failed to fetch top hearted tracks.")
                return
            data = await resp.text()

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            await interaction.followup.send(f"XML parse error: {e}")
            return

        tracks_elem = root.find(".//player_creations")
        if tracks_elem is None:
            await interaction.followup.send("No track data found.")
            return

        tracks = tracks_elem.findall("player_creation")
        if not tracks:
            await interaction.followup.send("No tracks found.")
            return

        creations = []
        for track in tracks:
            cid = track.attrib.get("id")
            creations.append({
                "id": cid,
                "name": track.attrib.get("name", "Unknown"),
                "username": track.attrib.get("username", "Unknown"),
                "points_today": track.attrib.get("points_today", "0"),
                "points": track.attrib.get("points", "0"),
                "star_rating": track.attrib.get("star_rating", "N/A"),
                "downloads": track.attrib.get("downloads", "0"),
                "description": track.attrib.get("description", ""),
                "hearts": track.attrib.get("hearts", "0"),
                "thumbnail": f"{URL}player_creations/{cid}/preview_image.png" if cid else None,
            })

        await self.send_top_embed(interaction, creations, title="LBPK Tracks - Top 5 Hearted", show_hearts=True)
        
async def setup(bot):
    await bot.add_cog(Creations(bot))