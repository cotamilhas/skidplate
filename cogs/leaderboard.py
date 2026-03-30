import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import xml.etree.ElementTree as ET
from config import EMBED_COLOR, URL, FULL, HALF, EMPTY
from utils import debug, format_time, rating_to_stars, CreationDataFetcher


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.creation_fetcher = CreationDataFetcher(self.session, URL)

    LEADERBOARD_TYPE_CHOICES = [
        app_commands.Choice(name="Daily", value="DAILY"),
        app_commands.Choice(name="Last Month", value="LAST_MONTH"),
        app_commands.Choice(name="Last Week", value="LAST_WEEK"),
        app_commands.Choice(name="Lifetime", value="LIFETIME"),
        app_commands.Choice(name="Monthly", value="MONTHLY"),
        app_commands.Choice(name="Weekly", value="WEEKLY")
    ]

    GAME_TYPE_CHOICES = [
        app_commands.Choice(name="Character Creators", value="CHARACTER_CREATORS"),
        app_commands.Choice(name="Kart Creators", value="KART_CREATORS"),
        app_commands.Choice(name="Track Creators", value="TRACK_CREATORS"),
        app_commands.Choice(name="Online Action Race", value="ONLINE_ACTION_RACE"),
        app_commands.Choice(name="Online Pure Race", value="ONLINE_PURE_RACE"),
        app_commands.Choice(name="Online Time Trial Race", value="ONLINE_TIME_TRIAL_RACE"),
        app_commands.Choice(name="Overall", value="OVERALL"),
        app_commands.Choice(name="Overall Creators", value="OVERALL_CREATORS"),
        app_commands.Choice(name="Overall Race", value="OVERALL_RACE")
    ]

    PLATFORM_CHOICES = [
        app_commands.Choice(name="PS3", value="PS3"),
        app_commands.Choice(name="PSP", value="PSP"),
        app_commands.Choice(name="PSV", value="PSV")
    ]
    
    async def cog_unload(self):
        await self.session.close()

    @app_commands.command(
        name="hotlap",
        description="Shows the top 10 fastest hotlap times (PS3)"
    )
    async def hotlap(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        url = (f"{URL}leaderboards/view.xml"
            f"?type=LIFETIME&game_type=ONLINE_HOT_SEAT_RACE"
            f"&platform=PS3&page=1&per_page=100")

        debug(f"Fetching hotlap leaderboard: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await interaction.followup.send("Failed to fetch hotlap data.")
                    return
                data = await resp.text()

        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            await interaction.followup.send(f"XML Parse Error: {e}")
            return

        leaderboard_elem = root.find(".//leaderboard")
        if leaderboard_elem is None:
            await interaction.followup.send("No hotlap data found.")
            return

        top_players = []
        page_num = 1
        
        while True:
            url_page = (f"{URL}leaderboards/view.xml"
                    f"?type=LIFETIME&game_type=ONLINE_HOT_SEAT_RACE"
                    f"&platform=PS3&page={page_num}&per_page=100")

            async with aiohttp.ClientSession() as session:
                async with session.get(url_page) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.text()
                    
            try:
                root = ET.fromstring(data)
            except ET.ParseError:
                break

            leaderboard_elem = root.find(".//leaderboard")
            if leaderboard_elem is None:
                break

            items = leaderboard_elem.findall("player")
            if not items:
                break

            for player in items:
                username = player.attrib.get("username", "Unknown")
                best_lap = player.attrib.get("best_lap_time")
                if best_lap and best_lap != "N/A":
                    top_players.append({
                        "username": username,
                        "best_lap": best_lap,
                        "rank": player.attrib.get("rank", "?"),
                        "track_idx": player.attrib.get("track_idx")
                    })
            page_num += 1

        if not top_players:
            await interaction.followup.send("No hotlap data found.")
            return

        def lap_key(p):
            try:
                return float(p["best_lap"])
            except Exception:
                return float('inf')

        top_players_sorted = sorted(top_players, key=lap_key)[:10]
        track_idx = top_players_sorted[0]["track_idx"]
        track_info = await self.creation_fetcher.get_track_info(track_idx)

        track_rating_stars = "N/A"
        if track_idx is not None:
            try:
                creation_info = await self.creation_fetcher.get_creation_info(int(track_idx))
                if creation_info:
                    track_rating_stars = rating_to_stars(
                        creation_info.get("star_rating", "0"),
                        FULL,
                        HALF,
                        EMPTY,
                    )
            except (ValueError, TypeError):
                debug(f"Invalid track index for rating lookup: {track_idx}")

        embed = discord.Embed(
            title="Hot Lap Leaderboard",
            color=EMBED_COLOR
        )

        if track_info:
            embed.description = (
                f"`{track_info['name']}`\n"
                f"By *{track_info['creator']}*\n\n"
            )
            embed.set_thumbnail(url=track_info["thumbnail"])

        embed.add_field(name="Rating", value=f"**{track_rating_stars}**", inline=False)

        for i, player in enumerate(top_players_sorted, 1):
            formatted_time = format_time(player["best_lap"])
            embed.add_field(
                name=f"#{i} {player['username']}",
                value=f"**{formatted_time}**",
                inline=False
            )

        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
        await interaction.followup.send(embed=embed)

    # TODO: Implement full leaderboard command with all options
    # @app_commands.command(
    #     name="leaderboard",
    #     description="Shows the top players or creators on the leaderboard."
    # )
    # @app_commands.choices(
    #     board_type=LEADERBOARD_TYPE_CHOICES,
    #     game_type=GAME_TYPE_CHOICES,
    #     platform=PLATFORM_CHOICES
    # )
    # async def leaderboard(
    #     self,
    #     interaction: discord.Interaction,
    #     board_type: app_commands.Choice[str] = None,
    #     game_type: app_commands.Choice[str] = None,
    #     platform: app_commands.Choice[str] = None,
    #     page: int = 1
    # ):
    #     # Implementation here
    #     pass


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))