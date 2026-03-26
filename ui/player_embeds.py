import discord
from typing import Dict
from utils import presence_lookup, rating_to_stars, to_discord_timestamp


def add_player_fields_to_embed(
    embed: discord.Embed,
    info: Dict[str, str],
    show_win_rate: bool,
    full_emoji: str,
    half_emoji: str,
    empty_emoji: str,
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
