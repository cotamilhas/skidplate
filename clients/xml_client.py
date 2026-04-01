import aiohttp
import xml.etree.ElementTree as ET
from typing import Optional, Mapping, Any
from config import DEBUG_MODE


def debug(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")


class XMLFetcher:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch_xml(self, url: str, params: Optional[Mapping[str, Any]] = None) -> Optional[ET.Element]:
        debug(f"GET XML: {url} params={params}")
        try:
            async with self.session.get(url, params=params) as resp:
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
