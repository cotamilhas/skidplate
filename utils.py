import discord
import aiohttp
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import os
import tempfile
from typing import Optional, List, Dict, Any, Union
import json
from config import EMBED_COLOR, URL, DEBUG_MODE
from clients.xml_client import XMLFetcher
from clients.moderation_api import ModerationAPIHelper

def debug(msg: str):
    from config import DEBUG_MODE
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")

def presence_lookup(presence: str) -> str:
    match presence:
        case "OFFLINE":
            return "Offline"
        case "ONLINE":
            return "Online"
        case "INGAME":
            return "In Game"
        case "LOBBY":
            return "Lobby"
        case "WEB":
            return "Web"
        case "CAREER_CHALLENGE":
            return "Career Challenge"
        case "CASUAL_RACE":
            return "Casual Race"
        case "IDLING":
            return "Idling"
        case "IN_POD":
            return "In Pod"
        case "IN_STUDIO":
            return "Creation Station"
        case "KART_PARK_CHALLENGE":
            return "Kart Park Challenge"
        case "RANKED_RACE":
            return "XP Race"
        case "ROAMING":
            return "Roaming"
        case _:
            return presence

def rating_to_stars(rating: Union[str, float], full_emoji: str, half_emoji: str, empty_emoji: str) -> str:
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        return str(rating)
    
    from config import USE_EMOJIS
    
    if not USE_EMOJIS:
        return f"{rating:.1f}"
    
    rating = max(0.0, min(5.0, rating))

    full = int(rating)
    half = 1 if (rating - full) >= 0.5 else 0
    empty = 5 - full - half

    return f"{full_emoji * full}{half_emoji * half}{empty_emoji * empty}"

def format_time(time_str: str) -> str:
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 3:
                minutes = int(parts[0])
                seconds = int(parts[1])
                milliseconds = int(parts[2])
                return f"{minutes:02}:{seconds:02}:{milliseconds:03}"
            elif len(parts) == 2:
                seconds = int(parts[0])
                milliseconds = int(parts[1])
                return f"00:{seconds:02}:{milliseconds:03}"

        total_ms = int(
            (Decimal(time_str) * 1000)
            .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )

        minutes = total_ms // 60000
        seconds = (total_ms % 60000) // 1000
        milliseconds = total_ms % 1000

        return f"{minutes:02}:{seconds:02}:{milliseconds:03}"

    except Exception:
        return time_str

def to_discord_timestamp(iso_date: str) -> str:
    dt = datetime.fromisoformat(iso_date)
    return f"<t:{int(dt.timestamp())}:F>"

class PlayerDataFetcher:    
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self.session = session
        self.base_url = base_url
        self.xml_fetcher = XMLFetcher(session)

    async def get_player_id(self, username: str) -> Optional[str]:
        url = f"{self.base_url}players/to_id.xml"
        root = await self.xml_fetcher.fetch_xml(url, params={"username": username})
        if root is None:
            return None

        node = root.find(".//player_id")
        if node is not None:
            debug(f"Found player ID: {node.text}")
            return node.text

        debug("player_id not found")
        return None

    async def get_player_info(self, player_id: str) -> Optional[Dict[str, str]]:
        url = f"{self.base_url}players/{player_id}/info.xml"
        root = await self.xml_fetcher.fetch_xml(url)
        if root is None:
            return None

        player = root.find(".//player")
        if player is not None:
            debug(f"Player info: {player.attrib}")
            return player.attrib

        debug("player element not found")
        return None

    async def get_player_avatar(self, player_id: str, primary: bool = False) -> Optional[str]:
        file = "primary.png" if primary else "secondary.png"
        url = f"{self.base_url}player_avatars/MNR/{player_id}/{file}"

        debug(f"Avatar URL: {url}")

        async with self.session.get(url) as resp:
            if resp.status == 200:
                return str(resp.url)

        debug("Avatar not found")
        return None

class CreationDataFetcher:    
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self.session = session
        self.base_url = base_url
        self.xml_fetcher = XMLFetcher(session)

    async def fetch_creations(
        self,
        player_creation_type: str,
        per_page: int = 3,
        page: int = 1,
        sort_column: str = "points_today",
        sort_order: str = "desc",
        platform: str = "PS3",
    ) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}player_creations.xml"
        params = {
            "page": page,
            "per_page": per_page,
            "sort_column": sort_column,
            "player_creation_type": player_creation_type,
            "platform": platform,
            "sort_order": sort_order,
        }

        root = await self.xml_fetcher.fetch_xml(url, params=params)
        if root is None:
            return None

        pc_root = root.find(".//player_creations")
        if pc_root is None:
            debug("player_creations element not found")
            return None

        creations = []
        for elem in pc_root.findall("player_creation"):
            try:
                cid = elem.attrib.get("id")
                name = elem.attrib.get("name", "Unknown")
                username = elem.attrib.get("username", "Unknown")
                points_today = elem.attrib.get("points_today", "0")
                points = elem.attrib.get("points", "0")
                rating = elem.attrib.get("star_rating", "N/A")
                downloads = elem.attrib.get("downloads", "0")
                description = elem.attrib.get("description", "")
                thumbnail = f"{self.base_url}player_creations/{cid}/preview_image.png" if cid else None

                creations.append({
                    "id": cid,
                    "name": name,
                    "username": username,
                    "points_today": points_today,
                    "points": points,
                    "star_rating": rating,
                    "downloads": downloads,
                    "description": description,
                    "thumbnail": thumbnail
                })
            except Exception as e:
                debug(f"Error parsing player_creation element: {e}")
                continue

        return creations

    async def get_creation_info(self, creation_id: int) -> Optional[Dict[str, str]]:
        creation_url = f"{self.base_url}player_creations/{creation_id}.xml"
        root = await self.xml_fetcher.fetch_xml(creation_url)
        if root is None:
            return None

        creation_elem = root.find(".//player_creation")
        if creation_elem is None:
            return {}

        return creation_elem.attrib

    async def get_track_info(self, track_idx: int) -> Optional[Dict[str, Any]]:
        track_url = f"{self.base_url}player_creations/{track_idx}.xml"
        root = await self.xml_fetcher.fetch_xml(track_url)
        if root is None:
            return None

        track_elem = root.find(".//player_creation")
        if track_elem is None:
            return None

        track_name = track_elem.attrib.get("name", "Unknown Track")
        creator = track_elem.attrib.get("username", "Unknown Creator")
        track_id = track_elem.attrib.get("id")

        thumbnail_url = f"{self.base_url}player_creations/{track_id}/preview_image.png"

        return {
            "name": track_name,
            "creator": creator,
            "thumbnail": thumbnail_url
        }

    async def search_creations(
        self,
        search_query: str,
        player_creation_type: str = "CHARACTER",
        per_page: int = 10,
        page: int = 1,
        platform: str = "PS3",
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}player_creations/search.xml"
        params = {
            "page": page,
            "per_page": per_page,
            "platform": platform,
            "player_creation_type": player_creation_type,
            "search": search_query,
        }

        root = await self.xml_fetcher.fetch_xml(url, params=params)
        if root is None:
            return None

        pc_root = root.find(".//player_creations")
        if pc_root is None:
            debug("player_creations element not found")
            return None

        creations = []
        for elem in pc_root.findall("player_creation"):
            try:
                cid = elem.attrib.get("id")
                name = elem.attrib.get("name", "Unknown")
                username = elem.attrib.get("username", "Unknown")
                rating = elem.attrib.get("star_rating", "N/A")
                downloads = elem.attrib.get("downloads", "0")
                views = elem.attrib.get("views", "0")
                points = elem.attrib.get("points", "0")
                creation_type = elem.attrib.get("player_creation_type", "Unknown")

                creations.append({
                    "id": cid,
                    "name": name,
                    "username": username,
                    "star_rating": rating,
                    "downloads": downloads,
                    "views": views,
                    "points": points,
                    "player_creation_type": creation_type
                })
            except Exception as e:
                debug(f"Error parsing player_creation element: {e}")
                continue

        return {
            "creations": creations,
            "page": int(pc_root.get("page", 1)),
            "per_page": int(pc_root.get("row_end", per_page)) - int(pc_root.get("row_start", 0)),
            "total": int(pc_root.get("total", 0)),
            "total_pages": int(pc_root.get("total_pages", 1))
        }
        
    async def search_creations_by_player(
        self,
        username: str,
        player_creation_type: str = "CHARACTER",
        per_page: int = 10,
        page: int = 1,
        platform: str = "PS3",
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}player_creations/friends_view.xml"
        params = {
            "filters[player_creation_type]": player_creation_type,
            "filters[username]": username,
            "page": page,
            "per_page": per_page,
            "platform": platform,
            "sort_column": "created_at",
            "sort_order": "desc",
        }

        root = await self.xml_fetcher.fetch_xml(url, params=params)
        if root is None:
            return None

        pc_root = root.find(".//player_creations")
        if pc_root is None:
            debug("player_creations element not found")
            return None

        creations = []
        for elem in pc_root.findall("player_creation"):
            try:
                cid = elem.attrib.get("id")
                name = elem.attrib.get("name", "Unknown")
                rating = elem.attrib.get("star_rating", "N/A")
                downloads = elem.attrib.get("downloads", "0")
                views = elem.attrib.get("views", "0")
                points = elem.attrib.get("points", "0")
                creation_type = elem.attrib.get("player_creation_type", "Unknown")

                creations.append({
                    "id": cid,
                    "name": name,
                    "username": elem.attrib.get("username", username),
                    "star_rating": rating,
                    "downloads": downloads,
                    "views": views,
                    "points": points,
                    "player_creation_type": creation_type
                })
            except Exception as e:
                debug(f"Error parsing player_creation element: {e}")
                continue

        return {
            "creations": creations,
            "page": int(pc_root.get("page", 1)),
            "per_page": int(pc_root.get("row_end", per_page)) - int(pc_root.get("row_start", 0)),
            "total": int(pc_root.get("total", 0)),
            "total_pages": int(pc_root.get("total_pages", 1))
        }

async def fetch_total_creations(
    session: aiohttp.ClientSession,
    name: str,
    base_url: str,
    player_creation_type: str,
    platform: str = "PS3",
) -> str:
    url = f"{base_url}player_creations.xml"
    params = {
        "page": 1,
        "per_page": 0,
        "player_creation_type": player_creation_type,
        "platform": platform,
    }
    debug(f"GET {name}: {url} params={params}")

    try:
        async with session.get(url, params=params) as resp:
            debug(f"{name} HTTP status: {resp.status}")

            if resp.status != 200:
                debug(f"{name} failed with HTTP {resp.status}")
                return "0"

            text = await resp.text()
            debug(f"{name} response length: {len(text)} chars")

    except Exception as e:
        debug(f"{name} request error: {repr(e)}")
        return "0"

    try:
        root = ET.fromstring(text)
        debug(f"{name} XML parsed successfully")
    except ET.ParseError as e:
        debug(f"{name} XML parse error: {e}")
        return "0"

    player_creations = root.find(".//player_creations")
    if player_creations is None:
        debug(f"{name} <player_creations> element not found")
        return "0"

    total = player_creations.get("total", "0")
    debug(f"{name} total parsed: {total}")
    return total


async def fetch_online_players(session: aiohttp.ClientSession, base_url: str) -> str:
    url = f"{base_url}api/playercounts/sessioncount"
    debug(f"GET Online Players: {url}")

    try:
        async with session.get(url) as resp:
            debug(f"Online players HTTP status: {resp.status}")
            text = (await resp.text()).strip()
            debug(f"Online players raw response: '{text}'")
    except Exception as e:
        debug(f"Online players request error: {repr(e)}")
        return "0"

    if text.isdigit():
        debug("Online players parsed as pure digit")
        return text

    match = re.search(r"(\d+)", text)
    if match:
        debug(f"Online players extracted via regex: {match.group(1)}")
        return match.group(1)

    debug("Online players could not be parsed, defaulting to 0")
    return "0"

def create_basic_embed(title: str, color: discord.Color) -> discord.Embed:
    return discord.Embed(title=title, color=color)


async def prepare_player_avatar_attachment(
    session: aiohttp.ClientSession,
    avatar_url: Optional[str],
    player_id: str,
    fallback_path: str = "img/secondary.png",
) -> tuple[discord.File, str, Optional[str]]:
    if avatar_url:
        try:
            async with session.get(avatar_url) as resp:
                if resp.status == 200:
                    avatar_bytes = await resp.read()
                    temp_path = os.path.join(
                        tempfile.gettempdir(),
                        f"skidplate_avatar_{player_id}_{int(datetime.now().timestamp() * 1000)}.png",
                    )
                    with open(temp_path, "wb") as f:
                        f.write(avatar_bytes)
                    return discord.File(temp_path, filename="avatar.png"), "attachment://avatar.png", temp_path
        except Exception as e:
            debug(f"Failed to prepare avatar attachment: {e}")

    return discord.File(fallback_path, filename="secondary.png"), "attachment://secondary.png", None


def cleanup_temp_file(path: Optional[str]):
    if not path:
        return

    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        debug(f"Failed to clean up temp file {path}: {e}")