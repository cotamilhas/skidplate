import discord
import aiohttp
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import os
from typing import Optional, List, Dict, Any, Union

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

class XMLFetcher:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_xml(self, url: str) -> Optional[ET.Element]:
        debug(f"GET XML: {url}")
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    debug(f"HTTP {resp.status} while fetching XML")
                    return None
                text = await resp.text()
        except Exception as e:
            debug(f"Request error: {e}")
            return None

        try:
            return ET.fromstring(text)
        except ET.ParseError as e:
            debug(f"XML parse error: {e}")
            return None

    async def fetch_bytes(self, url: str) -> Optional[bytes]:
        debug(f"GET BYTES: {url}")
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    debug(f"HTTP {resp.status} while fetching bytes")
                    return None
                return await resp.read()
        except Exception as e:
            debug(f"Error loading bytes: {e}")
            return None

class PlayerDataFetcher:    
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self.session = session
        self.base_url = base_url
        self.xml_fetcher = XMLFetcher(session)

    async def get_player_id(self, username: str) -> Optional[str]:
        url = f"{self.base_url}players/to_id.xml?username={username}"
        root = await self.xml_fetcher.fetch_xml(url)
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
        url = (
            f"{self.base_url}player_creations.xml"
            f"?page={page}&per_page={per_page}"
            f"&sort_column={sort_column}"
            f"&player_creation_type={player_creation_type}"
            f"&platform={platform}&sort_order={sort_order}"
        )

        root = await self.xml_fetcher.fetch_xml(url)
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

async def fetch_total_creations(session: aiohttp.ClientSession, name: str, url: str) -> str:
    debug(f"GET {name}: {url}")

    try:
        async with session.get(url) as resp:
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

def add_player_fields_to_embed(embed: discord.Embed, info: Dict[str, str], show_win_rate: bool, full_emoji: str, half_emoji: str, empty_emoji: str):
    rating_stars = rating_to_stars(info.get("star_rating", "0"), full_emoji, half_emoji, empty_emoji)
    
    online_races = int(info.get("online_finished", "0")) + int(info.get("online_forfeit", "0")) + int(info.get("online_disconnected", "0"))
    online_wins = int(info.get("online_wins", "0"))
    win_rate = (online_wins / online_races) * 100 if online_races > 0 else 0
    
    embed.add_field(name="Rating", value=rating_stars, inline=False)
    
    embed.add_field(name="Online Races", value=online_races, inline=True)
    embed.add_field(name="Online Wins", value=online_wins, inline=True)
    
    if show_win_rate:
        embed.add_field(name="Win Rate", value=f"{win_rate:.2f}%", inline=False)
        
    embed.add_field(name="Longest Drift", value=info.get("longest_drift", "0"), inline=True)
    embed.add_field(name="Longest Air Time", value=info.get("longest_hang_time", "0"), inline=True)
    embed.add_field(name="Longest Win Streak", value=info.get("longest_win_streak", "0"), inline=True)

    presence = presence_lookup(info.get("presence", "OFFLINE"))
    embed.add_field(name="Presence", value=presence, inline=False)

    if info.get("created_at"):
        embed.add_field(name="Created At", value=to_discord_timestamp(info["created_at"]), inline=False)