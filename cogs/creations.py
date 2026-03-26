import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config import EMBED_COLOR, URL, FULL, HALF, EMPTY
from utils import (
    create_basic_embed,
    CreationDataFetcher,
)
from ui import (
    add_top_creation_fields_to_embed,
    add_creation_fields_to_embed,
    add_search_result_field,
)


class SearchResultsPaginator(discord.ui.View):
    def __init__(self, creations: list, total_pages: int, current_page: int, search_query: str, interaction_user_id: int, fetcher, player_creation_type: str = "CHARACTER", platform: str = "PS3"):
        super().__init__(timeout=300)
        self.creations = creations
        self.total_pages = total_pages
        self.current_page = current_page
        self.search_query = search_query
        self.interaction_user_id = interaction_user_id
        self.fetcher = fetcher
        self.player_creation_type = player_creation_type
        self.platform = platform
        self.update_buttons()

    def update_buttons(self):
        self.prev_page.disabled = self.current_page <= 1
        self.next_page.disabled = self.current_page >= self.total_pages

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction_user_id:
            await interaction.response.send_message("You are not the one who initiated this search.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_page -= 1
        self.prev_page.disabled = True
        self.next_page.disabled = True
        await interaction.followup.edit_message(interaction.message.id, view=self)
        await self.load_and_display_page(interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_page += 1
        self.prev_page.disabled = True
        self.next_page.disabled = True
        await interaction.followup.edit_message(interaction.message.id, view=self)
        await self.load_and_display_page(interaction)

    async def load_and_display_page(self, interaction: discord.Interaction):
        result = await self.fetcher.search_creations(
            search_query=self.search_query,
            player_creation_type=self.player_creation_type,
            platform=self.platform,
            page=self.current_page
        )

        if result is None or not result.get("creations"):
            await interaction.followup.send("Failed to load page.")
            return

        self.creations = result["creations"]
        self.total_pages = result["total_pages"]
        self.update_buttons()

        embed = discord.Embed(
            title=f"Search Results: {self.search_query}",
            description=f"Page {self.current_page}/{self.total_pages} | Total Results: {result['total']}",
            color=EMBED_COLOR
        )

        for i, creation in enumerate(self.creations, start=1):
            add_search_result_field(embed, creation, i, FULL, HALF, EMPTY)

        embed.set_footer(text="Use the buttons to navigate pages")
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)


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
        add_top_creation_fields_to_embed(embed, creations, FULL, HALF, EMPTY)

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
        creation_type="Type of creation (CHARACTER, KART, TRACK)",
        platform="Platform (PS3, PSV or PSP)"
    )
    @app_commands.choices(
        creation_type=[
            app_commands.Choice(name="CHARACTER", value="CHARACTER"),
            app_commands.Choice(name="KART", value="KART"),
            app_commands.Choice(name="TRACK", value="TRACK"),
        ],
        platform=[
            app_commands.Choice(name="PS3", value="PS3"),
            app_commands.Choice(name="PSP", value="PSP"),
            app_commands.Choice(name="PSV", value="PSV"),
        ],
    )
    async def creation_query(
        self,
        interaction: discord.Interaction,
        search: str,
        creation_type: app_commands.Choice[str],
        platform: app_commands.Choice[str]
    ):
        await interaction.response.defer(ephemeral=True)
        
        if len(search) < 2:
            await interaction.followup.send("Search query must be at least 2 characters long.")
            return

        result = await self.creation_fetcher.search_creations(
            search_query=search,
            player_creation_type=creation_type.value,
            platform=platform.value,
            page=1
        )

        if result is None:
            await interaction.followup.send("Failed to search creations.")
            return

        if not result.get("creations"):
            await interaction.followup.send(f"No creations found for '{search}'.")
            return

        embed = discord.Embed(
            title=f"Search Results: {search}",
            description=f"Page 1/{result['total_pages']} | Total Results: {result['total']}",
            color=EMBED_COLOR
        )

        for i, creation in enumerate(result["creations"], start=1):
            add_search_result_field(embed, creation, i, FULL, HALF, EMPTY)

        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)

        paginator = SearchResultsPaginator(
            creations=result["creations"],
            total_pages=result["total_pages"],
            current_page=1,
            search_query=search,
            interaction_user_id=interaction.user.id,
            fetcher=self.creation_fetcher,
            player_creation_type=creation_type.value,
            platform=platform.value
        )

        await interaction.followup.send(embed=embed, view=paginator, ephemeral=True)
        

async def setup(bot):
    await bot.add_cog(Creations(bot))