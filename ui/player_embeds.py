import discord
from typing import Dict
from utils import presence_lookup, rating_to_stars, to_discord_timestamp


def add_player_fields_to_embed(
    embed: discord.Embed,
    info: Dict[str, str],
    show_win_rate: bool,
    full_emoji: str,
    half_emoji: str,
    empty_emoji: str
):
    rating_stars = rating_to_stars(info.get("star_rating", "0"), full_emoji, half_emoji, empty_emoji)

    online_races = int(info.get("online_finished", "0")) + int(info.get("online_forfeit", "0")) + int(info.get("online_disconnected", "0"))
    online_wins = int(info.get("online_wins", "0"))
    win_rate = (online_wins / online_races) * 100 if online_races > 0 else 0

    if show_win_rate:
        embed.add_field(name="Rating", value=rating_stars, inline=False)

    embed.add_field(name="Online Races", value=online_races, inline=True)
    embed.add_field(name="Online Wins", value=online_wins, inline=True)

    if show_win_rate:
        embed.add_field(name="Win Rate", value=f"{win_rate:.2f}%", inline=True)
    else:
        embed.add_field(name="Rating", value=rating_stars, inline=True)

    embed.add_field(name="Longest Drift", value=info.get("longest_drift", "0"), inline=True)
    embed.add_field(name="Longest Air Time", value=info.get("longest_hang_time", "0"), inline=True)
    embed.add_field(name="Longest Win Streak", value=info.get("longest_win_streak", "0"), inline=True)

    presence = presence_lookup(info.get("presence", "OFFLINE"))
    embed.add_field(name="Presence", value=presence, inline=False)

    if info.get("created_at"):
        embed.add_field(name="Created At", value=to_discord_timestamp(info["created_at"]), inline=False)


def build_player_complaints_embed(
    *,
    items: list[dict],
    current_page: int,
    per_page: int,
    total_pages: int | None,
    reporter_names: list[str],
    reported_names: list[str]
) -> discord.Embed:
    total_pages_text = str(total_pages) if total_pages is not None else "?"
    embed = discord.Embed(
        title="Player Complaints",
        description=f"Page {current_page}/{total_pages_text}",
        color=discord.Color.yellow()
    )

    start_index = (current_page - 1) * per_page
    for index, (item, reporter_name, reported_name) in enumerate(
        zip(items, reporter_names, reported_names),
        start=1
    ):
        reporter_id = item.get("UserId")
        reported_id = item.get("PlayerId")
        reason = item.get("Reason", "UNKNOWN")
        embed.add_field(
            name=f"Complaint #{start_index + index}",
            value=(
                f"Reporter: **{reporter_name}** (`{reporter_id}`)\n"
                f"Reported: **{reported_name}** (`{reported_id}`)\n"
                f"Reason: **{reason}**"
            ),
            inline=False
        )

    if not items:
        embed.description += "\nNo complaints found."

    return embed


def build_banned_players_embed(
    *,
    items: list[dict],
    current_page: int,
    total_pages: int | None,
    total_items: int | None
) -> discord.Embed:
    total_pages_text = str(total_pages) if total_pages is not None else "?"
    embed = discord.Embed(
        title="Banned Players",
        description=f"Page {current_page}/{total_pages_text}",
        color=discord.Color.yellow()
    )

    if total_items is not None:
        embed.set_footer(text=f"Total: {total_items}")

    if not items:
        embed.description += "\nNo banned players found on this page."
        return embed

    for user in items:
        uid = user.get("ID", "?")
        username = user.get("Username", "Unknown")
        embed.add_field(
            name=f"**{username}**",
            value=f"ID: `{uid}`",
            inline=False
        )

    return embed
