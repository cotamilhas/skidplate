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
    elif presence == "CASUAL_RACE":
        return "Casual Race"
    elif presence == "RANKED_RACE":
        return "XP Race"
    elif presence == "ROAMING":
        return "ModSpot"
    
    return presence.capitalize()

def rename_creation_type(creation_type):
    if creation_type == "CHARACTER":
        return "Mod"
    elif creation_type == "KART":
        return "Kart"
    elif creation_type == "TRACK":
        return "Track"
    
    return creation_type.capitalize()

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

# maybe creating an endpoint for plg
def get_player_username(player_id):
    response = requests.get(f"{URL}/api/player?id={player_id}")

    if response.status_code == 200:
        r = response.json()
        
        username = r.get("username")
        if username:
            return username

    return "Error: Unable to fetch player username."
    
def get_player_stats(username):
    response = requests.get(f"{URL}/api/player?username={username}")

    if response.status_code == 200:
        r = response.json()
        
        error = r.get("error")
        
        if error == "error_player_not_found":
            return "Error: Player not found."
        
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

def get_creation_stats(creation_id):
    response = requests.get(f"{URL}/api/creation/{creation_id}")

    if response.status_code == 200:
        r = response.json()
        
        error = r.get("error")
        
        if error == "error_creation_not_found":
            return "Error: Creation not found."
        
        is_track = r.get("type") == "TRACK"

        return {
            "id": r.get("playerCreationId"),
            "name": r.get("name"),
            "description": r.get("description"),
            "rating": r.get("rating"),
            "creatorUsername": r.get("creatorUsername"),
            "type": r.get("type"),
            "tags": r.get("tags"),
            "isMNR": r.get("isMNR"),
            "createdAt": r.get("createdAt"),
            "downloads": r.get("downloads", {}).get("all_time"),
            "views": r.get("views", {}).get("all_time"),
            "points": r.get("points", {}).get("all_time"),

            "bestLapTime": (
                r.get("records", {}).get("bestLapTime")
                if is_track else None
            ),

            "longestDrift": (
                r.get("longestDrift", {}).get("longestDrift")
                if is_track else None
            ),

            "longestHangTime": (
                r.get("longestHangTime", {}).get("longestHangTime")
                if is_track else None
            )
        }

    return "Error: Unable to fetch creation stats."

def get_creations_stats_by_query(
    query,
    creation_type=None,
    platform=None,
    is_mnr=None,
    page=1,
    per_page=6,
):
    params: dict[str, str | int] = {
        "query": query,
        "page": page,
        "perPage": per_page,
    }

    if creation_type is not None:
        params["type"] = creation_type

    if platform is not None:
        params["platform"] = platform

    resolved_is_mnr = True if is_mnr is None else is_mnr
    params["isMnr"] = str(resolved_is_mnr).lower()

    response = requests.get(f"{URL}/api/creations/search", params=params)

    if response.status_code == 200:
        r = response.json()
        
        error = r.get("error")
                
        if error == "error_creation_not_found":
            return "Error: Creation not found."

        return {
            "total": r.get("total", 0),
            "creations": [
                {
                    "id": c.get("playerCreationId"),
                    "name": c.get("name"),
                    "description": c.get("description"),
                    "rating": c.get("rating"),
                    "creatorUsername": c.get("creatorUsername"),
                    "type": c.get("type"),
                    "tags": c.get("tags"),
                    "isMNR": c.get("isMNR"),
                    "createdAt": c.get("createdAt"),
                    "downloads": c.get("downloads", {}).get("all_time"),
                    "views": c.get("views", {}).get("all_time"),
                    "points": c.get("points", {}).get("all_time"),
                    "bestLapTime": (
                        c.get("records", {}).get("bestLapTime")
                        if c.get("type") == "TRACK" else None
                    ),
                    "longestDrift": (
                        c.get("records", {}).get("longestDrift")
                        if c.get("type") == "TRACK" else None
                    ),
                    "longestHangTime": (
                        c.get("records", {}).get("longestHangTime")
                        if c.get("type") == "TRACK" else None
                    ),
                }
                for c in r.get("creations", [])
            ],
        }

    return "Error: Unable to fetch creations stats."

def get_creations_stats_by_username(
    username,
    creation_type=None,
    platform=None,
    is_mnr=None,
    page=1,
    per_page=6,
):
    params: dict[str, str | int] = {
        "page": page,
        "perPage": per_page,
    }

    if creation_type is not None:
        params["type"] = creation_type

    if platform is not None:
        params["platform"] = platform

    is_mnr = True if is_mnr is None else is_mnr
    params["isMnr"] = str(is_mnr).lower()

    response = requests.get(f"{URL}/api/creations/{username}", params=params)

    if response.status_code == 200:
        r = response.json()
        
        error = r.get("error")
                
        if error == "error_creation_not_found":
            return "Error: Creation not found."

        return {
            "total": r.get("total", 0),
            "creations": [
                {
                    "id": c.get("playerCreationId"),
                    "name": c.get("name"),
                    "description": c.get("description"),
                    "rating": c.get("rating"),
                    "creatorUsername": c.get("creatorUsername"),
                    "type": c.get("type"),
                    "tags": c.get("tags"),
                    "isMNR": c.get("isMNR"),
                    "createdAt": c.get("createdAt"),
                    "downloads": c.get("downloads", {}).get("all_time"),
                    "views": c.get("views", {}).get("all_time"),
                    "points": c.get("points", {}).get("all_time"),
                    "bestLapTime": (
                        c.get("records", {}).get("bestLapTime")
                        if c.get("type") == "TRACK" else None
                    ),
                    "longestDrift": (
                        c.get("records", {}).get("longestDrift")
                        if c.get("type") == "TRACK" else None
                    ),
                    "longestHangTime": (
                        c.get("records", {}).get("longestHangTime")
                        if c.get("type") == "TRACK" else None
                    ),
                }
                for c in r.get("creations", [])
            ],
        }

    return "Error: Unable to fetch creations stats."

def get_topmods():
    response = requests.get(f"{URL}/api/topmods")

    if response.status_code == 200:
        r = response.json()

        if isinstance(r, dict):
            creations_data = r.get("creations", [])
        elif isinstance(r, list):
            creations_data = r
        else:
            return "Error: Unable to fetch top mods."

        return [
            {
                "id": c.get("id", c.get("playerCreationId")),
                "name": c.get("name"),
                "description": c.get("description"),
                "rating": c.get("rating"),
                "creatorUsername": c.get("creatorUsername"),
                "type": c.get("type"),
                "tags": c.get("tags"),
                "createdAt": c.get("createdAt"),
                "downloads": (
                    c.get("downloads", {}).get("all_time")
                    if isinstance(c.get("downloads"), dict)
                    else c.get("downloads")
                ),
                "views": (
                    c.get("views", {}).get("all_time")
                    if isinstance(c.get("views"), dict)
                    else c.get("views")
                ),
                "points": (
                    c.get("points", {}).get("all_time")
                    if isinstance(c.get("points"), dict)
                    else c.get("points")
                ),
            }
            for c in creations_data
        ]

    return "Error: Unable to fetch top mods."

def get_topkarts():
    response = requests.get(f"{URL}/api/topkarts")

    if response.status_code == 200:
        r = response.json()

        if isinstance(r, dict):
            creations_data = r.get("creations", [])
        elif isinstance(r, list):
            creations_data = r
        else:
            return "Error: Unable to fetch top karts."

        return [
            {
                "id": c.get("id", c.get("playerCreationId")),
                "name": c.get("name"),
                "description": c.get("description"),
                "rating": c.get("rating"),
                "creatorUsername": c.get("creatorUsername"),
                "type": c.get("type"),
                "tags": c.get("tags"),
                "createdAt": c.get("createdAt"),
                "downloads": (
                    c.get("downloads", {}).get("all_time")
                    if isinstance(c.get("downloads"), dict)
                    else c.get("downloads")
                ),
                "views": (
                    c.get("views", {}).get("all_time")
                    if isinstance(c.get("views"), dict)
                    else c.get("views")
                ),
                "points": (
                    c.get("points", {}).get("all_time")
                    if isinstance(c.get("points"), dict)
                    else c.get("points")
                ),
            }
            for c in creations_data
        ]

    return "Error: Unable to fetch top karts."

def get_toptracks():
    response = requests.get(f"{URL}/api/toptracks")

    if response.status_code == 200:
        r = response.json()

        if isinstance(r, dict):
            creations_data = r.get("creations", [])
        elif isinstance(r, list):
            creations_data = r
        else:
            return "Error: Unable to fetch top tracks."

        return [
            {
                "id": c.get("id", c.get("playerCreationId")),
                "name": c.get("name"),
                "description": c.get("description"),
                "rating": c.get("rating"),
                "creatorUsername": c.get("creatorUsername"),
                "type": c.get("type"),
                "tags": c.get("tags"),
                "createdAt": c.get("createdAt"),
                "downloads": (
                    c.get("downloads", {}).get("all_time")
                    if isinstance(c.get("downloads"), dict)
                    else c.get("downloads")
                ),
                "views": (
                    c.get("views", {}).get("all_time")
                    if isinstance(c.get("views"), dict)
                    else c.get("views")
                ),
                "points": (
                    c.get("points", {}).get("all_time")
                    if isinstance(c.get("points"), dict)
                    else c.get("points")
                ),
            }
            for c in creations_data
        ]

    return "Error: Unable to fetch top tracks."

def get_players_online_presence(is_mnr=None, page=1, per_page=6):
    response = requests.get(f"{URL}/api/playercounts/presence?&isMnr={str(is_mnr).lower() if is_mnr is not None else 'true'}&page={page}&perPage={per_page}")

    if response.status_code == 200:
        r = response.json()
        
        if isinstance(r, dict):
            return {
                "total": r.get("total", 0),
                "creations": [
                    {
                        "id": c.get("userId"),
                        "username": c.get("username"),
                        "presence": c.get("presence"),
                        "platform": c.get("platform"),
                        "IsMNR": c.get("isMNR"),
                        "IsRpcn": c.get("isRpcn")
                    }
                    for c in r.get("presence", [])
                ],
            }
        
    return "Error: Unable to fetch players online count."

def get_players_online_count():
    response = requests.get(f"{URL}/api/playercounts/sessioncount")

    if response.status_code == 200:
        players_online = response.text
        
        return players_online
        
    return "Error: Unable to fetch players online count."

def get_total_creations_count():
    response = requests.get(f"{URL}/api/creationcount")

    if response.status_code == 200:
        r = response.json()
        
        return {
            "totalMNR": r.get("totalMNR"),
            "totalMods": r.get("mnr", {}).get("PS3", {}).get("CHARACTER"),
            "totalKarts": r.get("mnr", {}).get("PS3", {}).get("KART"),
            "totalTracks": r.get("mnr", {}).get("PS3", {}).get("TRACK")
        }
        
    return "Error: Unable to fetch total creations count."

def get_total_players_count():
    response = requests.get(f"{URL}/api/playercounts")

    if response.status_code == 200:
        player_count = response.text
        
        if player_count.isdigit():
            return player_count
        
    return "Error: Unable to fetch total players count."

def get_instance_name():
    response = requests.get(f"{URL}/api/GetInstanceName")

    if response.status_code == 200:
        return response.text

    return "Error: Unable to fetch instance name."