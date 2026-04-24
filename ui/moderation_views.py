import asyncio
from typing import TYPE_CHECKING, Any, Optional
from io import BytesIO

import discord

from utils import (
    prepare_player_avatar_attachment,
    cleanup_temp_file,
    parse_hotlap_queue_payload,
    extract_creation_id,
    PLATFORM_LABELS,
    to_discord_timestamp
)
from .creation_embeds import build_creation_complaints_embed, build_banned_creations_embed
from .player_embeds import build_player_complaints_embed, build_banned_players_embed
from .pagination import BasePaginatorView

if TYPE_CHECKING:
    from cogs.moderation import Moderation


class ComplaintsPaginator(BasePaginatorView):
    page_modal_title = "Go to Complaints Page"
    page_param_zero_indexed = True

    def __init__(
        self,
        moderation_cog: "Moderation",
        interaction_user_id: int,
        moderator_user_id: int,
        endpoint: str,
        mode: str,
        per_page: int = 1,
        start_page: int = 1
    ):
        self.moderation_cog = moderation_cog
        self.moderator_user_id = moderator_user_id
        super().__init__(
            interaction_user_id,
            per_page=per_page,
            start_page=start_page
        )
        self.endpoint = endpoint
        self.mode = mode
        self.preview_attachment: Optional[discord.File] = None
        self.temp_preview_path: Optional[str] = None

    def _clear_preview_attachment(self):
        cleanup_temp_file(self.temp_preview_path)
        self.temp_preview_path = None
        self.preview_attachment = None

    async def _on_page_changed(self):
        self._clear_preview_attachment()

    def _message_edit_kwargs(self, embed: discord.Embed) -> dict[str, Any]:
        attachments = [self.preview_attachment] if self.preview_attachment else []
        return {"embed": embed, "view": self, "attachments": attachments}

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {
            "page": self._api_page_value(page),
            "per_page": self.per_page
        }
        data, error = await self.moderation_cog.api_request("GET", self.endpoint, self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        total: Optional[int] = None
        items: list[dict[str, Any]] = []

        if isinstance(data, dict) and "items" in data:
            parsed_items = data.get("items") or []
            items = [item for item in parsed_items if isinstance(item, dict)]
            total = data.get("count") if isinstance(data.get("count"), int) else None
        elif isinstance(data, dict) and "Page" in data:
            parsed_items = data.get("Page") or []
            items = [item for item in parsed_items if isinstance(item, dict)]
            total = data.get("Total") if isinstance(data.get("Total"), int) else None
        elif isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
        else:
            return None, None, None, "Unexpected API response format."

        total_pages: Optional[int] = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        items.reverse()
        return items, total, total_pages, None

    async def build_embed(self) -> discord.Embed:
        if self.mode == "player":
            return await self._build_player_embed()
        return await self._build_creation_embed()

    async def _build_player_embed(self) -> discord.Embed:
        reporter_ids = [item.get("UserId") for item in self.items]
        reported_ids = [item.get("PlayerId") for item in self.items]

        reporter_names = await asyncio.gather(
            *(self.moderation_cog.resolve_player_name(player_id) for player_id in reporter_ids)
        )
        reported_names = await asyncio.gather(
            *(self.moderation_cog.resolve_player_name(player_id) for player_id in reported_ids)
        )

        embed = build_player_complaints_embed(
            items=self.items,
            current_page=self.current_page,
            per_page=self.per_page,
            total_pages=self.total_pages,
            reporter_names=reporter_names,
            reported_names=reported_names
        )

        first_reported_player_id = next((pid for pid in reported_ids if isinstance(pid, int)), None)
        if first_reported_player_id is not None:
            avatar_url = await self.moderation_cog.resolve_player_avatar(first_reported_player_id)
            avatar_file, avatar_thumbnail_url, temp_avatar_path = await prepare_player_avatar_attachment(
                self.moderation_cog.session,
                avatar_url,
                str(first_reported_player_id)
            )
            self.preview_attachment = avatar_file
            self.temp_preview_path = temp_avatar_path
            embed.set_thumbnail(url=avatar_thumbnail_url)

        return embed

    async def _build_creation_embed(self) -> discord.Embed:
        reporter_ids = [item.get("UserId") for item in self.items]
        creator_ids = [item.get("PlayerId") for item in self.items]
        creation_ids = [item.get("PlayerCreationId") for item in self.items]

        reporter_names = await asyncio.gather(
            *(self.moderation_cog.resolve_player_name(player_id) for player_id in reporter_ids)
        )
        creator_names = await asyncio.gather(
            *(self.moderation_cog.resolve_player_name(player_id) for player_id in creator_ids)
        )

        async def resolve_creation(cid: Any) -> tuple[str, Optional[str]]:
            if not isinstance(cid, int):
                return "Unknown Creation", None
            creation_info = await self.moderation_cog.resolve_creation_info(cid)
            return creation_info.get("name", "Unknown Creation"), creation_info.get("preview_url")

        creation_results = await asyncio.gather(*(resolve_creation(cid) for cid in creation_ids))
        creation_names = [result[0] for result in creation_results]

        embed = build_creation_complaints_embed(
            items=self.items,
            current_page=self.current_page,
            per_page=self.per_page,
            total_pages=self.total_pages,
            reporter_names=reporter_names,
            creator_names=creator_names,
            creation_names=creation_names
        )

        first_creation_id = next((cid for cid in creation_ids if isinstance(cid, int)), None)
        first_creation_preview = next((result[1] for result in creation_results if result[1]), None)

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
        await super().on_timeout()


class BanListPaginator(BasePaginatorView):
    page_modal_title = "Go to Ban List Page"
    page_param_zero_indexed = True

    def __init__(self, moderation_cog: "Moderation", interaction_user_id: int, moderator_user_id: int, start_page: int = 1):
        self.moderation_cog = moderation_cog
        self.moderator_user_id = moderator_user_id
        super().__init__(
            interaction_user_id,
            per_page=6,
            start_page=start_page
        )

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {
            "page": self._api_page_value(page),
            "per_page": self.per_page,
            "IsBanned": "true"
        }
        data, error = await self.moderation_cog.api_request("GET", "/users", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        if isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
            total = None
        elif isinstance(data, dict) and "Page" in data:
            parsed_items = data.get("Page") or []
            items = [item for item in parsed_items if isinstance(item, dict)]
            total = data.get("Total") if isinstance(data.get("Total"), int) else None
        else:
            return None, None, None, "Unexpected API response format."

        total_pages = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        return items, total, total_pages, None

    async def build_embed(self) -> discord.Embed:
        return build_banned_players_embed(
            items=self.items,
            current_page=self.current_page,
            total_pages=self.total_pages,
            total_items=self.total_items
        )


class BannedCreationsPaginator(BasePaginatorView):
    page_modal_title = "Go to Banned Creations Page"
    page_param_zero_indexed = True

    def __init__(self, moderation_cog: "Moderation", interaction_user_id: int, moderator_user_id: int, per_page: int = 6, start_page: int = 1):
        self.moderation_cog = moderation_cog
        self.moderator_user_id = moderator_user_id
        super().__init__(
            interaction_user_id,
            per_page=per_page,
            start_page=start_page
        )

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {
            "page": self._api_page_value(page),
            "per_page": self.per_page,
            "status": "BANNED"
        }
        data, error = await self.moderation_cog.api_request("GET", "/player_creations", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        if not (isinstance(data, dict) and "Page" in data):
            return None, None, None, "Unexpected API response format."

        parsed_items = data.get("Page") or []
        items = [item for item in parsed_items if isinstance(item, dict)]
        total = data.get("Total") if isinstance(data.get("Total"), int) else None

        total_pages = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        return items, total, total_pages, None

    async def build_embed(self) -> discord.Embed:
        player_ids = [item.get("PlayerID") for item in self.items]
        player_names = await asyncio.gather(
            *(self.moderation_cog.resolve_player_name(player_id) for player_id in player_ids)
        )
        return build_banned_creations_embed(
            items=self.items,
            current_page=self.current_page,
            total_pages=self.total_pages,
            total_items=self.total_items,
            player_names=player_names
        )


class ModeratorListPaginator(BasePaginatorView):
    page_modal_title = "Go to Moderators Page"

    def __init__(self, moderation_cog: "Moderation", interaction_user_id: int, moderator_user_id: int, start_page: int = 1):
        self.moderation_cog = moderation_cog
        self.moderator_user_id = moderator_user_id
        super().__init__(interaction_user_id, per_page=6, start_page=start_page)

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {"page": page, "per_page": self.per_page}
        data, error = await self.moderation_cog.api_request("GET", "/moderators", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        if isinstance(data, dict) and "Page" in data:
            parsed_items = data.get("Page") or []
            items = [item for item in parsed_items if isinstance(item, dict)]
            total = data.get("Total") if isinstance(data.get("Total"), int) else None
        elif isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
            total = len(items)
        else:
            return None, None, None, "Unexpected API response format."

        total_pages = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        return items, total, total_pages, None

    async def build_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="Moderators",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=discord.Color.blue()
        )
        if self.total_items is not None:
            embed.set_footer(text=f"Total: {self.total_items}")

        if not self.items:
            embed.description += "\nNo moderators found."
            return embed

        for mod in self.items:
            mid = mod.get("ID", "?")
            username = mod.get("Username", "Unknown")
            embed.add_field(name=f"ID: {mid}", value=f"**{username}**", inline=False)

        return embed


class AnnouncementsPaginator(BasePaginatorView):
    page_modal_title = "Go to Announcements Page"

    def __init__(
        self,
        moderation_cog: "Moderation",
        interaction_user_id: int,
        moderator_user_id: int,
        start_page: int = 1,
        platform: Optional[int] = None
    ):
        self.moderation_cog = moderation_cog
        self.moderator_user_id = moderator_user_id
        self.platform = platform
        super().__init__(interaction_user_id, per_page=6, start_page=start_page)

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params: dict[str, Any] = {"page": page, "per_page": self.per_page}
        if self.platform is not None:
            params["platform"] = self.platform

        data, error = await self.moderation_cog.api_request("GET", "/announcements", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        if isinstance(data, dict) and "Page" in data:
            parsed_items = data.get("Page") or []
            items = [item for item in parsed_items if isinstance(item, dict)]
            total = data.get("Total") if isinstance(data.get("Total"), int) else None
        elif isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
            total = len(items)
        else:
            return None, None, None, "Unexpected API response format."

        total_pages = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        return items, total, total_pages, None

    async def build_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="Announcements",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=discord.Color.yellow()
        )
        if self.total_items is not None:
            embed.set_footer(text=f"Total: {self.total_items}")

        if not self.items:
            embed.description += "\nNo announcements found."
            return embed

        for announcement in self.items:
            aid = announcement.get("Id", announcement.get("ID", "?"))
            subj = announcement.get("Subject", "(no subject)")
            plat = announcement.get("Platform", "?")
            plat_label = PLATFORM_LABELS.get(plat, str(plat)) if isinstance(plat, int) else str(plat)
            created = announcement.get("CreatedAt", "")
            text = announcement.get("Text", "")
            preview = text if isinstance(text, str) and len(text) <= 140 else (f"{str(text)[:140]}..." if text else "")
            embed.add_field(
                name=f"#{aid} | Platform: {plat_label}",
                value=f"**{subj}**\n{preview}\n{to_discord_timestamp(created)}",
                inline=False
            )

        return embed


class SystemEventsPaginator(BasePaginatorView):
    page_modal_title = "Go to System Events Page"

    def __init__(self, moderation_cog: "Moderation", interaction_user_id: int, moderator_user_id: int, start_page: int = 1):
        self.moderation_cog = moderation_cog
        self.moderator_user_id = moderator_user_id
        super().__init__(interaction_user_id, per_page=6, start_page=start_page)

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {"page": page, "per_page": self.per_page}
        data, error = await self.moderation_cog.api_request("GET", "/system_events", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        if isinstance(data, dict) and "Page" in data:
            parsed_items = data.get("Page") or []
            items = [item for item in parsed_items if isinstance(item, dict)]
            total = data.get("Total") if isinstance(data.get("Total"), int) else None
        elif isinstance(data, list):
            items = [item for item in data if isinstance(item, dict)]
            total = len(items)
        else:
            return None, None, None, "Unexpected API response format."

        total_pages = None
        if total is not None and self.per_page > 0:
            total_pages = max(1, (total + self.per_page - 1) // self.per_page)

        return items, total, total_pages, None

    async def build_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="System Events",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=discord.Color.yellow()
        )
        if self.total_items is not None:
            embed.set_footer(text=f"Total: {self.total_items}")

        if not self.items:
            embed.description += "\nNo system events found."
            return embed

        for event in self.items:
            eid = event.get("Id", event.get("ID", "?"))
            topic = event.get("Topic", "(no topic)")
            desc = event.get("Description", "")
            created = event.get("CreatedAt", "")
            img = event.get("ImageURL", None)
            preview = desc if isinstance(desc, str) and len(desc) <= 160 else (f"{str(desc)[:160]}..." if desc else "")
            value = f"{preview}\n{to_discord_timestamp(created)}"
            if img:
                value += f"\n{img}"
            embed.add_field(name=f"#{eid} | {topic}", value=value, inline=False)

        return embed


class HotlapQueuePaginator(BasePaginatorView):
    page_modal_title = "Go to Hotlap Queue Page"

    def __init__(self, moderation_cog: "Moderation", interaction_user_id: int, moderator_user_id: int, start_page: int = 1):
        self.moderation_cog = moderation_cog
        self.moderator_user_id = moderator_user_id
        super().__init__(interaction_user_id, per_page=6, start_page=start_page)

    async def fetch_page(self, page: int) -> tuple[Optional[list[dict[str, Any]]], Optional[int], Optional[int], Optional[str]]:
        params = {"page": page, "per_page": self.per_page}
        data, error = await self.moderation_cog.api_request("GET", "/hotlap/queue", self.moderator_user_id, params=params)
        if error:
            return None, None, None, error

        queue_entries, total_entries = parse_hotlap_queue_payload(data)
        items: list[dict[str, Any]] = []

        for entry in queue_entries:
            creation_id = extract_creation_id(entry)
            payload_name = None
            if isinstance(entry, dict):
                payload_name = entry.get("Name") or entry.get("name")

            items.append(
                {
                    "raw": entry,
                    "creation_id": creation_id,
                    "payload_name": payload_name
                }
            )

        total_pages = None
        if isinstance(total_entries, int) and self.per_page > 0:
            total_pages = max(1, (total_entries + self.per_page - 1) // self.per_page)

        return items, total_entries, total_pages, None

    async def build_embed(self) -> discord.Embed:
        total_pages_text = str(self.total_pages) if self.total_pages is not None else "?"
        embed = discord.Embed(
            title="Hotlap Queue",
            description=f"Page {self.current_page}/{total_pages_text}",
            color=discord.Color.yellow()
        )
        if self.total_items is not None:
            embed.set_footer(text=f"Total: {self.total_items}")

        if not self.items:
            embed.description += "\nQueue is empty."
            return embed

        for index, item in enumerate(self.items, start=1):
            creation_id = item.get("creation_id")
            payload_name = item.get("payload_name")

            creation_name: Optional[str] = payload_name if isinstance(payload_name, str) and payload_name.strip() else None
            creation_creator: Optional[str] = None

            if creation_id and (not creation_name or not creation_creator):
                creation_info = await self.moderation_cog.resolve_creation_info(creation_id)
                if not creation_name:
                    creation_name = creation_info["name"]
                creation_creator = creation_info["creator"]

            if not creation_id and not creation_name:
                embed.add_field(name=f"#{index}", value="Unknown track entry", inline=False)
                continue

            display_name = creation_name or "Unknown Track"
            id_line = f"ID: `{creation_id}`" if creation_id else "ID: Unknown"
            creator_line = f"Creator: **{creation_creator}**" if creation_creator else "Creator: **Unknown**"
            embed.add_field(
                name=f"#{index} - {display_name}",
                value=f"{creator_line}\n{id_line}",
                inline=False
            )

        return embed
