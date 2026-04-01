import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from typing import Optional, Any
import os
from io import BytesIO
from config import EMBED_COLOR, URL, MODERATOR_ROLE_ID, MAX_QUOTA
from utils import (
    debug,
    PlayerDataFetcher,
    CreationDataFetcher,
    prepare_player_avatar_attachment,
    cleanup_temp_file,
)
from clients import ModerationAPIHelper


PERMISSION_LABELS = {
    "ManageModerators": "Manage Moderators",
    "BanUsers": "Ban Players",
    "ChangeUserSettings": "Change Settings",
    "ChangeCreationStatus": "Change Creation Status",
    "ManageAnnouncements": "Manage Announcements",
    "ManageHotlap": "Manage Hotlap",
    "ManageSystemEvents": "Manage System Events",
    "ViewGriefReports": "View Grief Reports",
    "ViewPlayerComplaints": "View Player Complaints",
    "ViewPlayerCreationComplaints": "View Creation Complaints",
    "ChangeUserQuota": "Change User Quota",
}

PERMISSION_ARGUMENT_MAP = {
    "BanUsers": "ban_users",
    "ChangeCreationStatus": "change_creation_status",
    "ChangeUserSettings": "change_user_settings",
    "ViewGriefReports": "view_grief_reports",
    "ViewPlayerComplaints": "view_player_complaints",
    "ViewPlayerCreationComplaints": "view_player_creation_complaints",
    "ManageModerators": "manage_moderators",
    "ManageAnnouncements": "manage_announcements",
    "ManageHotlap": "manage_hotlap",
    "ManageSystemEvents": "manage_system_events",
    "ChangeUserQuota": "change_user_quota",
}

DEFAULT_MODERATOR_PERMISSIONS = {
    permission: False for permission in PERMISSION_ARGUMENT_MAP
}


def has_moderator_role():
    async def predicate(interaction: discord.Interaction) -> bool:
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
    
    return app_commands.check(predicate)


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


class Moderation(commands.Cog):
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
        
        self.logs_dir = "api_logs"
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)

        self.moderation_api = ModerationAPIHelper(
            session=self.moderation_session,
            api_base=self.api_base,
            logs_dir=self.logs_dir,
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
        ephemeral: bool = True,
    ):
        await interaction.followup.send(
            embed=self._embed(title=title, description=description, color=color),
            ephemeral=ephemeral,
        )

    async def send_error(self, interaction: discord.Interaction, message: str, ephemeral: bool = True):
        await self.send_embed(
            interaction,
            title="Error",
            description=message,
            color=discord.Color.red(),
            ephemeral=ephemeral,
        )

    async def send_success(self, interaction: discord.Interaction, message: str, ephemeral: bool = True):
        await self.send_embed(
            interaction,
            title="Success",
            description=message,
            color=discord.Color.green(),
            ephemeral=ephemeral,
        )

    async def start_complaints_paginator(
        self,
        interaction: discord.Interaction,
        endpoint: str,
        mode: str,
        page: int,
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
            start_page=page,
        )

        embed, error = await view.initialize()
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        send_kwargs = {
            "embed": embed,
            "view": view,
            "ephemeral": True,
            "wait": True,
        }
        if view.preview_attachment:
            send_kwargs["file"] = view.preview_attachment

        sent_message = await interaction.followup.send(**send_kwargs)
        view.message = sent_message

    async def get_moderators(self, user_id: int) -> tuple[list[dict[str, Any]], Optional[str]]:
        data, error = await self.api_request("GET", "/moderators", user_id, params={"page": 1, "per_page": 1000})
        if error:
            return [], error

        if isinstance(data, list):
            return data, None
        if isinstance(data, dict):
            return data.get("Page", []), None
        return [], "Unexpected moderator list format."

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
            "preview_url": f"{URL}player_creations/{creation_id}/preview_image.png",
        }
        self.creation_info_cache[creation_id] = resolved
        return resolved

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
    @app_commands.command(name="mod_login", description="Connect as API moderator")
    @app_commands.describe(username="Moderator username", password="Moderator password")
    @has_moderator_role()
    async def mod_login(self, interaction: discord.Interaction, username: str, password: str):
        debug(f"mod_login called by {interaction.user}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        try:
            url = f"{self.api_base}api/moderation/login"
            debug(f"Login attempt to: {url}")
            async with self.moderation_session.post(url, data={"login": username, "password": password}) as resp:
                debug(f"Login response status: {resp.status}")
                text = await resp.text()
                
                if resp.status == 200 and text == "ok":
                    cookies = resp.cookies
                    if 'Token' in cookies:
                        token = cookies['Token'].value
                        self.user_tokens[user_id] = token
                        debug(f"Token received for user {user_id}: {token[:10]}...")
                        await self.send_success(interaction, f"Connected as **{username}**", ephemeral=True)
                    else:
                        debug("No token in response cookies")
                        await self.send_embed(
                            interaction,
                            title="Login Failed",
                            description="Server did not provide token",
                            color=discord.Color.red(),
                            ephemeral=True,
                        )
                else:
                    debug(f"Login failed with status {resp.status}")
                    await self.send_embed(
                        interaction,
                        title="Login Failed",
                        description="Invalid username or password",
                        color=discord.Color.red(),
                        ephemeral=True,
                    )
        except Exception as e:
            debug(f"Login exception: {str(e)}")
            await self.send_error(interaction, f"```{str(e)}```", ephemeral=True)
            
    @app_commands.command(name="mod_create", description="Create a new moderator")
    @app_commands.describe(username="New moderator username", password="New moderator password")
    @has_moderator_role()
    async def mod_create(self, interaction: discord.Interaction, username: str, password: str):
        debug(f"mod_create called by {interaction.user} for username: {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        try:    
            permissions = DEFAULT_MODERATOR_PERMISSIONS.copy()
            
            data, error = await self.api_request("POST", "/moderators", user_id,
                                                params={"username": username, "password": password},
                                                json=permissions)
            
            if error:
                await self.send_error(interaction, error, ephemeral=True)
                return

            await self.send_success(interaction, f"Moderator **{username}** created successfully", ephemeral=True)
            debug(f"Moderator {username} created by {interaction.user.name}")
            
        except Exception as e:
            debug(f"Error creating moderator: {str(e)}")
            await self.send_error(interaction, f"```{str(e)}```", ephemeral=True)

    @app_commands.command(name="mod_perms", description="View your moderation permissions")
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

    @app_commands.command(name="mod_set_username", description="Change your moderator username")
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

    @app_commands.command(name="mod_set_password", description="Change your moderator password")
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
    @app_commands.command(name="ban_player", description="Ban or unban player")
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
            player_id,
        )
        embed.set_thumbnail(url=avatar_thumbnail_url)

        try:
            await interaction.followup.send(embed=embed, file=avatar_file, ephemeral=True)
        finally:
            cleanup_temp_file(temp_avatar_path)

    @app_commands.command(name="set_player_settings", description="Modify player settings (show no previews, allow opposite platform)")
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
        player_id = await self.player_fetcher.get_player_id(username)

        if player_id is None:
            await self.send_error(interaction, f"Player '{username}' not found", ephemeral=True)
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
        
    @app_commands.command(name="set_player_quota", description="Change a player's creation quota")
    @app_commands.describe(username="Player username", quota=f"New quota (integer between 0 and {MAX_QUOTA})")
    @has_moderator_role()
    async def set_player_quota(self, interaction: discord.Interaction, username: str, quota: int):
        debug(f"set_player_quota called by {interaction.user} for {username} -> quota={quota}")
        await interaction.response.defer(ephemeral=True)

        if quota < 0 or quota > MAX_QUOTA:
            await self.send_error(interaction, f"Quota must be an integer between 0 and {MAX_QUOTA}.", ephemeral=True)
            return

        user_id = interaction.user.id

        player_id = await self.player_fetcher.get_player_id(username)
        if player_id is None:
            await self.send_error(interaction, f"Player '{username}' was not found.", ephemeral=True)
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
            f"Quota for **{username}** (ID `{player_id}`) changed to **{quota}**.",
            ephemeral=True,
        )
        
    # ===== PLAYER CREATION MANAGEMENT =====
    @app_commands.command(name="ban_creation", description="Ban or approve a creation")
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
        
        creation_info = await self.creation_fetcher.get_creation_info(creation_id)
        creation_name = creation_info.get("name", "Unknown") if creation_info else "Unknown"
        
        debug(f"Creation {creation_id} status changed to {status}")
        embed = discord.Embed(
            title="Creation Banned" if banned else "Creation Approved",
            color=discord.Color.red() if banned else discord.Color.green()
        )
        embed.add_field(name="Name", value=f"**{creation_name}**", inline=True)
        embed.add_field(name="ID", value=f"`{creation_id}`", inline=True)
        
        preview_bytes = await self.get_creation_preview_bytes(creation_id)
        if preview_bytes:
            preview_file = discord.File(BytesIO(preview_bytes), filename="preview.png")
            embed.set_thumbnail(url="attachment://preview.png")
            await interaction.followup.send(embed=embed, file=preview_file, ephemeral=True)
            return
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    # ===== PLAYER/CREATION REPORTS & COMPLAINTS =====
    @app_commands.command(name="player_complaints", description="View player complaints with pagination")
    @app_commands.describe(page="Page number to open")
    @has_moderator_role()
    async def player_complaints(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer(ephemeral=True)
        await self.start_complaints_paginator(interaction, "/player_complaints", "player", page)

    @app_commands.command(name="creation_complaints", description="View creation complaints with pagination")
    @app_commands.describe(page="Page number to open")
    @has_moderator_role()
    async def creation_complaints(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer(ephemeral=True)
        await self.start_complaints_paginator(interaction, "/player_creation_complaints", "creation", page)

    # ===== MODERATOR MANAGEMENT =====
    @app_commands.command(name="mod_list", description="List all moderators")
    @app_commands.describe(page="Page (default: 1)", per_page="Per page (default: 10)")
    @has_moderator_role()
    async def mod_list(self, interaction: discord.Interaction, page: int = 1, per_page: int = 10):
        debug(f"mod_list called by {interaction.user}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        data, error = await self.api_request("GET", "/moderators", user_id, params={"page": page, "per_page": per_page})
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return
        
        embed = discord.Embed(title=f"Moderators (Page {page})", color=discord.Color.blue())
        
        if isinstance(data, dict) and "Page" in data:
            moderators = data.get("Page", [])
            total = data.get("Total", len(moderators))
            embed.set_footer(text=f"Total: {total}")
        elif isinstance(data, list):
            moderators = data
            embed.set_footer(text=f"Total: {len(moderators)}")
        else:
            moderators = []
        
        if moderators:
            for mod in moderators:
                mid = mod.get("ID", "?")
                username = mod.get("Username", "Unknown")
                embed.add_field(name=f"ID: {mid}", value=f"**{username}**", inline=False)
        else:
            embed.description = "No moderators found"
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mod_get", description="Get specific moderator details")
    @app_commands.describe(username="Moderator username")
    @has_moderator_role()
    async def mod_get(self, interaction: discord.Interaction, username: str):
        debug(f"mod_get called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        try:
            mod_data, error = await self.find_moderator_by_username(user_id, username)
            if error:
                await self.send_error(interaction, error, ephemeral=True)
                return
            
            if not mod_data:
                embed = discord.Embed(
                    title="Not Found",
                    description=f"Moderator **{username}** not found",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
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

    @app_commands.command(name="mod_set_permissions", description="Update moderator permissions")
    @app_commands.describe(
        username="Moderator username",
        ban_users="Can ban players",
        change_creation_status="Can change creation status",
        change_user_settings="Can change user settings",
        view_grief_reports="Can view grief reports",
        view_player_complaints="Can view player complaints",
        view_player_creation_complaints="Can view creation complaints",
        manage_moderators="Can manage moderators",
        manage_announcements="Can manage announcements",
        manage_hotlap="Can manage hotlap",
        manage_system_events="Can manage system events",
        change_user_quota="Can change user quota"
    )
    @has_moderator_role()
    async def mod_set_permissions(
        self,
        interaction: discord.Interaction,
        username: str,
        ban_users: Optional[bool] = None,
        change_creation_status: Optional[bool] = None,
        change_user_settings: Optional[bool] = None,
        view_grief_reports: Optional[bool] = None,
        view_player_complaints: Optional[bool] = None,
        view_player_creation_complaints: Optional[bool] = None,
        manage_moderators: Optional[bool] = None,
        manage_announcements: Optional[bool] = None,
        manage_hotlap: Optional[bool] = None,
        manage_system_events: Optional[bool] = None,
        change_user_quota: Optional[bool] = None
    ):
        debug(f"mod_set_permissions called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        mod_data, error = await self.find_moderator_by_username(user_id, username)
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        if mod_data is None:
            await self.send_error(interaction, f"Moderator **{username}** not found", ephemeral=True)
            return

        requested_updates = {
            "ban_users": ban_users,
            "change_creation_status": change_creation_status,
            "change_user_settings": change_user_settings,
            "view_grief_reports": view_grief_reports,
            "view_player_complaints": view_player_complaints,
            "view_player_creation_complaints": view_player_creation_complaints,
            "manage_moderators": manage_moderators,
            "manage_announcements": manage_announcements,
            "manage_hotlap": manage_hotlap,
            "manage_system_events": manage_system_events,
            "change_user_quota": change_user_quota,
        }

        if all(value is None for value in requested_updates.values()):
            embed = discord.Embed(
                title="No Changes",
                description="Specify at least one permission to update.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        mod_id = mod_data.get("ID")

        permissions_params = {}
        for api_field, argument_name in PERMISSION_ARGUMENT_MAP.items():
            requested_value = requested_updates[argument_name]
            effective_value = mod_data.get(api_field, False) if requested_value is None else requested_value
            permissions_params[api_field] = str(bool(effective_value)).lower()

        data, error = await self.api_request(
            "POST",
            f"/{mod_id}/set_permissions", user_id,
            params=permissions_params
        )

        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Permissions updated for moderator **{username}**", ephemeral=True)

    @app_commands.command(name="mod_delete", description="Delete a moderator")
    @app_commands.describe(username="Moderator username")
    @has_moderator_role()
    async def mod_delete(self, interaction: discord.Interaction, username: str):
        debug(f"mod_delete called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        mod_data, error = await self.find_moderator_by_username(user_id, username)
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        if mod_data is None:
            await self.send_error(interaction, f"Moderator **{username}** not found", ephemeral=True)
            return

        mod_id = mod_data.get("ID")
        
        data, error = await self.api_request("DELETE", f"/moderators/{mod_id}", user_id)
        
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Moderator **{username}** deleted", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))