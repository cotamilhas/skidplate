import aiohttp
import json
from typing import Dict
from config import DEBUG_MODE


def debug(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")


class ModerationAPIHelper:
    ERROR_LOGIN_REQUIRED = "You are not authorized to perform this action."
    ERROR_FORBIDDEN = "You do not have permission for this action."
    ERROR_NOT_FOUND = "Requested item was not found."
    ERROR_REQUEST_FAILED = "Moderation API request failed. Please try again."
    ERROR_CONNECTION = "Could not reach Moderation API. Please try again."
    ERROR_USERNAME_TAKEN = "That moderator username is already taken."
    ERROR_CANNOT_REMOVE_SELF = "You cannot delete your own moderator account."

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

    def _map_plain_text_error(self, raw_text: str) -> str:
        text = raw_text.strip().lower()
        if text == "error_username_is_taken":
            return self.ERROR_USERNAME_TAKEN
        if text == "error_cannot_remove_yourself":
            return self.ERROR_CANNOT_REMOVE_SELF
        if text.startswith("error"):
            return self.ERROR_REQUEST_FAILED
        return self.ERROR_REQUEST_FAILED

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
                    return None, self.ERROR_LOGIN_REQUIRED
                
                if resp.status == 403:
                    debug("Permission denied (403)")
                    return None, self.ERROR_FORBIDDEN
                
                if resp.status == 404:
                    debug("Resource not found (404)")
                    return None, self.ERROR_NOT_FOUND
                
                if resp.status >= 400:
                    debug(f"Error response: {resp.status}")
                    return None, self.ERROR_REQUEST_FAILED

                text = await resp.text()
                debug(f"Raw response text: {text[:200]}")

                try:
                    data = json.loads(text)
                    debug(f"Successfully parsed JSON response: {type(data)}")

                    return data, None
                except json.JSONDecodeError:
                    debug("JSON parsing failed, handling as plain text")

                    stripped = text.strip()
                    if stripped.lower().startswith("error"):
                        return None, self._map_plain_text_error(stripped)

                    return stripped, None
        except Exception as e:
            debug(f"API Request exception: {str(e)}")
            return None, self.ERROR_CONNECTION
