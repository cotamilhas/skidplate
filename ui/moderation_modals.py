from __future__ import annotations
from typing import Any, Optional, TYPE_CHECKING
import discord
from utils import debug, DEFAULT_MODERATOR_PERMISSIONS, PLATFORM_LABELS
if TYPE_CHECKING:
    from cogs.moderation import Moderation


def _build_platform_options(selected_platform: Optional[int] = None) -> list[discord.SelectOption]:
    options: list[discord.SelectOption] = []
    for value, label in PLATFORM_LABELS.items():
        options.append(
            discord.SelectOption(
                label=f"{label} ({value})",
                value=str(value),
                default=(selected_platform == value)
            )
        )
    return options


async def handle_mod_login_submission(
    moderation_cog: Moderation,
    interaction: discord.Interaction,
    username: str,
    password: str
):
    debug(f"mod_login modal submitted by {interaction.user}")
    await interaction.response.defer(ephemeral=True)

    user_id = interaction.user.id

    try:
        url = f"{moderation_cog.api_base}api/moderation/login"
        debug(f"Login attempt to: {url}")
        async with moderation_cog.moderation_session.post(url, data={"login": username, "password": password}) as resp:
            debug(f"Login response status: {resp.status}")
            text = await resp.text()

            if resp.status == 200 and text == "ok":
                cookies = resp.cookies
                if "Token" in cookies:
                    token = cookies["Token"].value
                    moderation_cog.user_tokens[user_id] = token
                    debug(f"Token received for user {user_id}: {token[:10]}...")
                    await moderation_cog.send_success(interaction, f"Connected as **{username}**", ephemeral=True)
                else:
                    debug("No token in response cookies")
                    await moderation_cog.send_embed(
                        interaction,
                        title="Login Failed",
                        description="Server did not provide token",
                        color=discord.Color.red(),
                        ephemeral=True
                    )
            else:
                debug(f"Login failed with status {resp.status}")
                await moderation_cog.send_embed(
                    interaction,
                    title="Login Failed",
                    description="Invalid username or password",
                    color=discord.Color.red(),
                    ephemeral=True
                )
    except Exception as e:
        debug(f"Login exception: {str(e)}")
        await moderation_cog.send_error(interaction, f"```{str(e)}```", ephemeral=True)


async def handle_mod_create_submission(
    moderation_cog: Moderation,
    interaction: discord.Interaction,
    username: str,
    password: str
):
    debug(f"mod_create modal submitted by {interaction.user} for username: {username}")
    await interaction.response.defer(ephemeral=True)

    user_id = interaction.user.id

    try:

        permissions = DEFAULT_MODERATOR_PERMISSIONS.copy()

        data, error = await moderation_cog.api_request(
            "POST",
            "/moderators",
            user_id,
            params={"username": username, "password": password},
            json=permissions
        )

        if error:
            await moderation_cog.send_error(interaction, error, ephemeral=True)
            return

        await moderation_cog.send_success(interaction, f"Moderator **{username}** created successfully", ephemeral=True)
        debug(f"Moderator {username} created by {interaction.user.name}")

    except Exception as e:
        debug(f"Error creating moderator: {str(e)}")
        await moderation_cog.send_error(interaction, f"```{str(e)}```", ephemeral=True)


async def handle_announce_create_submission(
    moderation_cog: Moderation,
    interaction: discord.Interaction,
    platform: int,
    subject: str,
    text: str
):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    params = {
        "languageCode": "en-US",
        "subject": subject,
        "text": text,
        "platform": platform,
    }

    data, error = await moderation_cog.api_request("POST", "/announcements", user_id, params=params)
    if error:
        await moderation_cog.send_error(interaction, error, ephemeral=True)
        return

    await moderation_cog.send_success(interaction, "Announcement created.", ephemeral=True)


async def get_announcement_for_edit(
    moderation_cog: Moderation,
    user_id: int,
    announcement_id: int,
    platform: Optional[int]
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    data, error = await moderation_cog.api_request("GET", f"/announcements/{announcement_id}", user_id)
    if not error and isinstance(data, dict):
        return data, None

    params: dict[str, Any] = {"page": 1, "per_page": 1000}
    if platform is not None:
        params["platform"] = platform

    list_data, list_error = await moderation_cog.api_request("GET", "/announcements", user_id, params=params)
    if list_error:
        return None, list_error

    items: list[dict[str, Any]] = []
    if isinstance(list_data, dict) and "Page" in list_data:
        page_items = list_data.get("Page") or []
        if isinstance(page_items, list):
            items = [item for item in page_items if isinstance(item, dict)]
    elif isinstance(list_data, list):
        items = [item for item in list_data if isinstance(item, dict)]

    for item in items:
        item_id = item.get("Id", item.get("ID"))
        if item_id == announcement_id:
            return item, None

    return None, "Announcement not found."


async def get_system_event_for_edit(
    moderation_cog: Moderation,
    user_id: int,
    event_id: int
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    data, error = await moderation_cog.api_request("GET", f"/system_events/{event_id}", user_id)
    if not error and isinstance(data, dict):
        return data, None

    params: dict[str, Any] = {"page": 1, "per_page": 1000}
    list_data, list_error = await moderation_cog.api_request("GET", "/system_events", user_id, params=params)
    if list_error:
        return None, list_error

    items: list[dict[str, Any]] = []
    if isinstance(list_data, dict) and "Page" in list_data:
        page_items = list_data.get("Page") or []
        if isinstance(page_items, list):
            items = [item for item in page_items if isinstance(item, dict)]
    elif isinstance(list_data, list):
        items = [item for item in list_data if isinstance(item, dict)]

    for item in items:
        item_id = item.get("Id", item.get("ID"))
        if item_id == event_id:
            return item, None

    return None, "System event not found."


async def handle_announce_edit_submission(
    moderation_cog: Moderation,
    interaction: discord.Interaction,
    announcement_id: int,
    platform: int,
    subject: str,
    text: str
):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    params = {
        "languageCode": "en-US",
        "subject": subject,
        "text": text,
        "platform": platform,
    }

    data, error = await moderation_cog.api_request("POST", f"/announcements/{announcement_id}", user_id, params=params)
    if error:
        await moderation_cog.send_error(interaction, error, ephemeral=True)
        return

    await moderation_cog.send_success(interaction, f"Announcement `{announcement_id}` updated.", ephemeral=True)


async def handle_sysmsg_create_submission(
    moderation_cog: Moderation,
    interaction: discord.Interaction,
    topic: str,
    description: str,
    image_url: Optional[str]
):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    params = {"topic": topic, "description": description}
    if image_url:
        params["imageURL"] = image_url

    data, error = await moderation_cog.api_request("POST", "/system_events", user_id, params=params)
    if error:
        await moderation_cog.send_error(interaction, error, ephemeral=True)
        return

    await moderation_cog.send_success(interaction, "System event created.", ephemeral=True)


async def handle_sysmsg_edit_submission(
    moderation_cog: Moderation,
    interaction: discord.Interaction,
    event_id: int,
    topic: str,
    description: str,
    image_url: Optional[str]
):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    params = {"topic": topic, "description": description}
    if image_url:
        params["imageURL"] = image_url

    data, error = await moderation_cog.api_request("POST", f"/system_events/{event_id}", user_id, params=params)
    if error:
        await moderation_cog.send_error(interaction, error, ephemeral=True)
        return

    await moderation_cog.send_success(interaction, f"System event `{event_id}` updated.", ephemeral=True)


class ModeratorLoginModal(discord.ui.Modal, title="Moderator Login"):
    username = discord.ui.TextInput(label="Username", required=True, max_length=64)
    password = discord.ui.TextInput(label="Password", required=True, max_length=128)

    def __init__(self, moderation_cog: Moderation):
        super().__init__()
        self.moderation_cog = moderation_cog

    async def on_submit(self, interaction: discord.Interaction):
        await handle_mod_login_submission(
            self.moderation_cog,
            interaction,
            str(self.username),
            str(self.password)
        )


class ModeratorCreateModal(discord.ui.Modal, title="Create Moderator"):
    username = discord.ui.TextInput(label="Username", required=True, max_length=64)
    password = discord.ui.TextInput(label="Password", required=True, max_length=128)

    def __init__(self, moderation_cog: Moderation):
        super().__init__()
        self.moderation_cog = moderation_cog

    async def on_submit(self, interaction: discord.Interaction):
        await handle_mod_create_submission(
            self.moderation_cog,
            interaction,
            str(self.username),
            str(self.password)
        )


class AnnouncementCreateModal(discord.ui.Modal, title="Create Announcement"):
    platform = discord.ui.Label(
        text="Platform",
        description="Choose where this announcement should appear.",
        component=discord.ui.Select(
            options=_build_platform_options(),
            min_values=1,
            max_values=1,
        )
    )
    subject = discord.ui.TextInput(label="Subject", required=True, max_length=120)
    text = discord.ui.TextInput(label="Body Text", required=True, style=discord.TextStyle.paragraph, max_length=1900)

    def __init__(self, moderation_cog: Moderation):
        super().__init__()
        self.moderation_cog = moderation_cog

    async def on_submit(self, interaction: discord.Interaction):
        selected_values = self.platform.component.values
        if not selected_values:
            await interaction.response.send_message(
                "Please choose a platform.",
                ephemeral=True
            )
            return

        selected_platform = int(selected_values[0])

        await handle_announce_create_submission(
            self.moderation_cog,
            interaction,
            selected_platform,
            str(self.subject),
            str(self.text)
        )


class AnnouncementEditModal(discord.ui.Modal, title="Edit Announcement"):
    platform = discord.ui.Label(
        text="Platform",
        description="Choose where this announcement should appear.",
        component=discord.ui.Select(
            options=_build_platform_options(),
            min_values=1,
            max_values=1,
        )
    )
    subject = discord.ui.TextInput(label="Subject", required=True, max_length=120)
    text = discord.ui.TextInput(label="Body Text", required=True, style=discord.TextStyle.paragraph, max_length=1900)

    def __init__(
        self,
        moderation_cog: Moderation,
        announcement_id: int,
        initial_platform: Optional[str] = None,
        initial_subject: Optional[str] = None,
        initial_text: Optional[str] = None
    ):
        super().__init__()
        self.moderation_cog = moderation_cog
        self.announcement_id = announcement_id
        selected_platform: Optional[int] = None
        if initial_platform is not None:
            normalized = initial_platform.strip()
            if normalized.isdigit():
                parsed = int(normalized)
                if parsed in PLATFORM_LABELS:
                    selected_platform = parsed

        self.platform.component.options = _build_platform_options(selected_platform)
        if initial_subject is not None:
            self.subject.default = initial_subject
        if initial_text is not None:
            self.text.default = initial_text

    async def on_submit(self, interaction: discord.Interaction):
        selected_values = self.platform.component.values
        if not selected_values:
            await interaction.response.send_message(
                "Please choose a platform.",
                ephemeral=True
            )
            return

        selected_platform = int(selected_values[0])

        await handle_announce_edit_submission(
            self.moderation_cog,
            interaction,
            self.announcement_id,
            selected_platform,
            str(self.subject),
            str(self.text)
        )


class SystemEventCreateModal(discord.ui.Modal, title="Create System Event"):
    topic = discord.ui.TextInput(label="Topic", required=True, max_length=120)
    description = discord.ui.TextInput(label="Description", required=True, style=discord.TextStyle.paragraph, max_length=1900)
    image_url = discord.ui.TextInput(label="Image URL (optional)", required=False, max_length=500)

    def __init__(self, moderation_cog: Moderation):
        super().__init__()
        self.moderation_cog = moderation_cog

    async def on_submit(self, interaction: discord.Interaction):
        await handle_sysmsg_create_submission(
            self.moderation_cog,
            interaction,
            str(self.topic),
            str(self.description),
            str(self.image_url).strip() or None
        )


class SystemEventEditModal(discord.ui.Modal, title="Edit System Event"):
    topic = discord.ui.TextInput(label="Topic", required=True, max_length=120)
    description = discord.ui.TextInput(label="Description", required=True, style=discord.TextStyle.paragraph, max_length=1900)
    image_url = discord.ui.TextInput(label="Image URL (optional)", required=False, max_length=500)

    def __init__(
        self,
        moderation_cog: Moderation,
        event_id: int,
        initial_topic: Optional[str] = None,
        initial_description: Optional[str] = None,
        initial_image_url: Optional[str] = None
    ):
        super().__init__()
        self.moderation_cog = moderation_cog
        self.event_id = event_id
        if initial_topic is not None:
            self.topic.default = initial_topic
        if initial_description is not None:
            self.description.default = initial_description
        if initial_image_url is not None:
            self.image_url.default = initial_image_url

    async def on_submit(self, interaction: discord.Interaction):
        await handle_sysmsg_edit_submission(
            self.moderation_cog,
            interaction,
            self.event_id,
            str(self.topic),
            str(self.description),
            str(self.image_url).strip() or None
        )


__all__ = [
    "ModeratorLoginModal",
    "ModeratorCreateModal",
    "AnnouncementCreateModal",
    "AnnouncementEditModal",
    "SystemEventCreateModal",
    "SystemEventEditModal",
    "get_announcement_for_edit",
    "get_system_event_for_edit",
]
