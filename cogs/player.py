import discord
from discord import app_commands
from discord.ext import commands
import time

from config import URL
from utils import *


class Player(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="player", description="Get a player's stats")
    @app_commands.describe(username="The player to get stats for")
    async def player(self, interaction: discord.Interaction, username: str) -> None:
        player_stats = get_player_stats(username)
        
        if isinstance(player_stats, str):
            await interaction.response.send_message(player_stats, ephemeral=True)
            return
        
        user_id = player_stats.get("userId")
        is_banned = player_stats.get("isBanned")
        created_at = player_stats.get("createdAt")
        presence = player_stats.get("presence")
        skill_level_id = player_stats.get("skillLevelId")
        
        embed = discord.Embed(title=f"{username}")
        embed.description = f"{player_stats.get('quote', '')}"
        embed.set_image(url=f"{URL}/player_avatars/MNR/{user_id}/secondary.png?{int(time.time())}")  # Just to prevent caching issues
        
        embed, file = skill_level_id_to_image(skill_level_id, embed)
        
        if is_banned:
            embed.color = discord.Color.red()
        else:
            embed.color = discord.Color.green()
            
        embed.add_field(name="Star Rating", value=player_stats.get("starRating"), inline=False)
        embed.add_field(name="Skill Level", value=player_stats.get("skillLevelName", "Unknown"), inline=True)
        embed.add_field(name="Online Races", value=player_stats.get("onlineRaces"), inline=True)
        embed.add_field(name="Online Wins", value=player_stats.get("onlineWins"), inline=True)
        embed.add_field(name="Creation XP", value=player_stats.get("creationPoints"), inline=True)
        embed.add_field(name="Race XP", value=player_stats.get("raceXp"), inline=True)
        embed.add_field(name="Presence", value=rename_presence(presence), inline=False)
        embed.add_field(name="Created", value=convert_datetime_to_discord_date(created_at), inline=False)
        
        embed.set_footer(text=f"Player ID: {user_id} | Requested by: {interaction.user}", icon_url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed, file=file)
        
    @app_commands.command(name="avatar", description="Get a player's avatar")
    @app_commands.describe(username="The player to get the avatar for")
    @app_commands.describe(avatar_type="Avatar type: 'primary' or 'secondary'")
    @app_commands.choices(avatar_type=[
        app_commands.Choice(name="Primary", value="primary"),
        app_commands.Choice(name="Secondary", value="secondary")
    ])
    async def avatar(self, interaction: discord.Interaction, username: str, avatar_type: str = "secondary") -> None:
        player_id = get_player_id(username)
        if player_id.isdigit():
            embed = discord.Embed(title=f"{username}'s Avatar")
            embed.set_image(url=f"{URL}/player_avatars/MNR/{player_id}/{avatar_type}.png?{int(time.time())}")
            
            embed.set_footer(text=f"Player ID: {player_id} | Requested by: {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(player_id, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Player(bot))
