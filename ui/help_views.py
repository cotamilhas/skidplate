from typing import Any, Optional

import discord

from config import EMBED_COLOR
from .pagination import BasePaginatorView


class HelpPaginator(BasePaginatorView):
    page_modal_title = "Go to Help Page"

    def __init__(
        self,
        owner_user_id: int,
        *,
        pages: list[dict[str, Any]],
        bot_name: str,
        requester_name: str,
        requester_avatar_url: Optional[str],
        bot_avatar_url: Optional[str],
        start_page: int = 1
    ):
        super().__init__(owner_user_id, per_page=1, start_page=start_page)
        self.pages = pages
        self.bot_name = bot_name
        self.requester_name = requester_name
        self.requester_avatar_url = requester_avatar_url
        self.bot_avatar_url = bot_avatar_url

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        total_pages = max(1, len(self.pages))
        if page < 1 or page > total_pages:
            return [], len(self.pages), total_pages, None
        return [self.pages[page - 1]], len(self.pages), total_pages, None

    async def build_embed(self) -> discord.Embed:
        page_data = self.items[0] if self.items else {"fields": []}
        embed = discord.Embed(
            title=f"Help for {self.bot_name} - {page_data.get('category', 'Help')}",
            color=EMBED_COLOR,
            description=(
                "Use `/help <command>` to get details for a specific command."
            )
        )

        for field in page_data.get("fields", []):
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=False
            )

        embed.set_footer(
            text=f"Page {self.current_page}/{self.total_pages or 1} • Requested by {self.requester_name}",
            icon_url=self.requester_avatar_url
        )
        if self.bot_avatar_url:
            embed.set_thumbnail(url=self.bot_avatar_url)
        return embed