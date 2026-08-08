import requests
import discord
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum

from config import URL, MODERATOR_PERMISSIONS


class CreationType(Enum):
    PHOTO = 0
    PLANET = 1
    TRACK = 2
    ITEM = 3
    STORY = 4
    DELETED = 5
    CHARACTER = 6
    KART = 7


class Platform(Enum):
    PS2 = 0
    PSP = 1
    PS3 = 2
    WEB = 3
    PSV = 4


class PresenceName(Enum):
    OFFLINE = "Offline"
    ONLINE = "Online"
    INGAME = "In Game"
    LOBBY = "Lobby"
    CAREER_CHALLENGE = "Career Challenge"
    IDLING = "AFK"
    IN_POD = "Pod"
    IN_STUDIO = "Creation Station"
    KART_PARK_CHALLENGE = "Kart Park Challenge"
    CASUAL_RACE = "Casual Race"
    RANKED_RACE = "XP Race"
    ROAMING = "ModSpot"


class CreationTypeName(Enum):
    PHOTO = "Photo"
    PLANET = "Planet"
    TRACK = "Track"
    STORY = "Story Level"
    DELETED = "Removed Creation"
    CHARACTER = "Mod"
    KART = "Kart"
    


PLATFORMS = {member.name: member.value for member in Platform}
PRESENCE_NAMES = {member.name: member.value for member in PresenceName}
CREATION_TYPE_NAMES = {member.name: member.value for member in CreationTypeName}


def get_platform_name(platform_id):
    if platform_id is None:
        return None

    if isinstance(platform_id, str):
        normalized = platform_id.strip().upper()
        if normalized.isdigit():
            platform_id = int(normalized)
        else:
            try:
                return Platform[normalized].name
            except KeyError:
                return None

    try:
        return Platform(platform_id).name
    except (TypeError, ValueError):
        return None


def rename_presence(presence):
    if not presence:
        return "Unknown"

    try:
        return PresenceName[presence.upper()].value
    except (AttributeError, KeyError):
        return presence.replace("_", " ").title()


def rename_creation_type(creation_type):
    if not creation_type:
        return "Unknown"

    try:
        return CreationTypeName[creation_type.upper()].value
    except (AttributeError, KeyError):
        return creation_type.replace("_", " ").title()

def rename_complaint(complaint):
    if complaint == "ILLEGAL":
        return "Illegal Act"
    elif complaint == "TOS":
        return "Terms of Service"
    elif complaint == "VULGAR":
        return "Vulgar/Swearing"

    return complaint.replace("_", " ").title()

def convert_datetime_to_discord_date(timestamp):
    if not timestamp:
        return "Unknown"
    dt = datetime.fromisoformat(timestamp)
    return f"<t:{int(dt.timestamp())}:F>"

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

def get_creation_name(creation_id):
    response = requests.get(f"{URL}/api/creation/{creation_id}")

    if response.status_code == 200:
        r = response.json()
        
        error = r.get("error")
        
        if error == "error_creation_not_found":
            return "Error: Creation not found."
        
        return r.get("name")

    return "Error: Unable to fetch creation name."

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

    is_mnr = True if is_mnr is None else is_mnr
    params["isMnr"] = str(is_mnr).lower()

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

def reset_in_seconds_to_discord_timestamp(seconds):
    future_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return f"<t:{int(future_time.timestamp())}:R>"

def format_time(time):
    if isinstance(time, str) and ":" in time:
        parts = time.split(":")
        if len(parts) == 3:
            minutes = int(parts[0])
            seconds = int(parts[1])
            milliseconds = int(parts[2])
            return f"{minutes:02}:{seconds:02}:{milliseconds:03}"
        if len(parts) == 2:
            seconds = int(parts[0])
            milliseconds = int(parts[1])
            return f"00:{seconds:02}:{milliseconds:03}"

    total_ms = int((Decimal(str(time)) * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    minutes = total_ms // 60000
    seconds = (total_ms % 60000) // 1000
    milliseconds = total_ms % 1000

    return f"{minutes:02}:{seconds:02}:{milliseconds:03}"

def get_hotlap_scores():
    response = requests.get(f"{URL}/api/hotlap")

    if response.status_code == 200:
        r = response.json()
        
        return {
            "id": r.get("track", {}).get("id"),
            "name": r.get("track", {}).get("name"),
            "rating": r.get("track", {}).get("rating"),
            "creatorUsername": r.get("track", {}).get("creatorUsername"),
            "resetInSeconds": r.get("resetInSeconds"),
            "topTimes": [
                {
                    "rank": t.get("rank"),
                    "scoreId": t.get("scoreId"),
                    "playerUsername": t.get("playerUsername"),
                    "bestLapTime": t.get("bestLapTime"),
                    "updatedAt": t.get("updatedAt"),
                }
                for t in r.get("topTimes", [])
            ]
        }
        
    return "Error: Unable to fetch hotlap scores."

def get_time_trial_scores(track_id):
    response = requests.get(f"{URL}/api/score?trackId={track_id}&page=1&perPage=10")

    if response.status_code == 200:
        r = response.json()
        
        return {
            "id": r.get("track", {}).get("id"),
            "name": r.get("track", {}).get("name"),
            "rating": r.get("track", {}).get("rating"),
            "creatorUsername": r.get("track", {}).get("creatorUsername"),
            "scores": [
                {
                    "rank": t.get("rank"),
                    "id": t.get("id"),
                    "playerUsername": t.get("playerUsername"),
                    "bestLapTime": t.get("bestLapTime"),
                    "updatedAt": t.get("updatedAt"),
                }
                for t in r.get("scores", [])
            ]
        }
        
    return "Error: Unable to fetch time trial scores."

# moderation functions
def moderator_login(username, password):
    response = requests.post(f"{URL}/api/moderation/login?login={username}&password={password}")

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            token = response.cookies.get("Token")
            return token
        
        elif r == "error":
            return "Error: Invalid credentials."
        
    return "Error: Unable to login as moderator."

def refresh_moderator_token(token):
    headers = { "Authorization": f"Bearer {token}"}
    
    response = requests.post(f"{URL}/api/moderation/refresh_token", headers=headers)

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            token = response.cookies.get("Token")
            return token
        
    return "Error: Unable to refresh moderator token."

def get_moderator_id(token, username):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    response = requests.get(f"{URL}/api/moderation/{username}/id", headers=headers)

    if response.status_code == 200:
        r = response.text
        return r
    
    if response.status_code == 403:
        return "Error: You do not have permission to get moderator ID."
    
    return "Error: Unable to fetch moderator ID."

def moderator_set_player_ban(token, username, is_banned):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    player_id = get_player_id(username)
    response = requests.post(f"{URL}/api/moderation/setban?id={player_id}&isBanned={str(is_banned).lower()}", headers=headers)

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to set ban status for player."
        
    return "Error: Unable to set ban status for player."

def moderator_get_banned_player_creations(token, page=1, per_page=6, sort_order="desc"):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.get(
        f"{URL}/api/moderation/player_creations?page={page}&per_page={per_page}&status=BANNED&sortOrder={sort_order}",
        headers=headers,
    )

    if response.status_code == 200:
        return response.json()

    elif response.status_code == 403:
        return "Error: You do not have permission to view banned player creations."

    return "Error: Unable to get banned player creations."

def moderator_ban_creation(token, creation_id, is_banned):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    if is_banned:
        status = "BANNED"
    else:
        status = "APPROVED"
        
    response = requests.post(f"{URL}/api/moderation/setStatus?id={creation_id}&status={status}", headers=headers)

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to set ban status for creation."
        
    return "Error: Unable to set ban status for creation."

def moderator_set_user_quota(token, username, quota):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    player_id = get_player_id(username)
    response = requests.post(f"{URL}/api/moderation/setUserQuota?id={player_id}&quota={quota}", headers=headers)

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to set quota for user."
        
    return "Error: Unable to set quota for user."

def moderator_user_allow_opposite_platform(token, username, allow_opposite_platform):
    headers = { "Authorization": f"Bearer {token}"}

    refresh_moderator_token(token)

    player_id = get_player_id(username)
    response = requests.post(f"{URL}/api/moderation/setUserSettings?id={player_id}&AllowOppositePlatform={str(allow_opposite_platform).lower()}", headers=headers)

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to set opposite platform allowance for user."
        
    return "Error: Unable to set opposite platform allowance for user."

def moderator_reset_player_profile(token, username, remove_creations=False):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    player_id = get_player_id(username)
    if isinstance(player_id, str) and player_id.startswith("Error:"):
        return player_id

    response = requests.delete(
        f"{URL}/api/moderation/users/{player_id}/stats",
        params={"removeCreations": str(remove_creations).lower()},
        headers=headers,
    )

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to reset player profile."
        
    return "Error: Unable to reset player profile."

def moderator_remove_player_avatars(token, username, is_mnr=True):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    player_id = get_player_id(username)
    response = requests.delete(f"{URL}/api/moderation/users/{player_id}/avatar?isMNR={str(is_mnr).lower()}", headers=headers)

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to remove player avatars."

    return "Error: Unable to remove player avatar."

def moderator_get_announcements(token, page=1, per_page=6, platform=None):
    headers = { "Authorization": f"Bearer {token}"}

    refresh_moderator_token(token)

    url = f"{URL}/api/moderation/announcements?page={page}&per_page={per_page}"
    if platform is not None:
        url += f"&platform={platform}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    
    elif response.status_code == 403:
        return "Error: You do not have permission to get announcements."

    return "Error: Unable to get announcements."

def moderator_create_announcement(token, language_code, subject, text, platform):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.post(
        f"{URL}/api/moderation/announcements?languageCode={language_code}&subject={subject}&text={text}&platform={platform}",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"

    elif response.status_code == 403:
        return "Error: You do not have permission to manage announcements."

    return "Error: Unable to create announcement."


def moderator_edit_announcement(token, announcement_id, language_code, subject, text):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.post(
        f"{URL}/api/moderation/announcements/{announcement_id}?languageCode={language_code}&subject={subject}&text={text}&platform=2",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"

    elif response.status_code == 403:
        return "Error: You do not have permission to manage announcements."

    elif response.status_code == 404:
        return "Error: Announcement not found."

    return "Error: Unable to edit announcement."


def moderator_delete_announcement(token, announcement_id):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.delete(
        f"{URL}/api/moderation/announcements/{announcement_id}",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"

    elif response.status_code == 403:
        return "Error: You do not have permission to manage announcements."

    elif response.status_code == 404:
        return "Error: Announcement not found."

    return "Error: Unable to delete announcement."

def moderator_remove_player_creation(token, creation_id):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.delete(
        f"{URL}/api/moderation/player_creations/{creation_id}",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"

    elif response.status_code == 403:
        return "Error: You do not have permission to remove player creations."

    elif response.status_code == 404:
        return "Error: Creation not found."

    return "Error: Unable to remove player creation."


def moderator_remove_player_creations(token, username):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    player_id = get_player_id(username)
    if isinstance(player_id, str) and player_id.startswith("Error:"):
        return player_id

    response = requests.delete(
        f"{URL}/api/moderation/users/{player_id}/creations",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"

    elif response.status_code == 403:
        return "Error: You do not have permission to remove player creations."

    elif response.status_code == 404:
        return "Error: Player not found."

    return "Error: Unable to remove player creations."


def moderator_get_banned_console_ids(token, page=1, per_page=6):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.get(
        f"{URL}/api/moderation/banned_console_ids?page={page}&per_page={per_page}",
        headers=headers,
    )

    if response.status_code == 200:
        return response.json()

    elif response.status_code == 403:
        return "Error: You do not have permission to manage console IDs."

    return "Error: Unable to fetch banned console IDs."


def moderator_add_banned_console_id(token, console_id):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.post(
        f"{URL}/api/moderation/banned_console_ids?consoleId={console_id}",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"
        if response.text == "error_already_exists":
            return "Error: Console ID already exists."

    elif response.status_code == 403:
        return "Error: You do not have permission to manage console IDs."

    return "Error: Unable to add banned console ID."


def moderator_remove_banned_console_id(token, console_id):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.delete(
        f"{URL}/api/moderation/banned_console_ids?consoleId={console_id}",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"

    elif response.status_code == 403:
        return "Error: You do not have permission to manage console IDs."

    elif response.status_code == 404:
        return "Error: Console ID not found."

    return "Error: Unable to remove banned console ID."


def moderator_ban_console_id_by_session(token, username):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    player_id = get_player_id(username)
    if isinstance(player_id, str) and player_id.startswith("Error:"):
        return player_id

    response = requests.post(
        f"{URL}/api/moderation/banned_console_ids/player/{player_id}",
        headers=headers,
    )

    if response.status_code == 200:
        if response.text == "ok":
            return "ok"
        if response.text == "no_active_session":
            return "Error: Player has no active session."
        if response.text == "no_console_id_found":
            return "Error: No console ID found for the player's active session."
        if response.text == "error_already_exists":
            return "Error: Console ID already exists."

    elif response.status_code == 403:
        return "Error: You do not have permission to manage console IDs."

    return "Error: Unable to add console ID by player session."

def moderator_get_player_complaints(token, page=1, per_page=1):
    headers = { "Authorization": f"Bearer {token}" }
    
    refresh_moderator_token(token)

    response = requests.get(
        f"{URL}/api/moderation/player_complaints?page={page}&per_page={per_page}",
        headers=headers,
    )

    if response.status_code == 200:
        return response.json()

    elif response.status_code == 403:
        return "Error: You do not have permission to view player complaints."

    return "Error: Unable to get player complaints."

def moderator_get_creation_complaints(token, page=1, per_page=1):
    headers = { "Authorization": f"Bearer {token}" }
    
    refresh_moderator_token(token)

    response = requests.get(
        f"{URL}/api/moderation/player_creation_complaints?page={page}&per_page={per_page}",
        headers=headers,
    )

    if response.status_code == 200:
        return response.json()

    elif response.status_code == 403:
        return "Error: You do not have permission to view creation complaints."

    return "Error: Unable to get creation complaints."

# moderator management
def create_moderator(token, username, password):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    # set permissions in the future, for now just creates the moderator
    response = requests.post(f"{URL}/api/moderation/moderators?username={username}&password={password}", headers=headers)
    
    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to create a moderator."
    
    return "Error: Unable to create moderator."

def delete_moderator(token, username):
    headers = { "Authorization": f"Bearer {token}"}
    refresh_moderator_token(token)
    
    moderator_id = get_moderator_id(token, username)
    if isinstance(moderator_id, str) and moderator_id.startswith("Error:"):
        return moderator_id
    
    response = requests.delete(f"{URL}/api/moderation/moderators/{moderator_id}", headers=headers)

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
    elif response.status_code == 403:
        return "Error: You do not have permission to delete a moderator."

    return "Error: Unable to delete moderator."

def get_moderators(token):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    response = requests.get(
        f"{URL}/api/moderation/moderators",
        params={"page": 1, "per_page": 10},
        headers=headers,
    )

    if response.status_code == 200:
        return response.json()
    
    elif response.status_code == 403:
        return "Error: You do not have permission to get moderators."

    return "Error: Unable to get moderators."


def moderator_get_moderators(token, page=1, per_page=6, sort_order="desc"):
    headers = { "Authorization": f"Bearer {token}" }

    refresh_moderator_token(token)

    response = requests.get(
        f"{URL}/api/moderation/moderators?page={page}&per_page={per_page}&sortOrder={sort_order}",
        headers=headers,
    )

    if response.status_code == 200:
        return response.json()

    elif response.status_code == 403:
        return "Error: You do not have permission to get moderators."

    return "Error: Unable to get moderators."

def moderator_get_permissions(token):
    headers = { "Authorization": f"Bearer {token}"}

    refresh_moderator_token(token)

    response = requests.get(f"{URL}/api/moderation/permissions", headers=headers)

    if response.status_code == 200:
        r = response.json()

        return r
    
    elif response.status_code == 404:
        return "Error: Moderator not found."

    return "Error: Unable to get moderator permissions."

def moderator_set_permissions(token, username, permissions, value):
    headers = { "Authorization": f"Bearer {token}" }
    refresh_moderator_token(token)

    moderator_id = get_moderator_id(token, username)
    if isinstance(moderator_id, str) and moderator_id.startswith("Error:"):
        return moderator_id

    if isinstance(permissions, dict):
        permission_params = {
            k: "true" if v else "false"
            for k, v in permissions.items()
            if k in MODERATOR_PERMISSIONS
        }
    elif isinstance(permissions, list) and value is not None:
        permission_params = {
            p: "true" if value else "false"
            for p in permissions
            if p in MODERATOR_PERMISSIONS
        }
    else:
        return "Error: Invalid permissions format."

    if not permission_params:
        return "Error: No valid permissions provided."

    response = requests.post(
        f"{URL}/api/moderation/{moderator_id}/set_permissions",
        params=permission_params,
        headers=headers,
    )

    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
        else:
            return "Error: Moderator not found."
    
    else:
        return "Error: Unable to set moderator permissions."
    
def moderator_set_username(token, username):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    response = requests.get(f"{URL}/api/moderation/set_username?username={username}", headers=headers)
    
    if response.status_code == 200:
        r = response.json()
        
        return r
    
    elif response.status_code == 403:
        return "Error: You do not have permission to get moderators."
    
    else:
        return "Error: Unable to get moderators."
    
def moderator_set_password(token, password):
    headers = { "Authorization": f"Bearer {token}"}
    
    refresh_moderator_token(token)
    
    response = requests.post(f"{URL}/api/moderation/set_password?password={password}", headers=headers)
    
    if response.status_code == 200:
        r = response.text
        
        if r == "ok":
            return r
        
        elif r == "error_moderator_not_found":
            return "Error: Moderator not found."
        
        # impossible to reach this point but eh
        elif r == "error_password_is_empty":
            return "Error: Password is empty."
    
    else:
        return "Error: Unable to set moderator password."
