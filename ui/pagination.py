from typing import Any, Optional

import discord


class PageJumpModal(discord.ui.Modal):
    page_input = discord.ui.TextInput(
        label="Page",
        placeholder="Enter a page number (e.g. 1)",
        min_length=1,
        max_length=6
    )

    def __init__(self, view: "BasePaginatorView", *, title: str):
        super().__init__(title=title)
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


class BasePaginatorView(discord.ui.View):
    page_modal_title = "Go to Page"
    page_param_zero_indexed = False

    def __init__(self, owner_user_id: int, *, per_page: int, start_page: int):
        super().__init__(timeout=300)
        self.owner_user_id = owner_user_id
        self.per_page = per_page
        self.current_page = max(1, start_page)
        self.total_pages: Optional[int] = None
        self.total_items: Optional[int] = None
        self.items: list[dict[str, Any]] = []
        self.message: Optional[discord.Message] = None
        self._loading = False
        self.update_buttons()

    def _api_page_value(self, page: int) -> int:
        if self.page_param_zero_indexed:
            return max(0, page - 1)
        return page

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_user_id:
            await interaction.response.send_message("You are not the one who initiated this command.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.prev_page.disabled = self.current_page <= 1
        self.next_page.disabled = self.total_pages is not None and self.current_page >= self.total_pages

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        raise NotImplementedError

    async def build_embed(self) -> discord.Embed:
        raise NotImplementedError

    async def _on_page_changed(self):
        return None

    def _message_edit_kwargs(self, embed: discord.Embed) -> dict[str, Any]:
        return {"embed": embed, "view": self}

    async def initialize(self) -> tuple[Optional[discord.Embed], Optional[str]]:
        items, total, total_pages, error = await self.fetch_page(self.current_page)
        if error:
            return None, error

        self.items = items or []
        self.total_items = total
        self.total_pages = total_pages
        self.update_buttons()
        await self._on_page_changed()
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
        await self._on_page_changed()

        if self.message is not None:
            embed = await self.build_embed()
            await self.message.edit(**self._message_edit_kwargs(embed))

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="< Previous", style=discord.ButtonStyle.primary)
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
        await interaction.response.send_modal(PageJumpModal(self, title=self.page_modal_title))

    @discord.ui.button(label="Next >", style=discord.ButtonStyle.primary)
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
