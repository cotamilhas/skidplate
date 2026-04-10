import asyncio
import discord
from typing import TYPE_CHECKING, Any, Optional
from io import BytesIO

from config import EMBED_COLOR
from utils import debug, prepare_player_avatar_attachment, cleanup_temp_file

if TYPE_CHECKING:
    from cogs.moderation import Moderation


CREATION_TYPE_LABELS = {
    0: "Photo",
    1: "Planet",
    2: "Track",
    3: "Item",
    4: "Story",
    5: "Deleted",
    6: "Mod",
    7: "Kart",
}


class ComplaintsPageJumpModal(discord.ui.Modal, title="Go to Complaints Page"):
    page_input = discord.ui.TextInput(
        label="Page",
        placeholder="Enter a page number (e.g. 1)",
        min_length=1,
        max_length=6,
    )

    def __init__(self, view: "ComplaintsPaginator"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.page_input).strip()
        if not raw_value.isdigit():
            await interaction.response.send_message("Please enter a valid page number.", ephemeral=True)
            return

        target_page = int(raw_value)
        await interaction.response.defer(ephemeral=True)
        if self.view._loading:
            return
        self.view._loading = True
        try:
            await self.view.go_to_page(interaction, target_page)
        finally:
            self.view._loading = False


class BanListPageJumpModal(discord.ui.Modal, title="Go to Ban List Page"):
    page_input = discord.ui.TextInput(
        label="Page",
        placeholder="Enter a page number (e.g. 1)",
        min_length=1,
        max_length=6,
    )

    def __init__(self, view: "BanListPaginator"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.page_input).strip()
        if not raw_value.isdigit():
            await interaction.response.send_message("Please enter a valid page number.", ephemeral=True)
            return

        target_page = int(raw_value)
        await interaction.response.defer(ephemeral=True)

        if self.view._loading:
            return

        self.view._loading = True
        try:
            await self.view.go_to_page(interaction, target_page)
        finally:
            self.view._loading = False


class ComplaintsPaginator(discord.ui.View):
    def __init__(
        self,
        moderation_cog: "Moderation",
        interaction_user_id: int,
        moderator_user_id: int,
        endpoint: str,
        mode: str,
        per_page: int = 1,
        start_page: int = 1,
    ):
        super().__init__(timeout=300)
        self.moderation_cog = moderation_cog
        self.interaction_user_id = interaction_user_id
        self.moderator_user_id = moderator_user_id
        self.endpoint = endpoint
        self.mode = mode
        self.per_page = per_page
        self.current_page = max(1, start_page)
        self.total_pages: Optional[int] = None
        self.total_items: Optional[int] = None
        self.items: list[dict[str, Any]] = []
        self.message: Optional[discord.Message] = None
        self.preview_attachment: Optional[discord.File] = None
        self.temp_preview_path: Optional[str] = None
        self._loading = False
        self.update_buttons()

    def _clear_preview_attachment(self):
        cleanup_temp_file(self.temp_preview_path)
        self.temp_preview_path = None
        self.preview_attachment = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction_user_id:
            await interaction.response.send_message("You are not the one who initiated this command.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.prev_page.disabled = self.current_page <= 1
        if self.total_pages is None:
            self.next_page.disabled = False
        else:
            self.next_page.disabled = self.current_page >= self.total_pages

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {
            "page": max(0, page - 1),
            "per_page": self.per_page,
        }
        data, error = await self.moderation_cog.api_request("GET", self.endpoint, self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        total: Optional[int] = None
        items: list[dict[str, Any]] = []

        if isinstance(data, dict) and "items" in data:
            items = data.get("items") or []
            total = data.get("count")
            debug(f"API response for {self.endpoint} page {page}: items={len(items)}, total={total}")
            if not isinstance(total, int):
                total = None
        elif isinstance(data, dict) and "Page" in data:
            items = data.get("Page") or []
            total_val = data.get("Total")
            total = total_val if isinstance(total_val, int) else None
        elif isinstance(data, list):
            items = data
            total = None
        else:
            return None, None, None, "Unexpected API response format."

        total_pages: Optional[int] = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        items.reverse()
        return items, total, total_pages, None

    async def initialize(self) -> tuple[Optional[discord.Embed], Optional[str]]:
        items, total, total_pages, error = await self.fetch_page(self.current_page)
        if error:
            return None, error

        self.items = items or []
        self.total_items = total
        self.total_pages = total_pages
        self.update_buttons()
        return await self.build_embed(), None

    async def go_to_page(self, interaction: discord.Interaction, page: int):
        if page < 1:
            await interaction.followup.send("Page must be 1 or higher.", ephemeral=True)
            return

        items, total, total_pages, error = await self.fetch_page(page)
        if error:
            await interaction.followup.send(f"Failed to fetch page: {error}", ephemeral=True)
            return

        if not items and page > 1:
            await interaction.followup.send("That page has no items.", ephemeral=True)
            return

        self.current_page = page
        self.items = items or []
        self.total_items = total
        self.total_pages = total_pages
        self.update_buttons()

        if self.message is not None:
            embed = await self.build_embed()
            attachments = [self.preview_attachment] if self.preview_attachment else []
            await self.message.edit(embed=embed, view=self, attachments=attachments)

    async def build_embed(self) -> discord.Embed:
        self._clear_preview_attachment()
        if self.mode == "player":
            return await self.build_player_embed()
        return await self.build_creation_embed()

    async def build_player_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="Player Complaints",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=EMBED_COLOR,
        )

        start_index = (self.current_page - 1) * self.per_page
        first_reported_player_id: Optional[int] = None

        for index, item in enumerate(self.items, start=1):
            reporter_id = item.get("UserId")
            reported_id = item.get("PlayerId")
            reason = item.get("Reason", "UNKNOWN")

            reporter_name = await self.moderation_cog.resolve_player_name(reporter_id)
            reported_name = await self.moderation_cog.resolve_player_name(reported_id)

            if first_reported_player_id is None and isinstance(reported_id, int):
                first_reported_player_id = reported_id

            embed.add_field(
                name=f"Complaint #{start_index + index}",
                value=(
                    f"Reporter: **{reporter_name}** (`{reporter_id}`)\n"
                    f"Reported: **{reported_name}** (`{reported_id}`)\n"
                    f"Reason: **{reason}**"
                ),
                inline=False,
            )

        if first_reported_player_id is not None:
            avatar_url = await self.moderation_cog.resolve_player_avatar(first_reported_player_id)
            avatar_file, avatar_thumbnail_url, temp_avatar_path = await prepare_player_avatar_attachment(
                self.moderation_cog.session,
                avatar_url,
                str(first_reported_player_id),
            )
            self.preview_attachment = avatar_file
            self.temp_preview_path = temp_avatar_path
            embed.set_thumbnail(url=avatar_thumbnail_url)

        return embed

    async def build_creation_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="Creation Complaints",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=EMBED_COLOR,
        )

        start_index = (self.current_page - 1) * self.per_page
        first_creation_preview: Optional[str] = None
        first_creation_id: Optional[int] = None

        for index, item in enumerate(self.items, start=1):
            reporter_id = item.get("UserId")
            creator_id = item.get("PlayerId")
            creation_id = item.get("PlayerCreationId")
            reason = item.get("Reason", "UNKNOWN")

            reporter_name = await self.moderation_cog.resolve_player_name(reporter_id)
            creator_name = await self.moderation_cog.resolve_player_name(creator_id)

            creation_name = "Unknown Creation"
            preview_url = None
            if isinstance(creation_id, int):
                creation_info = await self.moderation_cog.resolve_creation_info(creation_id)
                creation_name = creation_info.get("name", "Unknown Creation")
                preview_url = creation_info.get("preview_url")
                if first_creation_id is None:
                    first_creation_id = creation_id

            if first_creation_preview is None and preview_url:
                first_creation_preview = preview_url

            embed.add_field(
                name=f"Complaint #{start_index + index}",
                value=(
                    f"Reporter: **{reporter_name}** (`{reporter_id}`)\n"
                    f"Creator: **{creator_name}** (`{creator_id}`)\n"
                    f"Creation: **{creation_name}** (`{creation_id}`)\n"
                    f"Reason: **{reason}**"
                ),
                inline=False,
            )

        if first_creation_id is not None:
            preview_bytes = await self.moderation_cog.get_creation_preview_bytes(first_creation_id)
            if preview_bytes:
                self.preview_attachment = discord.File(BytesIO(preview_bytes), filename="creation_preview.png")
                embed.set_thumbnail(url="attachment://creation_preview.png")
            elif first_creation_preview:
                embed.set_thumbnail(url=first_creation_preview)
        elif first_creation_preview:
            embed.set_thumbnail(url=first_creation_preview)

        return embed

    async def on_timeout(self):
        self._clear_preview_attachment()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.defer()
        self._loading = True
        try:
            await self.go_to_page(interaction, self.current_page - 1)
        finally:
            self._loading = False

    @discord.ui.button(label="Go To Page", style=discord.ButtonStyle.secondary)
    async def go_to_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(ComplaintsPageJumpModal(self))

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.defer()
        self._loading = True
        try:
            await self.go_to_page(interaction, self.current_page + 1)
        finally:
            self._loading = False


class BanListPaginator(discord.ui.View):
    def __init__(self, moderation_cog: "Moderation", interaction_user_id: int, moderator_user_id: int, start_page: int = 1):
        super().__init__(timeout=300)
        self.moderation_cog = moderation_cog
        self.interaction_user_id = interaction_user_id
        self.moderator_user_id = moderator_user_id

        self.per_page = 6
        self.current_page = max(1, start_page)

        self.total_pages: Optional[int] = None
        self.total_items: Optional[int] = None
        self.items: list[dict[str, Any]] = []
        self.message: Optional[discord.Message] = None
        self._loading = False
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction_user_id:
            await interaction.response.send_message("You are not the one who initiated this command.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.prev_page.disabled = self.current_page <= 1
        if self.total_pages is None:
            self.next_page.disabled = False
        else:
            self.next_page.disabled = self.current_page >= self.total_pages

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {
            "page": page,
            "per_page": self.per_page,
            "IsBanned": "true",
        }
        data, error = await self.moderation_cog.api_request("GET", "/users", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        if isinstance(data, list):
            items = data
            total = None
        elif isinstance(data, dict) and "Page" in data:
            items = data.get("Page") or []
            total_val = data.get("Total")
            total = total_val if isinstance(total_val, int) else None
        else:
            return None, None, None, "Unexpected API response format."

        total_pages = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        return items, total, total_pages, None

    async def initialize(self) -> tuple[Optional[discord.Embed], Optional[str]]:
        items, total, total_pages, error = await self.fetch_page(self.current_page)
        if error:
            return None, error

        self.items = items or []
        self.total_items = total
        self.total_pages = total_pages
        self.update_buttons()
        return self.build_embed(), None

    async def go_to_page(self, interaction: discord.Interaction, page: int):
        if page < 1:
            await interaction.followup.send("Page must be 1 or higher.", ephemeral=True)
            return

        items, total, total_pages, error = await self.fetch_page(page)
        if error:
            await interaction.followup.send(f"Failed to fetch page: {error}", ephemeral=True)
            return

        if not items and page > 1:
            await interaction.followup.send("That page has no items.", ephemeral=True)
            return

        self.current_page = page
        self.items = items or []
        self.total_items = total
        self.total_pages = total_pages
        self.update_buttons()

        if self.message is not None:
            await self.message.edit(embed=self.build_embed(), view=self)

    def build_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="Banned Players",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=EMBED_COLOR,
        )

        if self.total_items is not None:
            embed.set_footer(text=f"Total: {self.total_items}")

        if not self.items:
            embed.description += "\nNo banned players found on this page."
            return embed

        for user in self.items:
            uid = user.get("ID", "?")
            username = user.get("Username", "Unknown")
            embed.add_field(
                name=f"**{username}**",
                value=f"ID: `{uid}`",
                inline=False,
            )

        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.defer()
        self._loading = True
        try:
            await self.go_to_page(interaction, self.current_page - 1)
        finally:
            self._loading = False

    @discord.ui.button(label="Go To Page", style=discord.ButtonStyle.secondary)
    async def go_to_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(BanListPageJumpModal(self))

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.defer()
        self._loading = True
        try:
            await self.go_to_page(interaction, self.current_page + 1)
        finally:
            self._loading = False
            
class BannedCreationsPageJumpModal(discord.ui.Modal, title="Go to Banned Creations Page"):
    page_input = discord.ui.TextInput(label="Page", placeholder="Enter a page number (e.g. 1)", min_length=1, max_length=6)

    def __init__(self, view: "BannedCreationsPaginator"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.page_input).strip()
        if not raw_value.isdigit():
            await interaction.response.send_message("Please enter a valid page number.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if self.view._loading:
            return
        self.view._loading = True
        try:
            await self.view.go_to_page(interaction, int(raw_value))
        finally:
            self.view._loading = False


class BannedCreationsPaginator(discord.ui.View):
    def __init__(self, moderation_cog: "Moderation", interaction_user_id: int, moderator_user_id: int, per_page: int = 6, start_page: int = 1):
        super().__init__(timeout=300)
        self.moderation_cog = moderation_cog
        self.interaction_user_id = interaction_user_id
        self.moderator_user_id = moderator_user_id
        self.per_page = per_page
        self.current_page = max(1, start_page)
        self.total_pages: Optional[int] = None
        self.total_items: Optional[int] = None
        self.items: list[dict[str, Any]] = []
        self.message: Optional[discord.Message] = None
        self._loading = False
        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction_user_id:
            await interaction.response.send_message("You are not the one who initiated this command.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.prev_page.disabled = self.current_page <= 1
        self.next_page.disabled = (self.total_pages is not None and self.current_page >= self.total_pages)

    async def fetch_page(self, page: int):
        params = {"page": page, "per_page": self.per_page, "status": "BANNED"}
        data, error = await self.moderation_cog.api_request("GET", "/player_creations", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        if not (isinstance(data, dict) and "Page" in data):
            return None, None, None, "Unexpected API response format."

        items = data.get("Page") or []
        total_val = data.get("Total")
        total = total_val if isinstance(total_val, int) else None

        total_pages = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        return items, total, total_pages, None

    async def initialize(self):
        items, total, total_pages, error = await self.fetch_page(self.current_page)
        if error:
            return None, error
        self.items = items or []
        self.total_items = total
        self.total_pages = total_pages
        self.update_buttons()
        return await self.build_embed(), None

    async def go_to_page(self, interaction: discord.Interaction, page: int):
        if page < 1:
            await interaction.followup.send("Page must be 1 or higher.", ephemeral=True)
            return

        items, total, total_pages, error = await self.fetch_page(page)
        if error:
            await interaction.followup.send(f"Failed to fetch page: {error}", ephemeral=True)
            return
        if not items and page > 1:
            await interaction.followup.send("That page has no items.", ephemeral=True)
            return

        self.current_page = page
        self.items = items or []
        self.total_items = total
        self.total_pages = total_pages
        self.update_buttons()

        if self.message is not None:
            await self.message.edit(embed=await self.build_embed(), view=self)

    async def build_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="Banned Creations",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=EMBED_COLOR,
        )
        if self.total_items is not None:
            embed.set_footer(text=f"Total banned creations: {self.total_items}")

        if not self.items:
            embed.description += "\nNo banned creations found."
            return embed

        player_ids = [c.get("PlayerID") for c in self.items]
        player_names = await asyncio.gather(
            *(self.moderation_cog.resolve_player_name(player_id) for player_id in player_ids)
        )

        for c, player_name in zip(self.items, player_names):
            cid = c.get("ID", "?")
            name = c.get("Name", "Unknown")
            ctype = c.get("Type", "?")
            ctype_label = CREATION_TYPE_LABELS.get(ctype, f"Unknown ({ctype})")

            player_id = c.get("PlayerID")
            player_id_text = player_id if player_id is not None else "?"
            embed.add_field(
                name=name,
                value=f"ID: `{cid}`\nType: `{ctype_label}`\nPlayer: `{player_name}` (`{player_id_text}`)",
                inline=False,
            )
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.defer()
        self._loading = True
        try:
            await self.go_to_page(interaction, self.current_page - 1)
        finally:
            self._loading = False

    @discord.ui.button(label="Go To Page", style=discord.ButtonStyle.secondary)
    async def go_to_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(BannedCreationsPageJumpModal(self))

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._loading:
            await interaction.response.defer()
            return
        await interaction.response.defer()
        self._loading = True
        try:
            await self.go_to_page(interaction, self.current_page + 1)
        finally:
            self._loading = False
