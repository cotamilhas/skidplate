import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import time
import math
from typing import Any, Callable, Literal, TypeGuard

from config import MODERATOR_ROLE_ID, MAX_QUOTA, MODERATOR_PERMISSIONS
from utils import *


def build_moderation_embed(
    interaction: discord.Interaction,
    title,
    description,
    color: discord.Color,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
    )
    embed.set_footer(
        text=f"Requested by: {interaction.user}",
        icon_url=interaction.user.display_avatar.url,
    )
    return embed

def is_error_response(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and value.startswith("Error:")

def normalize_moderation_page_payload(data: Any) -> tuple[list[Any], int]:
    if isinstance(data, list):
        return data, len(data)

    if isinstance(data, dict):
        page_values = data.get("Page", [])
        total = data.get("Total") or len(page_values)
        if isinstance(page_values, list):
            return page_values, int(total)

    return [], 0

def normalize_console_id_input(console_id: str) -> str:
    # discord can auto-convert :100: into the 100 emoji... yes it's so stupid
    normalized = console_id.strip().replace("💯", ":100:").replace("：", ":")

    separator_candidates = ("-", ".", " ", "|", "/", "_", ";", ",")
    for separator in separator_candidates:
        normalized = normalized.replace(separator, ":")

    while "::" in normalized:
        normalized = normalized.replace("::", ":")

    return normalized.strip(":")


class GoToPageModal(discord.ui.Modal, title="Go to page"):
    def __init__(
        self,
        current_page: int,
        total_pages: int,
        on_page_submit: Callable[[discord.Interaction, int], Any],
    ):
        super().__init__()
        self.total_pages = total_pages
        self.on_page_submit = on_page_submit
        self.page_input = discord.ui.TextInput(
            label="Page number",
            placeholder=f"1-{total_pages}",
            default=str(current_page),
            required=True,
            max_length=6,
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.page_input.value.strip()
        if not value.isdigit():
            await interaction.response.send_message(
                "Please enter a valid page number.",
                ephemeral=True,
            )
            return

        page = int(value)
        if page < 1 or page > self.total_pages:
            await interaction.response.send_message(
                f"Page must be between 1 and {self.total_pages}.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        await self.on_page_submit(interaction, page)


class ModerationPaginatedView(discord.ui.View):
    def __init__(self, requester_id: int, current_page: int = 1, total_pages: int = 1):
        super().__init__(timeout=180)
        self.requester_id = requester_id
        self.current_page = current_page
        self.total_pages = total_pages
        self._update_page_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True

        await interaction.response.send_message(
            "Only the original user can use these controls.",
            ephemeral=True,
        )
        return False

    def _update_page_buttons(self):
        self.previous_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages
        self.goto_page_button.disabled = self.total_pages <= 1

    async def _load_page(self, interaction: discord.Interaction, page: int) -> None:
        raise NotImplementedError

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.current_page <= 1:
            return
        await self._load_page(interaction, self.current_page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.current_page >= self.total_pages:
            return
        await self._load_page(interaction, self.current_page + 1)

    @discord.ui.button(label="Go to page", style=discord.ButtonStyle.secondary, row=0)
    async def goto_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            GoToPageModal(
                current_page=self.current_page,
                total_pages=self.total_pages,
                on_page_submit=self._load_page,
            )
        )


class PermissionSelectionView(discord.ui.View):
    def __init__(
        self,
        token,
        target_username,
        grant_value: bool,
        requester_id: int,
    ):
        super().__init__(timeout=120)
        self.token = token
        self.target_username = target_username
        self.grant_value = grant_value
        self.requester_id = requester_id

        options = [
            discord.SelectOption(label=perm, value=perm)
            for perm in sorted(MODERATOR_PERMISSIONS)
        ]
        self.permission_select = discord.ui.Select(
            placeholder="Select one or more permissions",
            min_values=1,
            max_values=len(options),
            options=options,
        )
        self.permission_select.callback = self._on_permissions_selected
        self.add_item(self.permission_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message(
            "Only the command requester can use this selector.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        self.permission_select.disabled = True

    async def _on_permissions_selected(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        selected = list(self.permission_select.values)
        action_text = "granted" if self.grant_value else "revoked"

        result = await asyncio.to_thread(
            moderator_set_permissions,
            self.token,
            self.target_username,
            selected,
            self.grant_value,
        )

        self.permission_select.disabled = True

        if is_error_response(result):
            embed = build_moderation_embed(
                interaction,
                "Moderation Error",
                result,
                discord.Color.red(),
            )

            await interaction.edit_original_response(embed=embed, view=self)
            await interaction.followup.send(
                "Operation failed. See the original message for details.",
                ephemeral=True,
            )
            return

        embed = build_moderation_embed(
            interaction,
            "Permissions Updated",
            (
                f"Permissions for **{self.target_username}** were {action_text}:\n"
                + "\n".join(f"- **{perm}**" for perm in selected)
            ),
            discord.Color.green(),
        )

        await interaction.edit_original_response(embed=embed, view=self)
        

class LoginModal(discord.ui.Modal, title='Moderator Login'):
    def __init__(self, cog: "Moderation"):
        super().__init__()
        self.cog = cog

    username = discord.ui.TextInput(
        label='Username',
        style=discord.TextStyle.short,
        required=True
    )

    password = discord.ui.TextInput(
        label='Password',
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        token = await asyncio.to_thread(moderator_login, self.username.value, self.password.value)

        if token is None:
            embed = build_moderation_embed(
                interaction,
                "Moderation Error",
                "Error: Unable to login as moderator.",
                discord.Color.red(),
            )
            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )
            return

        if is_error_response(token):
            embed = build_moderation_embed(
                interaction,
                "Moderation Error",
                token,
                discord.Color.red(),
            )
            await interaction.followup.send(
                embed=embed,
                ephemeral=True,
            )
            return

        self.cog.moderation_tokens[interaction.user.id] = token
        embed = build_moderation_embed(
            interaction,
            "Login Successful",
            f"Login as **{self.username.value}** successful.",
            discord.Color.green(),
        )
        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )


class CreateAnnouncementModal(discord.ui.Modal, title="Create Announcement"):
    def __init__(self, cog: "Moderation", token: str):
        super().__init__()
        self.cog = cog
        self.token = token

    language_code = discord.ui.TextInput(
        label="Language Code",
        placeholder="en/US (This is kinda useless since the announcement will be sent to all languages)",
        default="en/US",
        required=False,
        max_length=8,
    )

    subject = discord.ui.TextInput(
        label="Title",
        placeholder="Announcement Title (This will not be displayed in the announcement)",
        required=True,
        max_length=50,
    )

    text = discord.ui.TextInput(
        label="Text",
        placeholder="Announcement Text (This will be displayed in the announcement)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    platform = discord.ui.Select(
        placeholder="Select platform",
        required=True,
        options=[
            discord.SelectOption(label="PS3", value="PS3"),
            discord.SelectOption(label="PSP", value="PSP"),
        ]
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        platform = self.platform
        if platform not in {"PS3", "PSP"}:
            await self.cog._send_followup_error(
                interaction,
                "Platform must be PS3 or PSP.",
            )
            return

        result = await asyncio.to_thread(
            moderator_create_announcement,
            self.token,
            self.language_code.value.strip(),
            self.subject.value.strip(),
            self.text.value.strip(),
            platform,
        )
        if is_error_response(result):
            await self.cog._send_followup_error(interaction, result)
            return

        embed = self.cog._embed(
            interaction,
            "Announcement Created",
            f"Title: **{self.subject.value.strip()}**.\n"
            f"Text: **{self.text.value.strip()}**.\n"
            f"Platform: **{platform}**.",
            discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class ModeratorsListView(ModerationPaginatedView):
    def __init__(self, token: str, interaction: discord.Interaction, per_page: int = 10):
        super().__init__(requester_id=interaction.user.id)
        self.token = token
        self.interaction = interaction
        self.per_page = per_page
        self.total_results = 0

    def _build_embed(self, moderators: list[dict]) -> discord.Embed:
        embed = build_moderation_embed(
            self.interaction,
            "Moderators",
            f"Total: **{self.total_results}** | Page: **{self.current_page}/{self.total_pages}**",
            discord.Color.blue(),
        )

        for moderator in moderators:
            moderator_id = moderator.get("ID")
            username = moderator.get("Username")
            embed.add_field(
                name=f"ID: `{moderator_id}`",
                value=f"{username}",
                inline=False,
            )

        return embed

    def get_first_page_embed(self) -> tuple[discord.Embed | None, str | None]:
        data = moderator_get_moderators(self.token, page=1, per_page=self.per_page)
        if is_error_response(data):
            return None, data

        moderators, total_results = normalize_moderation_page_payload(data)
        if not moderators:
            return None, "No moderators found."

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = 1
        self._update_page_buttons()
        return self._build_embed(moderators), None

    async def _load_page(self, interaction: discord.Interaction, page: int) -> None:
        data = await asyncio.to_thread(moderator_get_moderators, self.token, page, self.per_page)
        if is_error_response(data):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        moderators, total_results = normalize_moderation_page_payload(data)
        if not moderators:
            await interaction.edit_original_response(content="No moderators found.", embed=None, view=None)
            return

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_page_buttons()
        await interaction.edit_original_response(embed=self._build_embed(moderators), view=self)


class BannedCreationsView(ModerationPaginatedView):
    def __init__(self, token: str, interaction: discord.Interaction, per_page: int = 6):
        super().__init__(requester_id=interaction.user.id)
        self.token = token
        self.interaction = interaction
        self.per_page = per_page
        self.total_results = 0

    def _build_embed(self, creations: list[dict]) -> discord.Embed:
        embed = build_moderation_embed(
            self.interaction,
            "Banned Creations",
            f"Total: **{self.total_results}** | Page: **{self.current_page}/{self.total_pages}**",
            discord.Color.red(),
        )

        for creation in creations:
            creation_id = creation.get("ID")
            name = creation.get("Name")
            
            creation_type = creation.get("Type")
            creation_type = rename_creation_type(CreationType(creation_type).name)
            
            username = get_player_username(creation.get("PlayerID"))
            is_mnr = creation.get("IsMNR") # idk maybe useful later

            embed.add_field(
                name=f"{name} `{creation_id}`",
                value=f"Creator: {username}\nType: {creation_type}",
                inline=False,
            )

        return embed

    def get_first_page_embed(self) -> tuple[discord.Embed | None, str | None]:
        data = moderator_get_banned_player_creations(
            self.token,
            page=1,
            per_page=self.per_page,
        )
        if is_error_response(data):
            return None, data

        creations, total_results = normalize_moderation_page_payload(data)
        if not creations:
            return None, "No banned creations found."

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = 1
        self._update_page_buttons()
        return self._build_embed(creations), None

    async def _load_page(self, interaction: discord.Interaction, page: int) -> None:
        data = await asyncio.to_thread(
            moderator_get_banned_player_creations,
            self.token,
            page,
            self.per_page,
        )
        if is_error_response(data):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        creations, total_results = normalize_moderation_page_payload(data)
        if not creations:
            await interaction.edit_original_response(content="No banned creations found.", embed=None, view=None)
            return

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_page_buttons()
        embed = await asyncio.to_thread(self._build_embed, creations)
        await interaction.edit_original_response(embed=embed, view=self)


class CreationComplaintsListView(ModerationPaginatedView):
    def __init__(self, token: str, interaction: discord.Interaction, per_page: int = 1):
        super().__init__(requester_id=interaction.user.id)
        self.token = token
        self.interaction = interaction
        self.per_page = per_page
        self.total_results = 0

    def _build_embed(self, complaints: list[dict]) -> discord.Embed:
        embed = build_moderation_embed(
            self.interaction,
            "Creation Complaints",
            f"Total: **{self.total_results}** | Page: **{self.current_page}/{self.total_pages}**",
            discord.Color.orange(),
        )

        for complaint in complaints:
            user_id = complaint.get("UserId")
            player_id = complaint.get("PlayerId")
            creation_id = complaint.get("PlayerCreationId")
            reason = complaint.get("Reason")
            comments = complaint.get("Comments")

            embed.add_field(
                name=f"{get_creation_name(creation_id)} `{creation_id}`",
                value=(
                    f"Created by: `{get_player_username(player_id)}`\n"
                    f"Reported by: `{get_player_username(user_id)}`\n"
                    f"Reason: **{rename_complaint(str(reason))}**\n"
                ),
                inline=False,
            )
            
            embed.set_thumbnail(url=f"{URL}/player_creations/{creation_id}/preview_image.png")
            
            if comments:
                embed.add_field(
                    name="Comments",
                    value=comments,
                    inline=False,
                )

        return embed

    def get_first_page_embed(self) -> tuple[discord.Embed | None, str | None]:
        data = moderator_get_creation_complaints(self.token, page=1, per_page=self.per_page)
        if is_error_response(data):
            return None, data

        complaints, total_results = normalize_moderation_page_payload(data)
        if not complaints:
            return None, "No creation complaints found."

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = 1
        self._update_page_buttons()
        return self._build_embed(complaints), None

    async def _load_page(self, interaction: discord.Interaction, page: int) -> None:
        data = await asyncio.to_thread(
            moderator_get_creation_complaints,
            self.token,
            page,
            self.per_page,
        )
        if is_error_response(data):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        complaints, total_results = normalize_moderation_page_payload(data)
        if not complaints:
            await interaction.edit_original_response(content="No creation complaints found.", embed=None, view=None)
            return

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_page_buttons()
        await interaction.edit_original_response(embed=self._build_embed(complaints), view=self)


class PlayerComplaintsListView(ModerationPaginatedView):
    def __init__(self, token: str, interaction: discord.Interaction, per_page: int = 1):
        super().__init__(requester_id=interaction.user.id)
        self.token = token
        self.interaction = interaction
        self.per_page = per_page
        self.total_results = 0

    def _build_embed(self, complaints: list[dict]) -> discord.Embed:
        embed = build_moderation_embed(
            self.interaction,
            "Player Complaints",
            f"Total: **{self.total_results}** | Page: **{self.current_page}/{self.total_pages}**",
            discord.Color.orange(),
        )

        for complaint in complaints:
            user_id = complaint.get("UserId")
            player_id = complaint.get("PlayerId")
            reason = complaint.get("Reason")
            comments = complaint.get("Comments")

            embed.add_field(
                name=f"`{get_player_username(player_id)}`",
                value=(
                    f"Reported by: `{get_player_username(user_id)}`\n"
                    f"Reason: **{rename_complaint(str(reason))}**"
                ),
                inline=False,
            )
            
            embed.set_thumbnail(url=f"{URL}/player_avatars/MNR/{player_id}/secondary.png?{int(time.time())}")
            
            if comments:
                embed.add_field(
                    name="Comments",
                    value=comments,
                    inline=False,
                )

        return embed

    def get_first_page_embed(self) -> tuple[discord.Embed | None, str | None]:
        data = moderator_get_player_complaints(self.token, page=1, per_page=self.per_page)
        if is_error_response(data):
            return None, data

        complaints, total_results = normalize_moderation_page_payload(data)
        if not complaints:
            return None, "No player complaints found."

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = 1
        self._update_page_buttons()
        return self._build_embed(complaints), None

    async def _load_page(self, interaction: discord.Interaction, page: int) -> None:
        data = await asyncio.to_thread(
            moderator_get_player_complaints,
            self.token,
            page,
            self.per_page,
        )
        if is_error_response(data):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        complaints, total_results = normalize_moderation_page_payload(data)
        if not complaints:
            await interaction.edit_original_response(content="No player complaints found.", embed=None, view=None)
            return

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_page_buttons()
        await interaction.edit_original_response(embed=self._build_embed(complaints), view=self)


class AnnouncementsListView(ModerationPaginatedView):
    def __init__(
        self,
        token: str,
        interaction: discord.Interaction,
        per_page: int = 6,
        platform: str | None = None,
    ):
        super().__init__(requester_id=interaction.user.id)
        self.token = token
        self.interaction = interaction
        self.per_page = per_page
        self.platform = platform
        self.total_results = 0

    def _build_embed(self, announcements: list[dict]) -> discord.Embed:
        embed = build_moderation_embed(
            self.interaction,
            "Announcements",
            f"Total: **{self.total_results}** | Page: **{self.current_page}/{self.total_pages}**",
            discord.Color.blue(),
        )

        for announcement in announcements:
            announcement_id = announcement.get("Id")
            subject = announcement.get("Subject")
            text = str(announcement.get("Text"))
            platform = get_platform_name(announcement.get("Platform"))
            created_at = announcement.get("CreatedAt")
            created_at = convert_datetime_to_discord_date(created_at)
            shortened_text = text if len(text) <= 250 else f"{text[:247]}..."

            embed.add_field(
                name=f"{subject} `{announcement_id}`",
                value=f"{shortened_text}\n"
                f"Platform: **{platform}**\n"
                f"Created At: {created_at}",
                inline=False,
            )

        return embed

    def get_first_page_embed(self) -> tuple[discord.Embed | None, str | None]:
        data = moderator_get_announcements(
            self.token,
            page=1,
            per_page=self.per_page,
            platform=self.platform,
        )
        if is_error_response(data):
            return None, data

        announcements, total_results = normalize_moderation_page_payload(data)
        if not announcements:
            return None, "No announcements found."

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = 1
        self._update_page_buttons()
        return self._build_embed(announcements), None

    async def _load_page(self, interaction: discord.Interaction, page: int) -> None:
        data = await asyncio.to_thread(
            moderator_get_announcements,
            self.token,
            page,
            self.per_page,
            self.platform,
        )
        if is_error_response(data):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        announcements, total_results = normalize_moderation_page_payload(data)
        if not announcements:
            await interaction.edit_original_response(content="No announcements found.", embed=None, view=None)
            return

        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_page_buttons()
        await interaction.edit_original_response(embed=self._build_embed(announcements), view=self)


class BannedConsoleIdsListView(ModerationPaginatedView):
    def __init__(self, token: str, interaction: discord.Interaction, per_page: int = 10):
        super().__init__(requester_id=interaction.user.id)
        self.token = token
        self.interaction = interaction
        self.per_page = per_page
        self.total_results = 0
        self.console_ids: list[str] = []

    def _build_embed(self) -> discord.Embed:
        embed = build_moderation_embed(
            self.interaction,
            "Banned Console IDs",
            f"Total: **{self.total_results}** | Page: **{self.current_page}/{self.total_pages}**",
            discord.Color.orange(),
        )

        if not self.console_ids:
            embed.description = (
                f"Total: **{self.total_results}** | Page: **{self.current_page}/{self.total_pages}**\n\n"
                "No banned console IDs found."
            )
            return embed

        for console_id in self.console_ids:
            embed.add_field(name="Console ID", value=f"`{console_id}`", inline=False)

        return embed

    def get_first_page_embed(self) -> tuple[discord.Embed | None, str | None]:
        data = moderator_get_banned_console_ids(self.token, page=1, per_page=self.per_page)
        if is_error_response(data):
            return None, data

        console_ids, total_results = normalize_moderation_page_payload(data)
        self.console_ids = [str(console_id) for console_id in console_ids]
        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = 1
        self._update_page_buttons()
        return self._build_embed(), None

    async def _load_page(self, interaction: discord.Interaction, page: int) -> None:
        data = await asyncio.to_thread(moderator_get_banned_console_ids, self.token, page, self.per_page)
        if is_error_response(data):
            await interaction.edit_original_response(content=data, embed=None, view=None)
            return

        console_ids, total_results = normalize_moderation_page_payload(data)
        self.console_ids = [str(console_id) for console_id in console_ids]
        self.total_results = total_results
        self.total_pages = max(1, math.ceil(total_results / self.per_page))
        self.current_page = min(max(page, 1), self.total_pages)
        self._update_page_buttons()
        await interaction.edit_original_response(embed=self._build_embed(), view=self)
            

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        token_store = getattr(bot, "_moderation_tokens", None)
        if not isinstance(token_store, dict):
            token_store = {}
            setattr(bot, "_moderation_tokens", token_store)
        self.moderation_tokens: dict[int, str] = token_store

    def _has_moderator_role(self, interaction: discord.Interaction) -> bool:
        if not MODERATOR_ROLE_ID:
            return False

        try:
            moderator_role_id = int(MODERATOR_ROLE_ID)
        except ValueError:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        return any(role.id == moderator_role_id for role in member.roles)

    def _embed(
        self,
        interaction: discord.Interaction,
        title,
        description,
        color: discord.Color,
    ) -> discord.Embed:
        return build_moderation_embed(interaction, title, description, color)

    async def _send_initial_error(self, interaction: discord.Interaction, message) -> None:
        await interaction.response.send_message(
            embed=self._embed(
                interaction,
                "Moderation Error",
                message,
                discord.Color.red(),
            ),
            ephemeral=True,
        )

    async def _send_followup_error(self, interaction: discord.Interaction, message) -> None:
        await interaction.followup.send(
            embed=self._embed(
                interaction,
                "Moderation Error",
                message,
                discord.Color.red(),
            ),
            ephemeral=True,
        )

    async def _require_moderator_token(self, interaction: discord.Interaction) -> str | None:
        token = self.moderation_tokens.get(interaction.user.id)
        if token:
            refreshed_token = await asyncio.to_thread(refresh_moderator_token, token)
            if isinstance(refreshed_token, str):
                self.moderation_tokens[interaction.user.id] = refreshed_token
                return refreshed_token
            return token

        await self._send_initial_error(interaction, "You need to login first.")
        return None

    async def _require_moderator_role(self, interaction: discord.Interaction) -> bool:
        if self._has_moderator_role(interaction):
            return True

        await interaction.response.send_message(
            embed=self._embed(
                interaction,
                "Permission Denied",
                "You do not have permission to use moderation commands.",
                discord.Color.red(),
            ),
            ephemeral=True,
        )
        return False
    
    moderation = app_commands.Group(name="mod", description="Moderation commands")

    @moderation.command(name="login", description="Login to the moderation panel")
    async def login(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        try:
            await interaction.response.send_modal(LoginModal(self))
        except discord.NotFound:
            return

    @moderation.command(name="ban_player", description="Ban or unban a player")
    @app_commands.describe(username="Player username", is_banned="True to ban, false to unban")
    async def ban_player(self, interaction: discord.Interaction, username: str, is_banned: bool):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_set_player_ban, token, username, is_banned)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        player_id = await asyncio.to_thread(get_player_id, username)

        embed = discord.Embed()
        embed.title = "Player Banned" if is_banned else "Player Unbanned"
        
        if is_banned:
            embed.color = discord.Color.red()
        else:
            embed.color = discord.Color.green()
            
        embed.add_field(
            name="Username",
            value=username,
            inline=True
        )
        
        embed.add_field(
            name="ID",
            value=player_id,
            inline=True
        )

        embed.set_thumbnail(url=f"{URL}/player_avatars/MNR/{player_id}/secondary.png?{int(time.time())}")
        embed.set_footer(
            text=f"Requested by: {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="ban_creation", description="Ban or unban a creation")
    @app_commands.describe(creation_id="Creation ID", is_banned="True to ban, false to unban")
    async def ban_creation(self, interaction: discord.Interaction, creation_id: int, is_banned: bool):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)
        
        result = await asyncio.to_thread(moderator_ban_creation, token, creation_id, is_banned)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        creation_stats = await asyncio.to_thread(get_creation_stats, creation_id)
        embed = discord.Embed()
        embed.title = "Creation Banned" if is_banned else "Creation Unbanned"
        
        if isinstance(creation_stats, str):
            await self._send_followup_error(interaction, creation_stats)
            return
        
        if is_banned:
            embed.color = discord.Color.red()
        else:
            embed.color = discord.Color.green()
            
        embed.add_field(
            name="Creation ID",
            value=str(creation_id),
            inline=True
        )
        
        embed.add_field(
            name="Creation Name",
            value=creation_stats.get("name"),
            inline=True
        )
        
        embed.set_thumbnail(url=f"{URL}/player_creations/{creation_id}/preview_image.png")
        
        embed.set_footer(
            text=f"Requested by: {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="set_quota", description="Set a player's quota (creation slots)")
    @app_commands.describe(username="Player username", quota="New quota (creation slots) value")
    async def set_quota(self, interaction: discord.Interaction, username: str, quota: int):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)
        
        if quota < 0 or quota > MAX_QUOTA:
            await self._send_followup_error(
                interaction,
                f"Quota must be between 0 and {MAX_QUOTA}.",
            )
            return

        result = await asyncio.to_thread(moderator_set_user_quota, token, username, quota)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        player_id = await asyncio.to_thread(get_player_id, username)

        embed = discord.Embed(
            title="Quota Updated",
            description=f"Quota for **{username}** has been set to **{quota}**.",
            color=discord.Color.green(),
        )
        
        embed.set_thumbnail(url=f"{URL}/player_avatars/MNR/{player_id}/secondary.png?{int(time.time())}")
        
        embed.set_footer(
            text=f"Requested by: {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="allow_opposite_platform", description="Basically link PSN and RPCN accounts")
    @app_commands.describe(username="Player username", allow_opposite_platform="True to allow, false to disallow")
    async def allow_opposite_platform(self, interaction: discord.Interaction, username: str, allow_opposite_platform: bool):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_user_allow_opposite_platform, token, username, allow_opposite_platform)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        player_id = await asyncio.to_thread(get_player_id, username)

        embed = discord.Embed(
            title="Opposite Platform Updated",
            description=f"Opposite platform for **{username}** has been {'allowed' if allow_opposite_platform else 'disallowed'}.",
            color=discord.Color.green(),
        )
        
        embed.set_thumbnail(url=f"{URL}/player_avatars/MNR/{player_id}/secondary.png?{int(time.time())}")
        
        embed.set_footer(
            text=f"Requested by: {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )

    @moderation.command(name="reset_user_profile", description="Reset user profile and optionally remove creations")
    @app_commands.describe(username="Player username")
    @app_commands.describe(remove_creations="Also remove all player creations")
    async def reset_user_profile(self, interaction: discord.Interaction, username: str, remove_creations: bool = False):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_reset_player_profile, token, username, remove_creations)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        player_id = await asyncio.to_thread(get_player_id, username)

        removal_text = " and all creations were removed" if remove_creations else ""
        embed = discord.Embed(
            title="User Profile Reset",
            description=f"Profile for **{username}** has been reset{removal_text}.",
            color=discord.Color.green(),
        )

        embed.set_thumbnail(url=f"{URL}/player_avatars/MNR/{player_id}/secondary.png?{int(time.time())}")
        embed.set_footer(
            text=f"Requested by: {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="delete_avatar", description="Remove a player's avatars")
    @app_commands.describe(username="Player username")
    @app_commands.describe(is_mnr="True to remove MNR avatars, false to remove LBPK avatars")
    async def delete_avatars(self, interaction: discord.Interaction, username: str, is_mnr: bool = True):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_remove_player_avatars, token, username, is_mnr)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = discord.Embed(
            title="Player Avatars Removed",
            description=f"Avatars for **{username}** have been removed.",
            color=discord.Color.green(),
        )
        embed.set_footer(
            text=f"Requested by: {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="get_announcements", description="Get the announcements")
    @app_commands.describe(platform="Optional platform filter (PS3 or PSP)")
    @app_commands.choices(platform=[
        app_commands.Choice(name="PS3", value="PS3"),
        app_commands.Choice(name="PSP", value="PSP"),
    ])
    async def get_announcements(self, interaction: discord.Interaction, platform: str | None = None):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        normalized_platform = platform.strip().upper() if platform and platform.strip() else None
        if normalized_platform not in {None, "PS3", "PSP"}:
            await self._send_initial_error(interaction, "Platform must be PS3 or PSP.")
            return

        await interaction.response.defer(ephemeral=True)

        view = AnnouncementsListView(
            token=token,
            interaction=interaction,
            platform=normalized_platform,
        )
        embed, error = await asyncio.to_thread(view.get_first_page_embed)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        if embed is None:
            await interaction.followup.send("Error: Unable to build announcements view.", ephemeral=True)
            return

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @moderation.command(name="create_announcement", description="Create a new announcement using a modal")
    async def create_announcement(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.send_modal(CreateAnnouncementModal(self, token))

    @moderation.command(name="delete_announcement", description="Delete an announcement by ID")
    @app_commands.describe(announcement_id="Announcement ID")
    async def delete_announcement(self, interaction: discord.Interaction, announcement_id: int):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_delete_announcement, token, announcement_id)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Announcement Deleted",
            f"Announcement **#{announcement_id}** was deleted.",
            discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @moderation.command(name="list_moderators", description="Get moderators with pagination")
    async def list_moderators(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        view = ModeratorsListView(token=token, interaction=interaction)
        embed, error = await asyncio.to_thread(view.get_first_page_embed)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        if embed is None:
            await interaction.followup.send("Error: Unable to build moderators view.", ephemeral=True)
            return

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @moderation.command(name="banned_creations", description="Get banned creations with pagination")
    async def banned_creations(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        view = BannedCreationsView(token=token, interaction=interaction)
        embed, error = await asyncio.to_thread(view.get_first_page_embed)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        if embed is None:
            await interaction.followup.send("Error: Unable to build banned creations view.", ephemeral=True)
            return

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @moderation.command(name="creation_complaints", description="Get creation complaints with pagination")
    async def creation_complaints(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        view = CreationComplaintsListView(token=token, interaction=interaction, per_page=1)
        embed, error = await asyncio.to_thread(view.get_first_page_embed)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        if embed is None:
            await interaction.followup.send("Error: Unable to build creation complaints view.", ephemeral=True)
            return

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @moderation.command(name="player_complaints", description="Get player complaints with pagination")
    async def player_complaints(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        view = PlayerComplaintsListView(token=token, interaction=interaction, per_page=1)
        embed, error = await asyncio.to_thread(view.get_first_page_embed)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        if embed is None:
            await interaction.followup.send("Error: Unable to build player complaints view.", ephemeral=True)
            return

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @moderation.command(name="delete_player_creations", description="Remove all creations from a player")
    @app_commands.describe(username="Player username")
    async def delete_player_creations(self, interaction: discord.Interaction, username: str):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_remove_player_creations, token, username)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Player Creations Removed",
            f"All creations for **{username}** were removed.",
            discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @moderation.command(name="banned_console_ids", description="Get banned console IDs with pagination")
    async def banned_console_ids(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        view = BannedConsoleIdsListView(token=token, interaction=interaction)
        embed, error = await asyncio.to_thread(view.get_first_page_embed)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        if embed is None:
            await interaction.followup.send("Error: Unable to build banned console IDs view.", ephemeral=True)
            return

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @moderation.command(name="remove_banned_console_id", description="Remove a banned console ID")
    @app_commands.describe(console_id="Console ID to unban")
    async def remove_banned_console_id(self, interaction: discord.Interaction, console_id: str):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        normalized_console_id = normalize_console_id_input(console_id)

        result = await asyncio.to_thread(moderator_remove_banned_console_id, token, normalized_console_id)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Console ID Unbanned",
            f"Console ID `{normalized_console_id}` was removed from the banned list.",
            discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @moderation.command(name="ban_console_id_by_session", description="Ban a console ID from a player's active session")
    @app_commands.describe(username="Player username")
    async def ban_console_id_by_session(self, interaction: discord.Interaction, username: str):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        result = await asyncio.to_thread(moderator_ban_console_id_by_session, token, username)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Console ID Banned",
            f"Console ID for **{username}** active session was banned.",
            discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=False)
        
    # moderator management commands
    @moderation.command(name="create_moderator", description="Create a new moderator")
    @app_commands.describe(username="New moderator username")
    @app_commands.describe(password="New moderator password")
    async def create_moderator(self, interaction: discord.Interaction, username: str, password: str):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(create_moderator, token, username, password)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Moderator Created",
            f"Moderator **{username}** has been created.",
            discord.Color.green(),
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="delete_moderator", description="Remove a moderator")
    @app_commands.describe(username="Moderator username to remove")
    async def delete_moderator(self, interaction: discord.Interaction, username: str):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(delete_moderator, token, username)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Moderator Removed",
            f"Moderator **{username}** has been removed.",
            discord.Color.green(),
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="set_username", description="Set/changes your moderation account username")
    @app_commands.describe(username="New username for your moderation account")
    async def set_username(self, interaction: discord.Interaction, username: str):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_set_username, token, username)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Username Changed",
            f"Your moderation account username has been updated to **{username}**.",
            discord.Color.green(),
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
        
    @moderation.command(name="set_password", description="Set/changes your moderation account password")
    @app_commands.describe(password="New password for your moderation account")
    async def set_password(self, interaction: discord.Interaction, password: str):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        result = await asyncio.to_thread(moderator_set_password, token, password)
        if is_error_response(result):
            await self._send_followup_error(interaction, result)
            return

        embed = self._embed(
            interaction,
            "Password Changed",
            "Your moderation account password has been updated.",
            discord.Color.green(),
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=False,
        )
    
    @moderation.command(name="get_permissions", description="Get moderator permissions")
    async def get_permissions(self, interaction: discord.Interaction):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        await interaction.response.defer(ephemeral=True)

        permissions = await asyncio.to_thread(moderator_get_permissions, token)
        if is_error_response(permissions):
            await self._send_followup_error(interaction, permissions)
            return

        if not isinstance(permissions, dict):
            await self._send_followup_error(interaction, "Invalid permissions response.")
            return

        embed = self._embed(
            interaction,
            "Moderator Permissions",
            "",
            discord.Color.blue(),
        )

        description = []

        for permission in MODERATOR_PERMISSIONS:
            has_permission = permissions.get(permission, False)
            description.append(
                f"{'✅' if has_permission else '❌'} **{permission}**"
            )

        embed.description = "\n".join(description)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )
        
    @moderation.command(name="set_permissions", description="Set moderator permissions")
    @app_commands.describe(username="Moderator username")
    @app_commands.describe(action="Choose whether to grant or revoke selected permissions")
    async def set_permissions(
        self,
        interaction: discord.Interaction,
        username: str,
        action: Literal["grant", "revoke"],
    ):
        if not await self._require_moderator_role(interaction):
            return

        token = await self._require_moderator_token(interaction)
        if not token:
            return

        grant_value = action == "grant"
        view = PermissionSelectionView(
            token=token,
            target_username=username,
            grant_value=grant_value,
            requester_id=interaction.user.id,
        )

        embed = self._embed(
            interaction,
            "Select Permissions",
            f"Select one or more permissions to **{action}** for **{username}**.",
            discord.Color.blue(),
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
