import aiohttp
import json
from datetime import datetime
from typing import Dict, Optional
from config import DEBUG_MODE


def debug(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")


class ModerationAPIHelper:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_base: str,
        user_tokens: Dict[int, str]
    ):
        self.session = session
        self.api_base = api_base
        self.user_tokens = user_tokens


    async def get_auth_headers(self, user_id: int) -> dict:
        token = self.user_tokens.get(user_id)
        if not token:
            debug(f"No moderator token available for user {user_id}")
            return {}
        debug(f"Auth headers prepared for user {user_id} with token: {token[:10]}...")
        return {"Authorization": f"Bearer {token}"}

    async def api_request(self, method: str, endpoint: str, user_id: int, **kwargs):
        url = f"{self.api_base}api/moderation{endpoint}"
        headers = await self.get_auth_headers(user_id)

        debug(f"API Request: {method} {url} by user {user_id}")

        try:
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                debug(f"API Response Status: {resp.status}")
                debug(f"Response Content-Type: {resp.content_type}")

                if resp.status == 401:
                    debug("Unauthorized (401)")
                    return None, "Unauthorized. Please log in first."
                
                if resp.status == 403:
                    debug("Permission denied (403)")
                    return None, "Permission denied. You do not have access to this action."
                
                if resp.status == 404:
                    debug("Resource not found (404)")
                    return None, "Resource not found."
                
                if resp.status >= 400:
                    debug(f"Error response: {resp.status}")
                    return None, f"Error {resp.status}"

                text = await resp.text()
                debug(f"Raw response text: {text[:200]}")

                try:
                    data = json.loads(text)
                    debug(f"Successfully parsed JSON response: {type(data)}")

                    return data, None
                except json.JSONDecodeError:
                    debug("JSON parsing failed, returning as text")
                    
                    return text, None
        except Exception as e:
            debug(f"API Request exception: {str(e)}")
            return None, f"Connection error: {str(e)}"
