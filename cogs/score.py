import discord
from discord import app_commands
from discord.ext import commands
import time

from config import URL
from utils import *


class Score(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="hotlap", description="Get the current hotlap best times.")
    async def hotlap(self, interaction: discord.Interaction) -> None:
        hotlap_scores = get_hotlap_scores()
        
        if hotlap_scores == "Error: Unable to fetch hotlap scores.":
            await interaction.response.send_message(hotlap_scores, ephemeral=True)
            return

        embed = discord.Embed(title=f"{hotlap_scores.get('name')}")
        embed.set_thumbnail(url=f"{URL}/player_creations/{hotlap_scores.get('id')}/preview_image.png")
        embed.add_field(name="Rating", value=hotlap_scores.get("rating"), inline=True)
        embed.add_field(name="Creator", value=hotlap_scores.get("creatorUsername"), inline=True)
        embed.add_field(name="Reset In", value=reset_in_seconds_to_discord_timestamp(hotlap_scores.get("resetInSeconds")), inline=True)
        
        top_times = hotlap_scores.get("topTimes", [])

        if top_times:
            leaderboard = ""

            for time in top_times:
                leaderboard += (
                    f"**#{time['rank']}** (`{time['scoreId']}`)\n"
                    f"{time['playerUsername']} - `{format_time(time['bestLapTime'])}`\n"
                )

            embed.add_field(
                name="Top Times",
                value=leaderboard,
                inline=False
            )
        else:
            embed.add_field(
                name="Top Times",
                value="No times have been set yet.",
                inline=False
            )

        await interaction.response.send_message(embed=embed)
        
    @app_commands.command(name="time-trials", description="Get a time trial by track ID.")
    @app_commands.describe(track_id="The track ID to get time trials for")
    async def time_trials(self, interaction: discord.Interaction, track_id: int) -> None:
        time_trial_scores = get_time_trial_scores(track_id)
        
        if time_trial_scores == "Error: Unable to fetch time trial scores.":
            await interaction.response.send_message(time_trial_scores, ephemeral=True)
            return

        embed = discord.Embed(title=f"{time_trial_scores.get('name')}")
        embed.set_thumbnail(url=f"{URL}/player_creations/{time_trial_scores.get('id')}/preview_image.png")
        embed.add_field(name="Rating", value=time_trial_scores.get("rating"), inline=True)
        embed.add_field(name="Creator", value=time_trial_scores.get("creatorUsername"), inline=True)
        
        top_times = time_trial_scores.get("scores", [])

        if top_times:
            leaderboard = ""

            for time in top_times:
                leaderboard += (
                    f"**#{time['rank']}** (`{time['id']}`)\n"
                    f"{time['playerUsername']} - `{format_time(time['bestLapTime'])}`\n"
                )

            embed.add_field(
                name="Top Times",
                value=leaderboard,
                inline=False
            )
        else:
            embed.add_field(
                name="Top Times",
                value="No times have been set yet.",
                inline=False
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Score(bot))
