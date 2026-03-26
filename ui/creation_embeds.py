import discord
from typing import Any, Dict, List
from utils import rating_to_stars, format_time


def trim_text(value: str, max_len: int = 250, fallback: str = "No description provided.") -> str:
    if not value:
        return fallback

    value = value.strip()
    if not value:
        return fallback

    return value if len(value) <= max_len else value[:max_len].rstrip() + "..."


def add_top_creation_fields_to_embed(embed: discord.Embed, creations: List[Dict[str, Any]], full_emoji: str, half_emoji: str, empty_emoji: str):
    if creations and creations[0].get("thumbnail"):
        embed.set_thumbnail(url=creations[0]["thumbnail"])

    for i, creation in enumerate(creations, start=1):
        name = creation.get("name", "Unknown")
        username = creation.get("username", "Unknown")
        points_today = creation.get("points_today", "0")
        points = creation.get("points", "0")
        rating = creation.get("star_rating", "N/A")
        downloads = creation.get("downloads", "0")
        short_desc = trim_text(creation.get("description", ""))

        rating_stars = rating_to_stars(rating, full_emoji, half_emoji, empty_emoji)

        field_value = (
            f"Creator: **{username}**\n"
            f"Points Today: **{points_today}** | Total Points: **{points}**\n"
            f"Rating: **{rating_stars}** | Total Downloads: **{downloads}**\n"
            f"> {short_desc}"
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


def add_search_result_field(embed: discord.Embed, creation: Dict[str, str], index: int, full_emoji: str, half_emoji: str, empty_emoji: str):
    name = creation.get("name", "Unknown")
    username = creation.get("username", "Unknown")
    creation_id = creation.get("id", "?")
    rating = creation.get("star_rating", "N/A")
    downloads = creation.get("downloads", "0")
    views = creation.get("views", "0")
    points = creation.get("points", "0")

    rating_stars = rating_to_stars(rating, full_emoji, half_emoji, empty_emoji)

    field_value = (
        f"ID: `{creation_id}` | Creator: **{username}**\n"
        f"Rating: **{rating_stars}** | Downloads: **{downloads}** | Views: **{views}**\n"
        f"Points: **{points}**"
    )

    embed.add_field(
        name=f"#{index} {name}",
        value=field_value,
        inline=False
    )
