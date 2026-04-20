import discord
from typing import Any, Dict, List
from utils import rating_to_stars, format_time


CREATION_TYPE_LABELS = {
    0: "Photo",
    1: "Planet",
    2: "Track",
    3: "Item",
    4: "Story",
    5: "Deleted",
    6: "Mod",
    7: "Kart"
}


def trim_text(value: str, max_len: int = 250, fallback: str = "No description provided.") -> str:
    if not value:
        return fallback

    value = value.strip()
    if not value:
        return fallback

    return value if len(value) <= max_len else value[:max_len].rstrip() + "..."


def add_top_creation_fields_to_embed(embed: discord.Embed, creations: List[Dict[str, Any]], full_emoji: str, half_emoji: str, empty_emoji: str, show_hearts: bool = False):
    if creations and creations[0].get("thumbnail"):
        embed.set_thumbnail(url=creations[0]["thumbnail"])

    for i, creation in enumerate(creations, start=1):
        name = creation.get("name", "Unknown")
        username = creation.get("username", "Unknown")
        creation_id = creation.get("id", "?")
        points_today = creation.get("points_today", "0")
        points = creation.get("points", "0")
        rating = creation.get("star_rating", "N/A")
        downloads = creation.get("downloads", "0")
        hearts = creation.get("hearts", "0")
        short_desc = trim_text(creation.get("description", ""))

        rating_stars = rating_to_stars(rating, full_emoji, half_emoji, empty_emoji)

        field_value = (
            f"ID: `{creation_id}` | Creator: **{username}**\n"
            f"Points Today: **{points_today}** | Total Points: **{points}**\n"
            f"Rating: **{rating_stars}** | Total Downloads: **{downloads}**"
            + (f" | Hearts: **{hearts}**" if show_hearts else "")
            + f"\n> {short_desc}"
        )

        embed.add_field(
            name=f"#{i} {name}",
            value=field_value,
            inline=False
        )


def add_creation_fields_to_embed(embed: discord.Embed, info: Dict[str, str], full_emoji: str, half_emoji: str, empty_emoji: str):
    description = info.get("description", "")
    if description:
        embed.add_field(
            name="Description",
            value=f"> {trim_text(description)}",
            inline=False
        )

    rating_stars = rating_to_stars(info.get("star_rating", "0"), full_emoji, half_emoji, empty_emoji)
    embed.add_field(name="Rating", value=f"**{rating_stars}**", inline=True)
    embed.add_field(name="Downloads", value=f"**{info.get('downloads', '0')}**", inline=True)
    embed.add_field(name="Views", value=f"**{info.get('views', '0')}**", inline=True)

    points_today = info.get("points_today", "0")
    points = info.get("points", "0")
    embed.add_field(name="Points", value=f"Today: **{points_today}** | Total: **{points}**", inline=False)

    platform = info.get("platform", "Unknown")
    embed.add_field(name="Platform", value=f"**{platform}**", inline=True)

    embed.add_field(name="Races Started", value=f"**{info.get('races_started', '0')}**", inline=True)

    creation_type = info.get("player_creation_type", "Unknown")
    if creation_type != "TRACK":
        embed.add_field(name="Races Won", value=f"**{info.get('races_won', '0')}**", inline=True)

    if creation_type == "TRACK":
        best_lap = format_time(info.get("best_lap_time", "N/A"))
        embed.add_field(name="Best Lap Time", value=f"**{best_lap}**", inline=True)

    embed.add_field(name="Longest Drift", value=f"**{info.get('longest_drift', '0')}**", inline=True)
    embed.add_field(name="Longest Air Time", value=f"**{info.get('longest_hang_time', '0')}**", inline=True)


def add_search_result_field(embed: discord.Embed, creation: Dict[str, str], index: int, full_emoji: str, half_emoji: str, empty_emoji: str, show_hearts: bool = False):
    name = creation.get("name", "Unknown")
    username = creation.get("username", "Unknown")
    creation_id = creation.get("id", "?")
    rating = creation.get("star_rating", "N/A")
    downloads = creation.get("downloads", "0")
    views = creation.get("views", "0")
    points = creation.get("points", "0")
    hearts = creation.get("hearts", "0")

    rating_stars = rating_to_stars(rating, full_emoji, half_emoji, empty_emoji)

    field_value = (
        f"ID: `{creation_id}` | Creator: **{username}**\n"
        f"Rating: **{rating_stars}** | Downloads: **{downloads}** | Views: **{views}**\n"
        f"Points: **{points}**"
        + (f" | Hearts: **{hearts}**" if show_hearts else "")
    )

    embed.add_field(
        name=f"#{index} | {name}",
        value=field_value,
        inline=False
    )


def build_creation_search_results_embed(
    *,
    search_query: str,
    current_page: int,
    total_pages: int,
    total_results: int,
    creations: list[dict],
    full_emoji: str,
    half_emoji: str,
    empty_emoji: str,
    footer_text: str,
    footer_icon_url: str | None = None,
    show_hearts: bool = False
) -> discord.Embed:
    embed = discord.Embed(
        title=f"Search Results: {search_query}",
        description=f"Page {current_page}/{total_pages} | Total Results: {total_results}",
        color=discord.Color.yellow()
    )

    for index, creation in enumerate(creations, start=1):
        add_search_result_field(embed, creation, index, full_emoji, half_emoji, empty_emoji, show_hearts=show_hearts)

    if footer_icon_url:
        embed.set_footer(text=footer_text, icon_url=footer_icon_url)
    else:
        embed.set_footer(text=footer_text)
    return embed


def build_creation_complaints_embed(
    *,
    items: list[dict],
    current_page: int,
    per_page: int,
    total_pages: int | None,
    reporter_names: list[str],
    creator_names: list[str],
    creation_names: list[str]
) -> discord.Embed:
    total_pages_text = str(total_pages) if total_pages is not None else "?"
    embed = discord.Embed(
        title="Creation Complaints",
        description=f"Page {current_page}/{total_pages_text}",
        color=discord.Color.yellow()
    )

    start_index = (current_page - 1) * per_page
    for index, (item, reporter_name, creator_name, creation_name) in enumerate(
        zip(items, reporter_names, creator_names, creation_names),
        start=1,
    ):
        reporter_id = item.get("UserId")
        creator_id = item.get("PlayerId")
        creation_id = item.get("PlayerCreationId")
        reason = item.get("Reason", "UNKNOWN")
        embed.add_field(
            name=f"Complaint #{start_index + index}",
            value=(
                f"Reporter: **{reporter_name}** (`{reporter_id}`)\n"
                f"Creator: **{creator_name}** (`{creator_id}`)\n"
                f"Creation: **{creation_name}** (`{creation_id}`)\n"
                f"Reason: **{reason}**"
            ),
            inline=False
        )

    if not items:
        embed.description += "\nNo complaints found."

    return embed


def build_banned_creations_embed(
    *,
    items: list[dict],
    current_page: int,
    total_pages: int | None,
    total_items: int | None,
    player_names: list[str]
) -> discord.Embed:
    total_pages_text = str(total_pages) if total_pages is not None else "?"
    embed = discord.Embed(
        title="Banned Creations",
        description=f"Page {current_page}/{total_pages_text}",
        color=discord.Color.yellow()
    )

    if total_items is not None:
        embed.set_footer(text=f"Total: {total_items}")

    if not items:
        embed.description += "\nNo banned creations found."
        return embed

    for creation, player_name in zip(items, player_names):
        cid = creation.get("ID", "?")
        name = creation.get("Name", "Unknown")
        ctype = creation.get("Type", "?")
        ctype_label = CREATION_TYPE_LABELS.get(ctype, f"Unknown ({ctype})")

        player_id = creation.get("PlayerID")
        player_id_text = player_id if player_id is not None else "?"
        embed.add_field(
            name=name,
            value=f"ID: `{cid}`\nType: `{ctype_label}`\nPlayer: `{player_name}` (`{player_id_text}`)",
            inline=False
        )

    return embed
