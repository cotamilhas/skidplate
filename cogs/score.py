import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import time

from config import URL
from utils import *


class Score(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="hotlap", description="Get the current hotlap best times.")
    async def hotlap(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        hotlap_scores = await asyncio.to_thread(get_hotlap_scores)
        
        if isinstance(hotlap_scores, str):
            await interaction.followup.send(hotlap_scores, ephemeral=True)
            return

        embed = discord.Embed(title="Hot Lap Leaderboard")
        embed.set_thumbnail(url=f"{URL}/player_creations/{hotlap_scores.get('id')}/preview_image.png")
        embed.color = discord.Color.yellow()
        embed.add_field(name=f"`{hotlap_scores.get('name')}`", value=f"By: _{hotlap_scores.get('creatorUsername')}_", inline=False)
        embed.add_field(name="Rating", value=hotlap_scores.get("rating"), inline=True)
        embed.add_field(name="Reset In", value=reset_in_seconds_to_discord_timestamp(hotlap_scores.get("resetInSeconds")), inline=True)
        
        top_times = hotlap_scores.get("topTimes", [])

        if top_times:
            for time in top_times:
                embed.add_field(
                    name=f"**#{time['rank']}** {time['playerUsername']} (`{time['scoreId']}`)",
                    value=f"`{format_time(time['bestLapTime'])}`",
                    inline=False
                )   
        else:
            embed.add_field(
                name="Top Times",
                value="No times have been set yet.",
                inline=False
            )

        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="time-trials", description="Get a time trial by track ID.")
    @app_commands.describe(track_id="The track ID to get time trials for")
    async def time_trials(self, interaction: discord.Interaction, track_id: int) -> None:
        await interaction.response.defer()
        time_trial_scores = await asyncio.to_thread(get_time_trial_scores, track_id)
        
        if isinstance(time_trial_scores, str):
            await interaction.followup.send(time_trial_scores, ephemeral=True)
            return

        embed = discord.Embed(title="Time Trial Leaderboard")
        embed.color = discord.Color.yellow()
        embed.set_thumbnail(url=f"{URL}/player_creations/{time_trial_scores.get('id')}/preview_image.png")
        embed.add_field(name="Rating", value=time_trial_scores.get("rating"), inline=True)
        embed.add_field(name=f"`{time_trial_scores.get('name')}`", value=f"By: _{time_trial_scores.get('creatorUsername')}_", inline=True)
        
        top_times = time_trial_scores.get("scores", [])

        if top_times:
            for time in top_times:
                embed.add_field(
                    name=f"**#{time['rank']}** {time['playerUsername']} (`{time['scoreId']}`)",
                    value=f"`{format_time(time['bestLapTime'])}`",
                    inline=False
                )
        else:
            embed.add_field(
                name="Top Times",
                value="No times have been set yet.",
                inline=False
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Score(bot))
