import requests
import discord
from config import URL


def convert_datetime_to_discord_date(timestamp):
    from datetime import datetime
    if not timestamp:
        return "Unknown"
    dt = datetime.fromisoformat(timestamp)
    return f"<t:{int(dt.timestamp())}:F>"

def rename_presence(presence):
    if presence == "OFFLINE":
        return "Offline"
    elif presence == "ONLINE":
        return "Online"
    elif presence == "INGAME":
        return "In Game"
    elif presence == "LOBBY":
        return "Lobby"
    elif presence == "CAREER_CHALLENGE":
        return "Career Challenge"
    elif presence == "IDLING":
        return "AFK"
    elif presence == "IN_POD":
        return "Pod"
    elif presence == "IN_STUDIO":
        return "Creation Station"
    elif presence == "KART_PARK_CHALLENGE":
        return "Kart Park Challenge"
    elif presence == "RANKED_RACE":
        return "XP Race"
    elif presence == "ROAMING":
        return "ModSpot"
    
    return presence.capitalize()

def skill_level_id_to_image(id, embed):
    file_name = f"{id}.PNG"
    path = f"img/levels/{file_name}"
    
    file = discord.File(path, filename=file_name)
    embed.set_thumbnail(url=f"attachment://{file_name}")
    
    return embed, file
    

def get_player_id(username):
    response = requests.get(f"{URL}/api/usernameToId?username={username}")

    if response.status_code == 200:
        player_id = response.text
        
        if player_id.isdigit():
            return player_id

    return "Error: Unable to fetch player ID."
    
def get_player_stats(username):
    response = requests.get(f"{URL}/api/player?username={username}")

    if response.status_code == 200:
        r = response.json()
        
        return {
            "userId": r.get("userId"),
            "quote": r.get("quote"),
            "starRating": r.get("starRating"),
            "onlineRaces": r.get("onlineRaces") + r.get("onlineFinished") + r.get("onlineForfeits"),
            "onlineWins": r.get("onlineWins"),
            "winStreak": r.get("winStreak"),
            "longestWinStreak": r.get("longestWinStreak"),
            "skillLevelId": r.get("skillLevels", {}).get("PS3", {}).get("id"),
            "skillLevelName": r.get("skillLevels", {}).get("PS3", {}).get("name"),
            "creationPoints": r.get("skillLevels", {}).get("PS3", {}).get("creationPoints"),
            "raceXp": r.get("skillLevels", {}).get("PS3", {}).get("raceXp"),
            "skillRating": r.get("skillRating"),
            "longestDrift": r.get("longestDrift"),
            "longestHangTime": r.get("longestHangTime"),
            "presence": r.get("presence"),
            "isBanned": r.get("isBanned"),
            "createdAt": r.get("createdAt"),
            "totalMods": r.get("creationsCount", {}).get("mnr", {}).get("PS3", {}).get("CHARACTER"),
            "totalKarts": r.get("creationsCount", {}).get("mnr", {}).get("PS3", {}).get("KART"),
            "totalTracks": r.get("creationsCount", {}).get("mnr", {}).get("PS3", {}).get("TRACK")
        }

    return "Error: Unable to fetch player stats."
