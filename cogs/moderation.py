import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from typing import Optional
import json
import os
from datetime import datetime
from config import EMBED_COLOR, URL, DEBUG_MODE, MODERATOR_ROLE_ID, MAX_QUOTA
from utils import debug, PlayerDataFetcher


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
        self.session = aiohttp.ClientSession()
        self.api_base = URL
        self.user_tokens: dict[int, str] = {}
        self.player_fetcher = PlayerDataFetcher(self.session, URL)
        
        self.logs_dir = "api_logs"
        if not os.path.exists(self.logs_dir):
            os.makedirs(self.logs_dir)

    async def cog_unload(self):
        await self.session.close()

    # TODO: Move this to utils and use in all cogs that make API calls 
    def save_api_response(self, endpoint: str, method: str, response_data, status_code: int, error: Optional[str] = None):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{self.logs_dir}/api_{timestamp}_{method}_{endpoint.replace('/', '_')}.json"
            
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "response": response_data if not error else None,
                "error": error if error else None,
                "url": f"{self.api_base}api/moderation{endpoint}"
            }
            
            if isinstance(response_data, str) and not error:
                try:
                    log_data["response_parsed"] = json.loads(response_data)
                except:
                    log_data["response_raw"] = response_data
            elif isinstance(response_data, (dict, list)):
                log_data["response"] = response_data
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            
            debug(f"API response saved to: {filename}")
        except Exception as e:
            debug(f"Failed to save API response log: {str(e)}")

    async def get_auth_headers(self, user_id: int) -> dict:
        token = self.user_tokens.get(user_id)
        if not token:
            debug(f"No moderator token available for user {user_id}")
            return {}
        debug(f"Auth headers prepared for user {user_id} with token: {token[:10]}...")
        return {"Authorization": f"Bearer {token}"}

    async def api_request(self, method: str, endpoint: str, user_id: int, **kwargs):
        url = f"{self.api_base}api/moderation{endpoint}"
        headers = await self.get_auth_headers(user_id)
        
        debug(f"API Request: {method} {url} by user {user_id}")
        
        try:
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                debug(f"API Response Status: {resp.status}")
                debug(f"Response Content-Type: {resp.content_type}")
                
                if resp.status == 401:
                    debug("Unauthorized (401)")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, "Unauthorized. Please log in first.")
                    return None, "Unauthorized. Please log in first."
                if resp.status == 403:
                    debug("Permission denied (403)")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, "Permission denied. You do not have access to this action.")
                    return None, "Permission denied. You do not have access to this action."
                if resp.status == 404:
                    debug("Resource not found (404)")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, "Resource not found.")
                    return None, "Resource not found."
                if resp.status >= 400:
                    debug(f"Error response: {resp.status}")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, f"Error {resp.status}")
                    return None, f"Error {resp.status}"
                
                text = await resp.text()
                debug(f"Raw response text: {text[:200]}")
                
                try:
                    data = json.loads(text)
                    debug(f"Successfully parsed JSON response: {type(data)}")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, data, resp.status)
                    return data, None
                except json.JSONDecodeError:
                    debug(f"JSON parsing failed, returning as text")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, text, resp.status)
                    return text, None
        except Exception as e:
            debug(f"API Request exception: {str(e)}")
            if DEBUG_MODE:
                self.save_api_response(endpoint, method, None, 0, f"Connection error: {str(e)}")
            return None, f"Connection error: {str(e)}"

    # ===== MODERATOR SELF MANAGEMENT =====
    @app_commands.command(name="mod_login", description="Connect as API moderator")
    @app_commands.describe(username="Moderator username", password="Moderator password")
    @has_moderator_role()
    async def mod_login(self, interaction: discord.Interaction, username: str, password: str):
        debug(f"mod_login called by {interaction.user} with username: {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        try:
            url = f"{self.api_base}api/moderation/login"
            debug(f"Login attempt to: {url}")
            async with self.session.post(url, params={"login": username, "password": password}) as resp:
                debug(f"Login response status: {resp.status}")
                text = await resp.text()
                debug(f"Login response data: {text}")
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"{self.logs_dir}/api_login_{timestamp}.json"
                login_data = {
                    "timestamp": datetime.now().isoformat(),
                    "endpoint": "/login",
                    "method": "POST",
                    "status_code": resp.status,
                    "response": text,
                    "username": username,
                    "user_id": user_id
                }
                if DEBUG_MODE:
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(login_data, f, indent=2, ensure_ascii=False)
                    debug(f"Login response saved to: {filename}")
                
                if resp.status == 200 and text == "ok":
                    cookies = resp.cookies
                    if 'Token' in cookies:
                        token = cookies['Token'].value
                        self.user_tokens[user_id] = token
                        debug(f"Token received for user {user_id}: {token[:10]}...")
                        
                        embed = discord.Embed(title="Login Success", description=f"Connected as **{username}**", color=discord.Color.green())
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        debug("No token in response cookies")
                        embed = discord.Embed(title="Login Failed", description="Server did not provide token", color=discord.Color.red())
                        await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    debug(f"Login failed with status {resp.status}: {text}")
                    embed = discord.Embed(title="Login Failed", description="Invalid username or password", color=discord.Color.red())
                    await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            debug(f"Login exception: {str(e)}")
            embed = discord.Embed(title="Error", description=f"```{str(e)}```", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            
    @app_commands.command(name="mod_create", description="Create a new moderator")
    @app_commands.describe(username="New moderator username", password="New moderator password")
    @has_moderator_role()
    async def mod_create(self, interaction: discord.Interaction, username: str, password: str):
        debug(f"mod_create called by {interaction.user} for username: {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        
        try:    
            permissions = {
                "BanUsers": False,
                "ChangeCreationStatus": False,
                "ChangeUserSettings": False,
                "ViewGriefReports": False,
                "ViewPlayerComplaints": False,
                "ViewPlayerCreationComplaints": False,
                "ManageModerators": False,
                "ManageAnnouncements": False,
                "ManageHotlap": False,
                "ManageSystemEvents": False,
                "ChangeUserQuota": False
            }
            
            data, error = await self.api_request("POST", "/moderators", user_id,
                                                params={"username": username, "password": password},
                                                json=permissions)
            
            if error:
                embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Moderator Created",
                description=f"Moderator **{username}** created successfully",
                color=discord.Color.green()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            debug(f"Moderator {username} created by {interaction.user.name}")
            
        except Exception as e:
            debug(f"Error creating moderator: {str(e)}")
            embed = discord.Embed(title="Error", description=f"```{str(e)}```", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mod_perms", description="View your moderation permissions")
    @has_moderator_role()
    async def mod_perms(self, interaction: discord.Interaction):
        debug(f"mod_perms called by {interaction.user}")
        await interaction.response.defer()
        
        user_id = interaction.user.id
        data, error = await self.api_request("GET", "/permissions", user_id)
        debug(f"Permissions data: {data}, error: {error}")
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed)
            return
        
        embed = discord.Embed(title="Your Permissions", color=EMBED_COLOR)
        
        if isinstance(data, dict):
            perms = {
                "ManageModerators": "Manage Moderators",
                "BanUsers": "Ban Users",
                "ChangeUserSettings": "Change Settings",
                "ChangeCreationStatus": "Change Creation Status",
                "ManageAnnouncements": "Manage Announcements",
                "ManageHotlap": "Manage Hotlap",
                "ManageSystemEvents": "Manage System Events",
                "ViewGriefReports": "View Grief Reports",
                "ViewPlayerComplaints": "View Player Complaints",
                "ViewPlayerCreationComplaints": "View Creation Complaints",
                "ChangeUserQuota": "Change User Quota"
            }
            
            for key, label in perms.items():
                has_perm = data.get(key, False)
                status = "✅ Yes" if has_perm else "❌ No"
                debug(f"Permission {key}: {has_perm}")
                embed.add_field(name=label, value=status, inline=True)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="mod_set_username", description="Change your moderator username")
    @app_commands.describe(username="New username")
    @has_moderator_role()
    async def mod_set_username(self, interaction: discord.Interaction, username: str):
        debug(f"mod_set_username called by {interaction.user} with username: {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        data, error = await self.api_request("POST", "/set_username", user_id, params={"username": username})
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(title="Success", description=f"Username changed to **{username}**", color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mod_set_password", description="Change your moderator password")
    @app_commands.describe(password="New password")
    @has_moderator_role()
    async def mod_set_password(self, interaction: discord.Interaction, password: str):
        debug(f"mod_set_password called by {interaction.user}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        data, error = await self.api_request("POST", "/set_password", user_id, params={"password": password})
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(title="Success", description="Password changed successfully", color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ===== USER MANAGEMENT =====
    @app_commands.command(name="ban_user", description="Ban or unban user")
    @app_commands.describe(username="Player username", ban="True to ban, False to unban")
    @has_moderator_role()
    async def ban_user(self, interaction: discord.Interaction, username: str, ban: bool):
        debug(f"ban_user called by {interaction.user} - username: {username}, ban: {ban}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        player_id = await self.player_fetcher.get_player_id(username)
        if player_id is None:
            embed = discord.Embed(title="Error", description=f"Player '{username}' not found", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        debug(f"Found player ID {player_id} for username {username}")
        
        is_banned = "true" if ban else "false"
        data, error = await self.api_request("POST", "/setBan", user_id, params={"id": player_id, "isBanned": is_banned})
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        action = "banned" if ban else "unbanned"
        embed = discord.Embed(title="Action Complete", description=f"Player **{username}** was **{action}**", 
                            color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="set_user_settings", description="Modify user settings")
    @app_commands.describe(username="Player username", show_no_previews="Show creations without previews", 
                          allow_opposite_platform="Allow opposite platform")
    @has_moderator_role()
    async def set_user_settings(self, interaction: discord.Interaction, username: str, 
                               show_no_previews: bool = False, allow_opposite_platform: bool = False):
        debug(f"set_user_settings called by {interaction.user} for {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        player_id = await self.player_fetcher.get_player_id(username)
        if player_id is None:
            embed = discord.Embed(title="Error", description=f"Player '{username}' not found", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        data, error = await self.api_request("POST", "/setUserSettings", user_id,
                                            params={
                                                "id": player_id,
                                                "ShowCreationsWithoutPreviews": str(show_no_previews).lower(),
                                                "AllowOppositePlatform": str(allow_opposite_platform).lower()
                                            })
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(title="Success", description=f"Settings updated for **{username}**", 
                            color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    @app_commands.command(name="set_user_quota", description="Change a player's creation quota")
    @app_commands.describe(username="Player username", quota="New quota (integer between 0 and 2147483647)")
    @has_moderator_role()
    async def set_user_quota(self, interaction: discord.Interaction, username: str, quota: int):
        debug(f"set_user_quota called by {interaction.user} for {username} -> quota={quota}")
        await interaction.response.defer(ephemeral=True)

        if quota < 0 or quota > MAX_QUOTA:
            embed = discord.Embed(
                title="Error",
                description=f"Quota must be an integer between 0 and {MAX_QUOTA}.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        user_id = interaction.user.id

        player_id = await self.player_fetcher.get_player_id(username)
        if player_id is None:
            embed = discord.Embed(
                title="Error",
                description=f"Player '{username}' was not found.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        data, error = await self.api_request(
            "POST",
            "/setUserQuota",
            user_id,
            params={"id": player_id, "quota": quota}
        )

        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="Success",
            description=f"Quota for **{username}** (ID `{player_id}`) changed to **{quota}**.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        
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
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        debug(f"Creation {creation_id} status changed to {status}")
        embed = discord.Embed(title="Status Updated", description=f"Creation ID `{creation_id}` → **{status}**", color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)

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
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
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
            all_mods, error = await self.api_request("GET", "/moderators", user_id, params={"page": 1, "per_page": 1000})
            
            if error:
                embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            moderators = all_mods if isinstance(all_mods, list) else all_mods.get("Page", [])
            
            mod_data = None
            for mod in moderators:
                if mod.get("Username", "").lower() == username.lower():
                    mod_data = mod
                    break
            
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
            permissions = {
                "BanUsers": "Ban Users",
                "ChangeCreationStatus": "Change Creation Status",
                "ChangeUserSettings": "Change Settings",
                "ViewGriefReports": "View Grief Reports",
                "ViewPlayerComplaints": "View Player Complaints",
                "ViewPlayerCreationComplaints": "View Creation Complaints",
                "ManageModerators": "Manage Moderators",
                "ManageAnnouncements": "Manage Announcements",
                "ManageHotlap": "Manage Hotlap",
                "ManageSystemEvents": "Manage System Events",
                "ChangeUserQuota": "Change User Quota"
            }
            
            for key, label in permissions.items():
                if mod_data.get(key, False):
                    perms_list.append(label)
            
            if perms_list:
                embed.add_field(name="Permissions", value="\n".join(f"✅ {p}" for p in perms_list), inline=False)
            else:
                embed.add_field(name="Permissions", value="No permissions granted", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            debug(f"Error in mod_get: {str(e)}")
            embed = discord.Embed(title="Error", description=f"```{str(e)}```", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mod_set_permissions", description="Update moderator permissions")
    @app_commands.describe(
        username="Moderator username",
        ban_users="Can ban users",
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
        ban_users: bool = False,
        change_creation_status: bool = False,
        change_user_settings: bool = False,
        view_grief_reports: bool = False,
        view_player_complaints: bool = False,
        view_player_creation_complaints: bool = False,
        manage_moderators: bool = False,
        manage_announcements: bool = False,
        manage_hotlap: bool = False,
        manage_system_events: bool = False,
        change_user_quota: bool = False
    ):
        debug(f"mod_set_permissions called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        all_mods, error = await self.api_request("GET", "/moderators", user_id, params={"page": 1, "per_page": 1000})
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        moderators = all_mods if isinstance(all_mods, list) else all_mods.get("Page", [])
        
        mod_id = None
        for mod in moderators:
            if mod.get("Username", "").lower() == username.lower():
                mod_id = mod.get("ID")
                break
        
        if mod_id is None:
            embed = discord.Embed(title="Error", description=f"Moderator **{username}** not found", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        permissions_params = {
            "BanUsers": str(ban_users).lower(),
            "ChangeCreationStatus": str(change_creation_status).lower(),
            "ChangeUserSettings": str(change_user_settings).lower(),
            "ViewGriefReports": str(view_grief_reports).lower(),
            "ViewPlayerComplaints": str(view_player_complaints).lower(),
            "ViewPlayerCreationComplaints": str(view_player_creation_complaints).lower(),
            "ManageModerators": str(manage_moderators).lower(),
            "ManageAnnouncements": str(manage_announcements).lower(),
            "ManageHotlap": str(manage_hotlap).lower(),
            "ManageSystemEvents": str(manage_system_events).lower(),
            "ChangeUserQuota": str(change_user_quota).lower()
        }

        data, error = await self.api_request(
            "POST",
            f"/{mod_id}/set_permissions", user_id,
            params=permissions_params
        )

        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="Success",
            description=f"Permissions updated for moderator **{username}**",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="mod_delete", description="Delete a moderator")
    @app_commands.describe(username="Moderator username")
    @has_moderator_role()
    async def mod_delete(self, interaction: discord.Interaction, username: str):
        debug(f"mod_delete called by {interaction.user} for moderator {username}")
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        all_mods, error = await self.api_request("GET", "/moderators", user_id, params={"page": 1, "per_page": 1000})
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        moderators = all_mods if isinstance(all_mods, list) else all_mods.get("Page", [])

        mod_id = None
        for mod in moderators:
            if mod.get("Username", "").lower() == username.lower():
                mod_id = mod.get("ID")
                break
        
        if mod_id is None:
            embed = discord.Embed(title="Error", description=f"Moderator **{username}** not found", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        data, error = await self.api_request("DELETE", f"/moderators/{mod_id}", user_id)
        
        if error:
            embed = discord.Embed(title="Error", description=error, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(title="Success", description=f"Moderator **{username}** deleted", 
                            color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))