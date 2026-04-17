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
    AnnouncementsPaginator,
    SystemEventsPaginator,
    HotlapQueuePaginator
)
from utils import (
    debug,
    PlayerDataFetcher,
    CreationDataFetcher,
    prepare_player_avatar_attachment,
    cleanup_temp_file,
    extract_creation_id,
    extract_creation_type,
    is_not_a_track_response,
    parse_hotlap_queue_payload
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
    "ChangeUserQuota": "Change Player Quota",
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

PLATFORM_LABELS = {
    0: "PS2",
    1: "PSP",
    2: "PS3",
    3: "WEB",
    4: "PSV"
}

PLATFORM_CHOICES = [
    app_commands.Choice(name=label, value=value)
    for value, label in PLATFORM_LABELS.items()
]


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

    @staticmethod
    def _truncate_text(value: Any, max_len: int, fallback: str = "") -> str:
        if not isinstance(value, str):
            return fallback
        text = value.strip()
        if not text:
            return fallback
        if len(text) <= max_len:
            return text
        return text[:max_len].rstrip() + "..."

    @staticmethod
    def _parse_paged_payload(data: Any, page_key: str = "Page") -> tuple[list[dict[str, Any]], Optional[int], bool]:
        if isinstance(data, dict):
            items = data.get(page_key, [])
            if isinstance(items, list):
                normalized_items = [item for item in items if isinstance(item, dict)]
                total = data.get("Total")
                if isinstance(total, int):
                    return normalized_items, total, True
                return normalized_items, len(normalized_items), True
            return [], None, False

        if isinstance(data, list):
            normalized_items = [item for item in data if isinstance(item, dict)]
            return normalized_items, len(normalized_items), True

        return [], None, False

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
        data, error = await self.api_request("GET", "/moderators", user_id, params={"page": 1, "per_page": 1000})
        if error:
            return [], error

        moderators, _, is_valid = self._parse_paged_payload(data)
        if is_valid:
            return moderators, None
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

    async def ensure_track_creation(self, interaction: discord.Interaction, creation_id: int) -> bool:
        if await self.is_track_creation(creation_id):
            return True

        await self.send_error(interaction, f"Creation `{creation_id}` is not a track.")
        return False

    async def is_track_creation(self, creation_id: int) -> bool:
        creation_info = await self.creation_fetcher.get_creation_info(creation_id)
        if not creation_info:
            return False
        creation_type = extract_creation_type(creation_info)
        return creation_type == "TRACK"

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
                            ephemeral=True
                        )
                else:
                    debug(f"Login failed with status {resp.status}")
                    await self.send_embed(
                        interaction,
                        title="Login Failed",
                        description="Invalid username or password",
                        color=discord.Color.red(),
                        ephemeral=True
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
            player_id
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
            f"Quota for **{username}** (ID `{player_id}`) changed to **{quota}**.",
            ephemeral=True
        )
        
    @app_commands.command(name="banned_players", description="List banned players")
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
        
    @app_commands.command(
        name="reset_player",
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
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        player_id = await self._resolve_player_id_or_error(interaction, username)
        if player_id is None:
            return

        params = {
            "removeCreations": str(remove_creations).lower(),
        }

        data, error = await self.api_request(
            "POST",
            f"/users/{player_id}/reset_profile",
            user_id,
            params=params,
        )
        debug(f"Reset player profile result: {data}, error: {error}")

        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(
            interaction,
            f"Profile reset for **{username}** (ID `{player_id}`).\n"
            f"Remove Creations: **{remove_creations}**",
            ephemeral=True
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

        debug(f"Creation {creation_id} status changed to {status}")
        await self._send_creation_status_embed(
            interaction,
            title="Creation Banned" if banned else "Creation Approved",
            color=discord.Color.red() if banned else discord.Color.green(),
            creation_id=creation_id
        )
        
    @app_commands.command(name="reset_creation", description="Reset a creation's stats (views, downloads, points, comments, ratings, reviews)")
    @app_commands.describe(creation_id="Creation ID to reset stats for")
    @has_moderator_role()
    async def reset_creation(self, interaction: discord.Interaction, creation_id: int):
        debug(f"reset_creation called by {interaction.user} - creation_id: {creation_id}")
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        data, error = await self.api_request(
            "POST",
            f"/player_creations/{creation_id}/reset_stats",
            user_id,
        )
        debug(f"Reset creation stats result: {data}, error: {error}")

        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self._send_creation_status_embed(
            interaction,
            title="Creation Stats Reset",
            color=discord.Color.green(),
            creation_id=creation_id
        )
        
    @app_commands.command(name="banned_creations", description="List banned creations")
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
        
    # ===== HOTLAP MANAGEMENT =====
    @app_commands.command(name="get_hotlap", description="Show current hotlap track")
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

    @app_commands.command(name="set_hotlap", description="Set hotlap by creation ID")
    @app_commands.describe(creation_id="Creation ID to set as hotlap")
    @has_moderator_role()
    async def set_hotlap(self, interaction: discord.Interaction, creation_id: int):
        await interaction.response.defer(ephemeral=True)

        if not await self.ensure_track_creation(interaction, creation_id):
            return

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

    @app_commands.command(name="reset_hotlap", description="Reset the current hotlap")
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

    @app_commands.command(name="hotlap_until_next", description="Get time until next hotlap")
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

    @app_commands.command(name="hotlap_queue", description="List the hotlap queue")
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

    @app_commands.command(name="hotlap_queue_add", description="Add a creation to the hotlap queue")
    @app_commands.describe(creation_id="Creation ID to add to queue")
    @has_moderator_role()
    async def hotlap_queue_add(self, interaction: discord.Interaction, creation_id: int):
        await interaction.response.defer(ephemeral=True)

        if not await self.ensure_track_creation(interaction, creation_id):
            return

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

    @app_commands.command(name="hotlap_queue_remove", description="Remove a creation from the hotlap queue by index or creation ID")
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
    @app_commands.command(name="announce_list", description="List announcements")
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

    @app_commands.command(name="announce_create", description="Create an announcement")
    @app_commands.describe(platform="Platform", subject="Subject", text="Body text")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    @has_moderator_role()
    async def announce_create(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[int],
        subject: str,
        text: str
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        params = {
            "languageCode": "en-US",
            "subject": subject,
            "text": text,
            "platform": platform.value
        }

        data, error = await self.api_request("POST", "/announcements", user_id, params=params)
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, "Announcement created.", ephemeral=True)

    @app_commands.command(name="announce_edit", description="Edit an announcement")
    @app_commands.describe(announcement_id="Announcement ID", platform="Platform", subject="Subject", text="Body text")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    @has_moderator_role()
    async def announce_edit(
        self,
        interaction: discord.Interaction,
        announcement_id: int,
        platform: app_commands.Choice[int],
        subject: str,
        text: str
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        params = {
            "languageCode": "en-US",
            "subject": subject,
            "text": text,
            "platform": platform.value
        }

        data, error = await self.api_request("POST", f"/announcements/{announcement_id}", user_id, params=params)
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Announcement `{announcement_id}` updated.", ephemeral=True)

    @app_commands.command(name="announce_delete", description="Delete an announcement")
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
        
    # ===== SYSTEM EVENTS =====
    @app_commands.command(name="sysmsg_list", description="List system messages (system events)")
    @app_commands.describe(page="Page (default: 1)")
    @has_moderator_role()
    async def sysmsg_list(self, interaction: discord.Interaction, page: int = 1):
        await interaction.response.defer(ephemeral=True)
        view = SystemEventsPaginator(
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

    @app_commands.command(name="sysmsg_create", description="Create a system event")
    @app_commands.describe(topic="Short title/topic", description="Message text", image_url="Optional image URL")
    @has_moderator_role()
    async def sysmsg_create(
        self,
        interaction: discord.Interaction,
        topic: str,
        description: str,
        image_url: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        params = {"topic": topic, "description": description}
        if image_url:
            params["imageURL"] = image_url

        data, error = await self.api_request("POST", "/system_events", user_id, params=params)
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, "System event created.", ephemeral=True)

    @app_commands.command(name="sysmsg_edit", description="Edit a system event")
    @app_commands.describe(event_id="System event ID", topic="Short title/topic", description="Message text", image_url="Optional image URL")
    @has_moderator_role()
    async def sysmsg_edit(
        self,
        interaction: discord.Interaction,
        event_id: int,
        topic: str,
        description: str,
        image_url: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        params = {"topic": topic, "description": description}
        if image_url:
            params["imageURL"] = image_url

        data, error = await self.api_request("POST", f"/system_events/{event_id}", user_id, params=params)
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"System event `{event_id}` updated.", ephemeral=True)

    @app_commands.command(name="sysmsg_delete", description="Delete a system event")
    @app_commands.describe(event_id="System event ID")
    @has_moderator_role()
    async def sysmsg_delete(self, interaction: discord.Interaction, event_id: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        data, error = await self.api_request("DELETE", f"/system_events/{event_id}", user_id)
        if error:
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"System event `{event_id}` deleted.", ephemeral=True)

    # ===== MODERATOR MANAGEMENT =====
    @app_commands.command(name="mod_list", description="List all moderators")
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

    @app_commands.command(name="mod_get", description="Get specific moderator details")
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

    @app_commands.command(name="mod_set_permissions", description="Update moderator permissions")
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

    @app_commands.command(name="mod_delete", description="Delete a moderator")
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
            if error == "error_cannot_remove_yourself":
                await self.send_error(
                    interaction,
                    "You cannot delete your own moderator account.",
                    ephemeral=True
                )
                return
            await self.send_error(interaction, error, ephemeral=True)
            return

        await self.send_success(interaction, f"Moderator **{username}** deleted", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))