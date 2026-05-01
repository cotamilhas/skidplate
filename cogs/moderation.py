import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import time
from typing import Optional, Any
from io import BytesIO
from config import EMBED_COLOR, URL, MODERATOR_ROLE_ID, MAX_QUOTA
from ui import (
    BanListPaginator,
    ComplaintsPaginator,
    BannedCreationsPaginator,
    ModeratorListPaginator,
    WhitelistPaginator,
    AnnouncementsPaginator,
    SystemEventsPaginator,
    HotlapQueuePaginator,
    ConfirmActionView
)
from ui.moderation_modals import (
    ModeratorLoginModal,
    ModeratorCreateModal,
    AnnouncementCreateModal,
    AnnouncementEditModal,
    SystemEventCreateModal,
    SystemEventEditModal,
    get_announcement_for_edit,
    get_system_event_for_edit,
)
from utils import (
    debug,
    PlayerDataFetcher,
    CreationDataFetcher,
    prepare_player_avatar_attachment,
    cleanup_temp_file,
    extract_creation_id,
    is_not_a_track_response,
    parse_hotlap_queue_payload,
    PLATFORM_LABELS,
    PERMISSION_LABELS,
    PERMISSION_ARGUMENT_MAP,
    DEFAULT_MODERATOR_PERMISSIONS,
    truncate_text,
    parse_paged_payload
)
from clients import ModerationAPIHelper

PLATFORM_CHOICES = [
    app_commands.Choice(name=label, value=value)
    for value, label in PLATFORM_LABELS.items()
]


async def _check_moderator_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Error",
                    description="This command can only be used in a server.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
        return False

    if not any(role.id == MODERATOR_ROLE_ID for role in interaction.user.roles):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Access Denied",
                    description=f"You need the <@&{MODERATOR_ROLE_ID}> role to use this command.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
        return False

    return True


def has_moderator_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        return await _check_moderator_role(interaction)

    return app_commands.check(predicate)


class Moderation(commands.Cog):
    moderators_group = app_commands.Group(
        name="mod",
        description="Moderator self-management commands (Moderator Only)"
    )
    players_group = app_commands.Group(
        name="players",
        description="Manage players (Moderator Only)"
    )
    creations_group = app_commands.Group(
        name="creations",
        description="Manage creations (Moderator Only)"
    )
    hotlap_group = app_commands.Group(
        name="hotlap",
        description="Manage the hotlap rotation (Moderator Only)"
    )
    announcements_group = app_commands.Group(
        name="announcements",
        description="Manage announcements (Moderator Only)"
    )
    whitelist_group = app_commands.Group(
        name="whitelist",
        description="Manage whitelist entries (Moderator Only)"
    )

    def __init__(self, bot):
        self.bot = bot
        self.session = bot.http_session
        self.moderation_session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())
        self.api_base = URL
        self.user_tokens: dict[int, str] = {}
        self.player_fetcher = PlayerDataFetcher(self.session, URL)
        self.creation_fetcher = CreationDataFetcher(self.session, URL)
        self.player_name_cache: dict[int, str] = {}
        self.creation_info_cache: dict[int, dict[str, str]] = {}
        self.creation_preview_cache: dict[int, bytes] = {}

        self.moderation_api = ModerationAPIHelper(
            session=self.moderation_session,
            api_base=self.api_base,
            user_tokens=self.user_tokens
        )

    async def cog_unload(self):
        await self.moderation_session.close()

    async def get_auth_headers(self, user_id: int) -> dict:
        return await self.moderation_api.get_auth_headers(user_id)

    async def api_request(self, method: str, endpoint: str, user_id: int, **kwargs):
        return await self.moderation_api.api_request(method, endpoint, user_id, **kwargs)

    @staticmethod
    def _embed(title: str, description: str, color: discord.Color) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=color)

    async def send_embed(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        description: str,
        color: discord.Color,
        ephemeral: bool = True
    ):
        await interaction.followup.send(
            embed=self._embed(title=title, description=description, color=color),
            ephemeral=ephemeral
        )

    async def send_error(self, interaction: discord.Interaction, message: str, ephemeral: bool = True):
        await self.send_embed(
            interaction,
            title="Error",
            description=message,
            color=discord.Color.red(),
            ephemeral=ephemeral
        )

    async def send_success(self, interaction: discord.Interaction, message: str, ephemeral: bool = True):
        await self.send_embed(
            interaction,
            title="Success",
            description=message,
            color=discord.Color.green(),
            ephemeral=ephemeral
        )

    async def _ensure_logged_in_or_error(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.user_tokens:
            return True

        embed = self._embed(
            title="Error",
            description=self.moderation_api.ERROR_LOGIN_REQUIRED,
            color=discord.Color.red()
        )

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    async def _resolve_player_id_or_error(self, interaction: discord.Interaction, username: str) -> Optional[str]:
        player_id = await self.player_fetcher.get_player_id(username)
        if player_id is None:
            await self.send_error(interaction, f"Player '{username}' not found.", ephemeral=True)
            return None
        return player_id

    async def _resolve_moderator_or_error(
        self,
        interaction: discord.Interaction,
        user_id: int,
        username: str
    ) -> Optional[dict[str, Any]]:
        mod_data, error = await self.find_moderator_by_username(user_id, username)
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return None
        if mod_data is None:
            await self.send_error(interaction, f"Moderator **{username}** not found", ephemeral=True)
            return None
        return mod_data

    async def _send_creation_status_embed(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        color: discord.Color,
        creation_id: int
    ):
        creation_info = await self.creation_fetcher.get_creation_info(creation_id)
        creation_name = creation_info.get("name", "Unknown") if creation_info else "Unknown"

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Name", value=f"**{creation_name}**", inline=True)
        embed.add_field(name="ID", value=f"`{creation_id}`", inline=True)

        preview_bytes = await self.get_creation_preview_bytes(creation_id)
        if preview_bytes:
            preview_file = discord.File(BytesIO(preview_bytes), filename="preview.png")
            embed.set_thumbnail(url="attachment://preview.png")
            await interaction.followup.send(embed=embed, file=preview_file, ephemeral=True)
            return

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def start_complaints_paginator(
        self,
        interaction: discord.Interaction,
        endpoint: str,
        mode: str,
        page: int
    ):
        if page < 1:
            await interaction.followup.send("Page must be 1 or higher.", ephemeral=True)
            return

        view = ComplaintsPaginator(
            moderation_cog=self,
            interaction_user_id=interaction.user.id,
            moderator_user_id=interaction.user.id,
            endpoint=endpoint,
            mode=mode,
            per_page=1,
            start_page=page
        )

        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        send_kwargs = {
            "embed": embed,
            "view": view,
            "ephemeral": True,
            "wait": True
        }
        if view.preview_attachment:
            send_kwargs["file"] = view.preview_attachment

        sent_message = await interaction.followup.send(**send_kwargs)
        view.message = sent_message

    async def get_moderators(self, user_id: int) -> tuple[list[dict[str, Any]], Optional[str]]:
        data, error = await self.api_request("GET", "/moderators", user_id, params={"page": 1, "per_page": 6})
        if error:
            return [], error

        moderators, _, is_valid = parse_paged_payload(data)
        if is_valid:
            return moderators, None
        return [], "Unexpected moderator list format."

    async def get_whitelist_entries(self, user_id: int, page: int = 1, per_page: int = 10) -> tuple[list[dict[str, Any]], Optional[int], Optional[str]]:
        data, error = await self.api_request("GET", "/whitelist", user_id, params={"page": page, "per_page": per_page})
        if error:
            return [], None, error

        entries, total, is_valid = parse_paged_payload(data)
        if is_valid:
            return entries, total, None
        return [], None, "Unexpected whitelist format."

    async def find_moderator_by_username(self, user_id: int, username: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        moderators, error = await self.get_moderators(user_id)
        if error:
            return None, error

        for moderator in moderators:
            if moderator.get("Username", "").lower() == username.lower():
                return moderator, None

        return None, None

    async def resolve_player_name(self, player_id: Any) -> str:
        if not isinstance(player_id, int):
            return "Unknown"

        cached = self.player_name_cache.get(player_id)
        if cached:
            return cached

        try:
            info = await self.player_fetcher.get_player_info(str(player_id))
            username = (
                (info or {}).get("username")
                or (info or {}).get("Username")
                or f"Unknown ({player_id})"
            )
        except Exception:
            username = f"Unknown ({player_id})"

        self.player_name_cache[player_id] = username
        return username

    async def resolve_player_avatar(self, player_id: Any) -> Optional[str]:
        if not isinstance(player_id, int):
            return None

        try:
            return await self.player_fetcher.get_player_avatar(str(player_id))
        except Exception:
            return None

    async def resolve_creation_info(self, creation_id: int) -> dict[str, str]:
        cached = self.creation_info_cache.get(creation_id)
        if cached:
            return cached

        info = await self.creation_fetcher.get_creation_info(creation_id) or {}
        resolved = {
            "name": info.get("name", "Unknown Creation"),
            "creator": info.get("username", "Unknown Creator"),
            "preview_url": f"{URL}player_creations/{creation_id}/preview_image.png",
        }
        self.creation_info_cache[creation_id] = resolved
        return resolved

    async def build_hotlap_embed(
        self,
        *,
        title: str,
        creation_id: Optional[int],
        color: discord.Color = EMBED_COLOR,
        footer: Optional[str] = None
    ) -> tuple[discord.Embed, Optional[discord.File]]:
        embed = discord.Embed(title=title, color=color)

        if not creation_id:
            embed.description = "No track is currently set."
            if footer:
                embed.set_footer(text=footer)
            return embed, None

        creation_info = await self.resolve_creation_info(creation_id)
        embed.add_field(name="Track", value=f"**{creation_info['name']}**", inline=True)
        embed.add_field(name="Creator", value=f"**{creation_info['creator']}**", inline=True)
        embed.add_field(name="ID", value=f"`{creation_id}`", inline=True)

        preview_bytes = await self.get_creation_preview_bytes(creation_id)
        preview_file = None
        if preview_bytes:
            preview_file = discord.File(BytesIO(preview_bytes), filename="preview.png")
            embed.set_thumbnail(url="attachment://preview.png")

        if footer:
            embed.set_footer(text=footer)

        return embed, preview_file

    async def send_hotlap_embed_response(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        creation_id: Optional[int],
        color: discord.Color = EMBED_COLOR,
        footer: Optional[str] = None
    ):
        embed, preview_file = await self.build_hotlap_embed(
            title=title,
            creation_id=creation_id,
            color=color,
            footer=footer
        )
        if preview_file:
            await interaction.followup.send(embed=embed, file=preview_file, ephemeral=True)
            return
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def get_creation_preview_bytes(self, creation_id: int) -> Optional[bytes]:
        cached = self.creation_preview_cache.get(creation_id)
        if cached is not None:
            return cached

        preview_url = f"{URL}player_creations/{creation_id}/preview_image.png"
        try:
            async with self.session.get(preview_url) as resp:
                if resp.status != 200:
                    return None

                preview_bytes = await resp.read()
                self.creation_preview_cache[creation_id] = preview_bytes
                return preview_bytes
        except Exception as e:
            debug(f"Failed to fetch cached preview image for {creation_id}: {e}")
            return None

    # ===== MODERATOR SELF MANAGEMENT =====
    @moderators_group.command(name="login", description="Connect as API moderator (opens a modal)")
    @has_moderator_role()
    async def mod_login(self, interaction: discord.Interaction):
        debug(f"mod_login called by {interaction.user}")
        await interaction.response.send_modal(ModeratorLoginModal(self))
            
    @moderators_group.command(name="create", description="Create a new moderator (opens a modal)")
    @has_moderator_role()
    async def mod_create(self, interaction: discord.Interaction):
        debug(f"mod_create called by {interaction.user}")
        if interaction.user.id not in self.user_tokens:
            await interaction.response.send_message(
                embed=self._embed(
                    title="Error",
                    description=self.moderation_api.ERROR_LOGIN_REQUIRED,
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return
        await interaction.response.send_modal(ModeratorCreateModal(self))

    @moderators_group.command(name="permissions", description="View your moderation permissions")
    @has_moderator_role()
    async def mod_perms(self, interaction: discord.Interaction):
        debug(f"mod_perms called by {interaction.user}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        data, error = await self.api_request("GET", "/permissions", user_id)
        debug(f"Permissions data: {data}, error: {error}")
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return
        
        embed = discord.Embed(title="Your Permissions", color=EMBED_COLOR)
        
        if isinstance(data, dict):
            for key, label in PERMISSION_LABELS.items():
                has_perm = data.get(key, False)
                status = "✅ Yes" if has_perm else "❌ No"
                debug(f"Permission {key}: {has_perm}")
                embed.add_field(name=label, value=status, inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @moderators_group.command(name="set-username", description="Change your moderator username")
    @app_commands.describe(username="New username")
    @has_moderator_role()
    async def mod_set_username(self, interaction: discord.Interaction, username: str):
        debug(f"mod_set_username called by {interaction.user} with username: {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        data, error = await self.api_request("POST", "/set_username", user_id, params={"username": username})
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Username changed to **{username}**", ephemeral=True)

    @moderators_group.command(name="set-password", description="Change your moderator password")
    @app_commands.describe(password="New password")
    @has_moderator_role()
    async def mod_set_password(self, interaction: discord.Interaction, password: str):
        debug(f"mod_set_password called by {interaction.user}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        data, error = await self.api_request("POST", "/set_password", user_id, data={"password": password})
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, "Password changed successfully", ephemeral=True)

    # ===== PLAYER MANAGEMENT =====
    @players_group.command(name="ban", description="Ban or unban a player")
    @app_commands.describe(username="Player username", ban="True to ban, False to unban")
    @has_moderator_role()
    async def ban_player(self, interaction: discord.Interaction, username: str, ban: bool):
        debug(f"ban_player called by {interaction.user} - username: {username}, ban: {ban}")
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        player_id = await self.player_fetcher.get_player_id(username)
        if player_id is None:
            await self.send_error(interaction, f"Player '{username}' not found")
            return

        debug(f"Found player ID {player_id} for username {username}")

        is_banned = "true" if ban else "false"
        data, error = await self.api_request("POST", "/setBan", user_id, params={"id": player_id, "isBanned": is_banned})

        if error:
            await self.send_error(interaction, error)
            return
        
        avatar_url = await self.player_fetcher.get_player_avatar(player_id)

        embed = discord.Embed(
            title="Player Banned" if ban else "Player Unbanned",
            color=discord.Color.red() if ban else discord.Color.green()
        )
        embed.add_field(name="Username", value=f"**{username}**", inline=True)
        embed.add_field(name="ID", value=f"`{player_id}`", inline=True)

        avatar_file, avatar_thumbnail_url, temp_avatar_path = await prepare_player_avatar_attachment(
            self.session,
            avatar_url,
            player_id
        )
        embed.set_thumbnail(url=avatar_thumbnail_url)

        try:
            await interaction.followup.send(embed=embed, file=avatar_file, ephemeral=True)
        finally:
            cleanup_temp_file(temp_avatar_path)

    @players_group.command(name="set-settings", description="Modify player settings")
    @app_commands.describe(
        username="Player username",
        show_no_previews="Show creations without previews",
        allow_opposite_platform="Allow players to connect to the opposite platform (PSN/RPCN)"
    )
    @has_moderator_role()
    async def set_player_settings(
        self,
        interaction: discord.Interaction,
        username: str,
        show_no_previews: Optional[bool] = None,
        allow_opposite_platform: Optional[bool] = None
    ):
        debug(f"set_player_settings called by {interaction.user} for {username}")
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        player_id = await self._resolve_player_id_or_error(interaction, username)
        if player_id is None:
            return

        params = {
            "id": player_id
        }
        
        if show_no_previews is None and allow_opposite_platform is None:
            embed = discord.Embed(
                title="No Changes",
                description="No settings were modified. Please specify at least one setting to change.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if show_no_previews is not None:
            params["ShowCreationsWithoutPreviews"] = str(show_no_previews).lower()

        if allow_opposite_platform is not None:
            params["AllowOppositePlatform"] = str(allow_opposite_platform).lower()

        data, error = await self.api_request(
            "POST",
            "/setUserSettings",
            user_id,
            params=params
        )

        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Settings updated for **{username}**", ephemeral=True)
        
    @players_group.command(name="set-quota", description="Change a player's creation quota")
    @app_commands.describe(username="Player username", quota=f"New quota (integer between 0 and {MAX_QUOTA})")
    @has_moderator_role()
    async def set_player_quota(self, interaction: discord.Interaction, username: str, quota: int):
        debug(f"set_player_quota called by {interaction.user} for {username} -> quota={quota}")
        await interaction.response.defer(ephemeral=True)

        if quota < 0 or quota > MAX_QUOTA:
            await self.send_error(interaction, f"Quota must be an integer between 0 and {MAX_QUOTA}.", ephemeral=True)
            return

        user_id = interaction.user.id

        player_id = await self._resolve_player_id_or_error(interaction, username)
        if player_id is None:
            return

        data, error = await self.api_request(
            "POST",
            "/setUserQuota",
            user_id,
            params={"id": player_id, "quota": quota}
        )

        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(
            interaction,
            f"Quota for **{username}** changed to **{quota}**.",
            ephemeral=True
        )
        
    @players_group.command(name="banned", description="List banned players")
    @has_moderator_role()
    async def banned_players(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = BanListPaginator(
            moderation_cog=self,
            interaction_user_id=interaction.user.id,
            moderator_user_id=interaction.user.id,
            start_page=1
        )

        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.message = sent_message
        
    @players_group.command(
        name="reset",
        description="Reset a player's profile stats (XP, wins, streaks, etc). Optionally delete their creations too."
    )
    @app_commands.describe(
        username="Player username",
        remove_creations="Also delete the player's creations"
    )
    @has_moderator_role()
    async def reset_player(
        self,
        interaction: discord.Interaction,
        username: str,
        remove_creations: bool = False
    ):
        debug(f"reset_player called by {interaction.user} for {username}, remove_creations={remove_creations}")
        if not await self._ensure_logged_in_or_error(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        player_id = await self._resolve_player_id_or_error(interaction, username)
        if player_id is None:
            return

        avatar_url = await self.player_fetcher.get_player_avatar(player_id)
        avatar_file, avatar_attach_url, temp_path = await prepare_player_avatar_attachment(
            self.session, avatar_url, player_id
        )

        embed = discord.Embed(
            title="Confirm: Reset Player Profile",
            description=(
                f"Are you sure you want to reset the profile stats for **{username}**?"
                f"\nRemove Creations: **{remove_creations}**"
                "\n\nThis action is **irreversible**."
            ),
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=avatar_attach_url)

        view = ConfirmActionView(invoker_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, file=avatar_file, view=view, ephemeral=True, wait=True)
        view.message = msg
        cleanup_temp_file(temp_path)

        await view.wait()

        if not view.confirmed:
            cancel_embed = discord.Embed(description="Action cancelled.", color=discord.Color.greyple())
            await msg.edit(embed=cancel_embed, attachments=[])
            return

        data, error = await self.api_request(
            "DELETE",
            f"/users/{player_id}/stats",
            user_id,
            params={"removeCreations": str(remove_creations).lower()},
        )
        debug(f"Reset player profile result: {data}, error: {error}")

        if error:
            error_embed = discord.Embed(description=f"Error: {error}", color=discord.Color.red())
            await msg.edit(embed=error_embed, attachments=[])
            return

        success_embed = discord.Embed(
            description=(
                f"Profile reset for **{username}**."
                f"\nRemove Creations: **{remove_creations}**"
            ),
            color=discord.Color.green()
        )
        await msg.edit(embed=success_embed, attachments=[])
        
    @players_group.command(
        name="delete",
        description="Delete a player account. This is NOT the same as reset."
    )
    @app_commands.describe(username="Player username")
    @has_moderator_role()
    async def delete_player(
        self,
        interaction: discord.Interaction,
        username: str
    ):
        debug(f"delete_player called by {interaction.user} for {username}")
        if not await self._ensure_logged_in_or_error(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        player_id = await self._resolve_player_id_or_error(interaction, username)
        if player_id is None:
            return

        avatar_url = await self.player_fetcher.get_player_avatar(player_id)
        avatar_file, avatar_attach_url, temp_path = await prepare_player_avatar_attachment(
            self.session, avatar_url, player_id
        )

        embed = discord.Embed(
            title="Confirm: Delete Player Account",
            description=(
                f"Are you sure you want to **permanently delete** the account of **{username}**?"
                "\n\nThis action is **irreversible**."
            ),
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=avatar_attach_url)

        view = ConfirmActionView(invoker_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, file=avatar_file, view=view, ephemeral=True, wait=True)
        view.message = msg
        cleanup_temp_file(temp_path)

        await view.wait()

        if not view.confirmed:
            cancel_embed = discord.Embed(description="Action cancelled.", color=discord.Color.greyple())
            await msg.edit(embed=cancel_embed, attachments=[])
            return

        data, error = await self.api_request(
            "DELETE",
            f"/users/{player_id}",
            user_id
        )
        debug(f"Remove user result: {data}, error: {error}")

        if error:
            error_embed = discord.Embed(description=f"Error: {error}", color=discord.Color.red())
            await msg.edit(embed=error_embed, attachments=[])
            return

        success_embed = discord.Embed(
            description=f"Player **{username}** was deleted.",
            color=discord.Color.green()
        )
        await msg.edit(embed=success_embed, attachments=[])
        
    # ===== PLAYER CREATION MANAGEMENT =====
    @creations_group.command(name="ban", description="Ban or approve a creation")
    @app_commands.describe(creation_id="Creation ID", banned="True to ban, False to approve")
    @has_moderator_role()
    async def creation_set_status(self, interaction: discord.Interaction, creation_id: int, banned: bool):
        debug(f"creation_set_status called by {interaction.user} - creation_id: {creation_id}, banned: {banned}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        status = "BANNED" if banned else "APPROVED"
        data, error = await self.api_request("POST", "/setStatus", user_id, params={"id": creation_id, "status": status})
        debug(f"Set status result: {data}, error: {error}")
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        debug(f"Creation {creation_id} status changed to {status}")
        await self._send_creation_status_embed(
            interaction,
            title="Creation Banned" if banned else "Creation Approved",
            color=discord.Color.red() if banned else discord.Color.green(),
            creation_id=creation_id
        )
        
    @creations_group.command(name="reset", description="Reset a creation's stats")
    @app_commands.describe(creation_id="Creation ID to reset stats for")
    @has_moderator_role()
    async def reset_creation(self, interaction: discord.Interaction, creation_id: int):
        debug(f"reset_creation called by {interaction.user} - creation_id: {creation_id}")
        if not await self._ensure_logged_in_or_error(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        creation_info = await self.creation_fetcher.get_creation_info(creation_id)
        creation_name = creation_info.get("name", "Unknown") if creation_info else "Unknown"

        embed = discord.Embed(
            title="Confirm: Reset Creation Stats",
            description=(
                f"Are you sure you want to reset all stats for **{creation_name}** (ID `{creation_id}`)?"
                "\n\nThis action is **irreversible**."
            ),
            color=discord.Color.orange()
        )

        preview_bytes = await self.get_creation_preview_bytes(creation_id)
        files = []
        if preview_bytes:
            embed.set_thumbnail(url="attachment://preview.png")
            files = [discord.File(BytesIO(preview_bytes), filename="preview.png")]

        view = ConfirmActionView(invoker_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, files=files, view=view, ephemeral=True, wait=True)
        view.message = msg

        await view.wait()

        if not view.confirmed:
            cancel_embed = discord.Embed(description="Action cancelled.", color=discord.Color.greyple())
            await msg.edit(embed=cancel_embed, attachments=[])
            return

        data, error = await self.api_request(
            "DELETE",
            f"/player_creations/{creation_id}/stats",
            user_id,
        )
        debug(f"Reset creation stats result: {data}, error: {error}")

        if error:
            error_embed = discord.Embed(description=f"Error: {error}", color=discord.Color.red())
            await msg.edit(embed=error_embed, attachments=[])
            return

        success_embed = discord.Embed(
            description=f"Stats reset for **{creation_name}** (ID `{creation_id}`).",
            color=discord.Color.green()
        )
        await msg.edit(embed=success_embed, attachments=[])
        
    @creations_group.command(name="banned", description="List banned creations")
    @has_moderator_role()
    async def banned_creations(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = BannedCreationsPaginator(
            moderation_cog=self,
            interaction_user_id=interaction.user.id,
            moderator_user_id=interaction.user.id,
            per_page=10,
            start_page=1
        )
        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.message = sent_message
        
    @creations_group.command(
        name="delete",
        description="Delete ALL creations from a player (does not delete the user)."
    )
    @app_commands.describe(username="Player username")
    @has_moderator_role()
    async def delete_player_creations(
        self,
        interaction: discord.Interaction,
        username: str
    ):
        debug(f"delete_player_creations called by {interaction.user} for {username}")
        if not await self._ensure_logged_in_or_error(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        player_id = await self._resolve_player_id_or_error(interaction, username)
        if player_id is None:
            return

        avatar_url = await self.player_fetcher.get_player_avatar(player_id)
        avatar_file, avatar_attach_url, temp_path = await prepare_player_avatar_attachment(
            self.session, avatar_url, player_id
        )

        embed = discord.Embed(
            title="Confirm: Delete All Player Creations",
            description=(
                f"Are you sure you want to delete **all creations** from **{username}**?"
                "\n\nThis action is **irreversible**."
            ),
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=avatar_attach_url)

        view = ConfirmActionView(invoker_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, file=avatar_file, view=view, ephemeral=True, wait=True)
        view.message = msg
        cleanup_temp_file(temp_path)

        await view.wait()

        if not view.confirmed:
            cancel_embed = discord.Embed(description="Action cancelled.", color=discord.Color.greyple())
            await msg.edit(embed=cancel_embed, attachments=[])
            return

        data, error = await self.api_request(
            "DELETE",
            f"/users/{player_id}/creations",
            user_id
        )
        debug(f"Remove player creations result: {data}, error: {error}")

        if error:
            error_embed = discord.Embed(description=f"Error: {error}", color=discord.Color.red())
            await msg.edit(embed=error_embed, attachments=[])
            return

        success_embed = discord.Embed(
            description=f"All creations from **{username}** were deleted.",
            color=discord.Color.green()
        )
        await msg.edit(embed=success_embed, attachments=[])
        
    # ===== PLAYER/CREATION REPORTS & COMPLAINTS =====
    @players_group.command(name="complaints", description="View player complaints with pagination")
    @app_commands.describe(page="Page number to open")
    @has_moderator_role()
    async def player_complaints(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer(ephemeral=True)
        await self.start_complaints_paginator(interaction, "/player_complaints", "player", page)

    @creations_group.command(name="complaints", description="View creation complaints with pagination")
    @app_commands.describe(page="Page number to open")
    @has_moderator_role()
    async def creation_complaints(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer(ephemeral=True)
        await self.start_complaints_paginator(interaction, "/player_creation_complaints", "creation", page)
        
    # ===== HOTLAP MANAGEMENT =====
    @hotlap_group.command(name="get", description="Show current hotlap track")
    @has_moderator_role()
    async def get_hotlap(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        data, error = await self.api_request('GET', '/hotlap', user_id)
        if error:
            await self.send_error(interaction, error)
            return

        creation_id = extract_creation_id(data)
        await self.send_hotlap_embed_response(
            interaction,
            title='Current Hotlap',
            creation_id=creation_id
        )

    @hotlap_group.command(name="set", description="Set hotlap by creation ID")
    @app_commands.describe(creation_id="Creation ID to set as hotlap")
    @has_moderator_role()
    async def set_hotlap(self, interaction: discord.Interaction, creation_id: int):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        data, error = await self.api_request('POST', '/hotlap', user_id, params={"creation": creation_id})
        if error:
            await self.send_error(interaction, error)
            return

        if is_not_a_track_response(data):
            await self.send_error(interaction, f"Creation `{creation_id}` is not a track.")
            return

        await self.send_hotlap_embed_response(
            interaction,
            title='Hotlap Updated',
            creation_id=creation_id,
            color=discord.Color.green(),
            footer=f"Set by {interaction.user.display_name}"
        )

    @hotlap_group.command(name="reset", description="Reset the current hotlap")
    @has_moderator_role()
    async def reset_hotlap(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        data, error = await self.api_request('POST', '/hotlap/reset', user_id)
        if error:
            await self.send_error(interaction, error)
            return
        embed = discord.Embed(
            title='Hotlap Reset',
            description='The current hotlap has been reset.',
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Reset by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @hotlap_group.command(name="until-next", description="Get time until next hotlap")
    @has_moderator_role()
    async def hotlap_until_next(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        data, error = await self.api_request('GET', '/hotlap/until_next', user_id)
        if error:
            await self.send_error(interaction, error)
            return

        try:
            seconds_remaining = max(0, int(float(str(data).strip())))
        except (TypeError, ValueError):
            await self.send_error(interaction, f"Invalid hotlap timer value: {data}")
            return

        next_hotlap_timestamp = int(time.time()) + seconds_remaining
        embed = discord.Embed(title='Hotlap Rotation', color=EMBED_COLOR)
        embed.add_field(
            name='Time Until Next',
            value=(
                f"<t:{next_hotlap_timestamp}:f>\n"
                f"(<t:{next_hotlap_timestamp}:R>)"
            ),
            inline=False,
        )

        current_data, current_error = await self.api_request('GET', '/hotlap', user_id)
        if not current_error:
            creation_id = extract_creation_id(current_data)
            if creation_id:
                creation_info = await self.resolve_creation_info(creation_id)
                embed.add_field(name='Current Track', value=f"**{creation_info['name']}**", inline=True)
                embed.add_field(name='Creator', value=f"**{creation_info['creator']}**", inline=True)
                embed.add_field(name='ID', value=f"`{creation_id}`", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @hotlap_group.command(name="queue", description="List the hotlap queue")
    @app_commands.describe(page="Page number")
    @has_moderator_role()
    async def hotlap_queue(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer(ephemeral=True)
        view = HotlapQueuePaginator(
            moderation_cog=self,
            interaction_user_id=interaction.user.id,
            moderator_user_id=interaction.user.id,
            start_page=page
        )

        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.message = sent_message

    @hotlap_group.command(name="queue-add", description="Add a creation to the hotlap queue")
    @app_commands.describe(creation_id="Creation ID to add to queue")
    @has_moderator_role()
    async def hotlap_queue_add(self, interaction: discord.Interaction, creation_id: int):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        data, error = await self.api_request('POST', '/hotlap/queue', user_id, params={"creation": creation_id})
        if error:
            await self.send_error(interaction, error)
            return

        if is_not_a_track_response(data):
            await self.send_error(interaction, f"Creation `{creation_id}` is not a track.")
            return

        await self.send_hotlap_embed_response(
            interaction,
            title='Track Added To Hotlap Queue',
            creation_id=creation_id,
            color=discord.Color.green(),
            footer=f"Added by {interaction.user.display_name}"
        )

    @hotlap_group.command(name="queue-remove", description="Remove a creation from the hotlap queue by index or creation ID")
    @app_commands.describe(index="Queue index to remove", creation_id="Creation ID to remove")
    @has_moderator_role()
    async def hotlap_queue_remove(self, interaction: discord.Interaction, index: Optional[int] = None, creation_id: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        if index is None and creation_id is None:
            await self.send_error(interaction, 'Provide either index or creation_id.')
            return
        if index is not None and creation_id is not None:
            await self.send_error(interaction, 'Provide either index or creation_id, not both.')
            return
        user_id = interaction.user.id
        data, error = await self.api_request('DELETE', '/hotlap/queue', user_id, params={'index': index, 'creation': creation_id})
        if error:
            await self.send_error(interaction, error)
            return
        await self.send_success(interaction, 'Hotlap removed from queue.')
        
    # ===== ANNOUNCEMENTS =====
    @announcements_group.command(name="list", description="List announcements")
    @app_commands.describe(page="Page (default: 1)", platform="Platform (optional)")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    @has_moderator_role()
    async def announce_list(
        self,
        interaction: discord.Interaction,
        page: int = 1,
        platform: Optional[app_commands.Choice[int]] = None
    ):
        await interaction.response.defer(ephemeral=True)
        view = AnnouncementsPaginator(
            moderation_cog=self,
            interaction_user_id=interaction.user.id,
            moderator_user_id=interaction.user.id,
            start_page=page,
            platform=platform.value if platform else None
        )

        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.message = sent_message

    @announcements_group.command(name="create", description="Create an announcement (opens a modal)")
    @has_moderator_role()
    async def announce_create(
        self,
        interaction: discord.Interaction
    ):
        if interaction.user.id not in self.user_tokens:
            await interaction.response.send_message(
                embed=self._embed(
                    title="Error",
                    description=self.moderation_api.ERROR_LOGIN_REQUIRED,
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return
        await interaction.response.send_modal(AnnouncementCreateModal(self))

    @announcements_group.command(name="edit", description="Edit an announcement (opens a modal)")
    @app_commands.describe(announcement_id="Announcement ID")
    @has_moderator_role()
    async def announce_edit(
        self,
        interaction: discord.Interaction,
        announcement_id: int
    ):
        if interaction.user.id not in self.user_tokens:
            await interaction.response.send_message(
                embed=self._embed(
                    title="Error",
                    description=self.moderation_api.ERROR_LOGIN_REQUIRED,
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        announcement_data, fetch_error = await get_announcement_for_edit(
            self,
            user_id,
            announcement_id,
            None
        )

        if fetch_error == "Announcement not found.":
            await interaction.response.send_message(
                embed=self._embed(
                    title="Error",
                    description=f"Announcement `{announcement_id}` was not found.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        initial_subject: Optional[str] = None
        initial_text: Optional[str] = None
        initial_platform: Optional[str] = None
        if announcement_data:
            initial_subject = truncate_text(
                announcement_data.get("Subject", announcement_data.get("subject", "")),
                120,
                ""
            )
            initial_text = truncate_text(
                announcement_data.get("Text", announcement_data.get("text", "")),
                1900,
                ""
            )
            platform_value = announcement_data.get("Platform", announcement_data.get("platform"))
            if isinstance(platform_value, int):
                initial_platform = str(platform_value)
            elif isinstance(platform_value, str):
                initial_platform = platform_value.strip()

        if fetch_error and fetch_error != "Announcement not found.":
            debug(
                f"announce_edit prefill failed for announcement {announcement_id}: {fetch_error}. "
                "Opening modal without prefilled values."
            )

        await interaction.response.send_modal(
            AnnouncementEditModal(
                self,
                announcement_id,
                initial_platform=initial_platform,
                initial_subject=initial_subject,
                initial_text=initial_text
            )
        )

    @announcements_group.command(name="delete", description="Delete an announcement")
    @app_commands.describe(announcement_id="Announcement ID")
    @has_moderator_role()
    async def announce_delete(self, interaction: discord.Interaction, announcement_id: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        data, error = await self.api_request("DELETE", f"/announcements/{announcement_id}", user_id)
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Announcement `{announcement_id}` deleted.", ephemeral=True)
        
    # # ===== SYSTEM EVENTS =====
    # @app_commands.command(name="sysmsg_list", description="List system messages (system events)")
    # @app_commands.describe(page="Page (default: 1)")
    # @has_moderator_role()
    # async def sysmsg_list(self, interaction: discord.Interaction, page: int = 1):
    #     await interaction.response.defer(ephemeral=True)
    #     view = SystemEventsPaginator(
    #         moderation_cog=self,
    #         interaction_user_id=interaction.user.id,
    #         moderator_user_id=interaction.user.id,
    #         start_page=page
    #     )

    #     embed, error = await view.initialize()
    #     if error:
    #         await self.send_error(interaction, error, ephemeral=True)
    #         return

    #     sent_message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
    #     view.message = sent_message

    # @app_commands.command(name="sysmsg_create", description="Create a system event (opens a modal)")
    # @has_moderator_role()
    # async def sysmsg_create(self, interaction: discord.Interaction):
    #     if interaction.user.id not in self.user_tokens:
    #         await interaction.response.send_message(
    #             embed=self._embed(
    #                 title="Error",
    #                 description=self.moderation_api.ERROR_LOGIN_REQUIRED,
    #                 color=discord.Color.red()
    #             ),
    #             ephemeral=True
    #         )
    #         return
    #     await interaction.response.send_modal(SystemEventCreateModal(self))

    # @app_commands.command(name="sysmsg_edit", description="Edit a system event (opens a modal)")
    # @app_commands.describe(event_id="System event ID")
    # @has_moderator_role()
    # async def sysmsg_edit(
    #     self,
    #     interaction: discord.Interaction,
    #     event_id: int
    # ):
    #     if interaction.user.id not in self.user_tokens:
    #         await interaction.response.send_message(
    #             embed=self._embed(
    #                 title="Error",
    #                 description=self.moderation_api.ERROR_LOGIN_REQUIRED,
    #                 color=discord.Color.red()
    #             ),
    #             ephemeral=True
    #         )
    #         return

    #     user_id = interaction.user.id
    #     event_data, fetch_error = await get_system_event_for_edit(self, user_id, event_id)

    #     if fetch_error == "System event not found.":
    #         await interaction.response.send_message(
    #             embed=self._embed(
    #                 title="Error",
    #                 description=f"System event `{event_id}` was not found.",
    #                 color=discord.Color.red()
    #             ),
    #             ephemeral=True
    #         )
    #         return

    #     initial_topic: Optional[str] = None
    #     initial_description: Optional[str] = None
    #     initial_image_url: Optional[str] = None
    #     if event_data:
    #         initial_topic = truncate_text(
    #             event_data.get("Topic", event_data.get("topic", "")),
    #             120,
    #             ""
    #         )
    #         initial_description = truncate_text(
    #             event_data.get("Description", event_data.get("description", "")),
    #             1900,
    #             ""
    #         )
    #         initial_image_url = truncate_text(
    #             event_data.get("ImageURL", event_data.get("imageURL", event_data.get("image_url", ""))),
    #             500,
    #             ""
    #         )

    #     if fetch_error and fetch_error != "System event not found.":
    #         debug(
    #             f"sysmsg_edit prefill failed for event {event_id}: {fetch_error}. "
    #             "Opening modal without prefilled values."
    #         )

    #     await interaction.response.send_modal(
    #         SystemEventEditModal(
    #             self,
    #             event_id,
    #             initial_topic=initial_topic,
    #             initial_description=initial_description,
    #             initial_image_url=initial_image_url
    #         )
    #     )

    # @app_commands.command(name="sysmsg_delete", description="Delete a system event")
    # @app_commands.describe(event_id="System event ID")
    # @has_moderator_role()
    # async def sysmsg_delete(self, interaction: discord.Interaction, event_id: int):
    #     await interaction.response.defer(ephemeral=True)
    #     user_id = interaction.user.id

    #     data, error = await self.api_request("DELETE", f"/system_events/{event_id}", user_id)
    #     if error:
    #         await self.send_error(interaction, error, ephemeral=True)
    #         return

    #     await self.send_success(interaction, f"System event `{event_id}` deleted.", ephemeral=True)
        
    # ===== WHITELIST MANAGEMENT =====
    @whitelist_group.command(name="list", description="List whitelist entries")
    @app_commands.describe(page="Page (default: 1)")
    @has_moderator_role()
    async def whitelist_list(self, interaction: discord.Interaction, page: int = 1):
        debug(f"whitelist_list called by {interaction.user}")
        await interaction.response.defer(ephemeral=True)

        view = WhitelistPaginator(
            moderation_cog=self,
            interaction_user_id=interaction.user.id,
            moderator_user_id=interaction.user.id,
            start_page=page
        )

        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.message = sent_message

    @whitelist_group.command(name="add", description="Add a username to the whitelist")
    @app_commands.describe(username="Username to whitelist")
    @has_moderator_role()
    async def whitelist_add(self, interaction: discord.Interaction, username: str):
        debug(f"whitelist_add called by {interaction.user} for {username}")
        await interaction.response.defer(ephemeral=True)

        data, error = await self.api_request("POST", "/whitelist", interaction.user.id, params={"username": username})
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        message = f"Added **{username}** to the whitelist."
        await self.send_success(interaction, message, ephemeral=True)

    @whitelist_group.command(name="update", description="Rename a whitelist username")
    @app_commands.describe(old_username="Current whitelisted username", new_username="New username")
    @has_moderator_role()
    async def whitelist_update(self, interaction: discord.Interaction, old_username: str, new_username: str):
        debug(f"whitelist_update called by {interaction.user} for {old_username} -> {new_username}")
        await interaction.response.defer(ephemeral=True)

        data, error = await self.api_request(
            "PATCH",
            "/whitelist",
            interaction.user.id,
            params={"oldUsername": old_username, "newUsername": new_username}
        )
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        message = f"Updated whitelist username from **{old_username}** to **{new_username}**."
        await self.send_success(interaction, message, ephemeral=True)

    @whitelist_group.command(name="remove", description="Remove a username from the whitelist")
    @app_commands.describe(username="Username to remove from the whitelist")
    @has_moderator_role()
    async def whitelist_remove(self, interaction: discord.Interaction, username: str):
        debug(f"whitelist_remove called by {interaction.user} for {username}")
        await interaction.response.defer(ephemeral=True)

        data, error = await self.api_request("DELETE", "/whitelist", interaction.user.id, params={"username": username})
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        message = f"Removed **{username}** from the whitelist."
        await self.send_success(interaction, message, ephemeral=True)
    
    # ===== MODERATOR MANAGEMENT =====
    @moderators_group.command(name="list", description="List all moderators")
    @app_commands.describe(page="Page (default: 1)")
    @has_moderator_role()
    async def mod_list(self, interaction: discord.Interaction, page: int = 1):
        debug(f"mod_list called by {interaction.user}")
        await interaction.response.defer(ephemeral=True)

        view = ModeratorListPaginator(
            moderation_cog=self,
            interaction_user_id=interaction.user.id,
            moderator_user_id=interaction.user.id,
            start_page=page
        )

        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        sent_message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        view.message = sent_message

    @moderators_group.command(name="get", description="Get specific moderator details")
    @app_commands.describe(username="Moderator username")
    @has_moderator_role()
    async def mod_get(self, interaction: discord.Interaction, username: str):
        debug(f"mod_get called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        try:
            mod_data = await self._resolve_moderator_or_error(interaction, user_id, username)
            if mod_data is None:
                return
            
            mod_id = mod_data.get("ID", "?")
            embed = discord.Embed(title=f"Moderator: {username}", color=discord.Color.blue())
            
            embed.add_field(name="ID", value=str(mod_id), inline=False)
            embed.add_field(name="Username", value=f"**{username}**", inline=False)
            
            perms_list = []

            for key, label in PERMISSION_LABELS.items():
                if mod_data.get(key, False):
                    perms_list.append(label)
            
            if perms_list:
                embed.add_field(name="Permissions", value="\n".join(f"✅ {p}" for p in perms_list), inline=False)
            else:
                embed.add_field(name="Permissions", value="No permissions granted", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            debug(f"Error in mod_get: {str(e)}")
            await self.send_error(interaction, f"```{str(e)}```", ephemeral=True)

    @moderators_group.command(name="set-permissions", description="Update moderator permissions")
    @app_commands.describe(
        username="Moderator username",
        permission="Permission to update",
        enabled="True to grant, False to revoke"
    )
    @app_commands.choices(permission=[
        app_commands.Choice(name=label, value=key)
        for key, label in PERMISSION_LABELS.items()
    ])
    @has_moderator_role()
    async def mod_set_permissions(
        self,
        interaction: discord.Interaction,
        username: str,
        permission: app_commands.Choice[str],
        enabled: bool
    ):
        debug(f"mod_set_permissions called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        mod_data = await self._resolve_moderator_or_error(interaction, user_id, username)
        if mod_data is None:
            return

        mod_id = mod_data.get("ID")

        permissions_params = {
            api_field: str(bool(mod_data.get(api_field, False))).lower()
            for api_field in PERMISSION_ARGUMENT_MAP
        }
        permissions_params[permission.value] = str(enabled).lower()

        data, error = await self.api_request(
            "POST",
            f"/{mod_id}/set_permissions", user_id,
            params=permissions_params
        )

        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        permission_label = PERMISSION_LABELS.get(permission.value, permission.value)
        action = "granted" if enabled else "revoked"
        await self.send_success(
            interaction,
            f"{permission_label} {action} for moderator **{username}**",
            ephemeral=True
        )

    @moderators_group.command(name="delete", description="Delete a moderator")
    @app_commands.describe(username="Moderator username")
    @has_moderator_role()
    async def mod_delete(self, interaction: discord.Interaction, username: str):
        debug(f"mod_delete called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        mod_data = await self._resolve_moderator_or_error(interaction, user_id, username)
        if mod_data is None:
            return

        mod_id = mod_data.get("ID")
        
        data, error = await self.api_request("DELETE", f"/moderators/{mod_id}", user_id)
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Moderator **{username}** deleted", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))