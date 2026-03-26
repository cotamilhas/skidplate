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
        logs_dir: str,
        user_tokens: Dict[int, str]
    ):
        self.session = session
        self.api_base = api_base
        self.logs_dir = logs_dir
        self.user_tokens = user_tokens

    def save_api_response(self, endpoint: str, method: str, response_data, status_code: int, error: Optional[str] = None):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{self.logs_dir}/api_{timestamp}_{method}_{endpoint.replace('/', '_')}.json"

            log_data = {
                "timestamp": datetime.now().isoformat(),
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "response": response_data if not error else None,
                "error": error if error else None,
                "url": f"{self.api_base}api/moderation{endpoint}"
            }

            if isinstance(response_data, str) and not error:
                try:
                    log_data["response_parsed"] = json.loads(response_data)
                except json.JSONDecodeError:
                    log_data["response_raw"] = response_data
            elif isinstance(response_data, (dict, list)):
                log_data["response"] = response_data

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            debug(f"API response saved to: {filename}")
        except Exception as e:
            debug(f"Failed to save API response log: {str(e)}")

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
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, "Unauthorized. Please log in first.")
                    return None, "Unauthorized. Please log in first."
                if resp.status == 403:
                    debug("Permission denied (403)")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, "Permission denied. You do not have access to this action.")
                    return None, "Permission denied. You do not have access to this action."
                if resp.status == 404:
                    debug("Resource not found (404)")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, "Resource not found.")
                    return None, "Resource not found."
                if resp.status >= 400:
                    debug(f"Error response: {resp.status}")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, None, resp.status, f"Error {resp.status}")
                    return None, f"Error {resp.status}"

                text = await resp.text()
                debug(f"Raw response text: {text[:200]}")

                try:
                    data = json.loads(text)
                    debug(f"Successfully parsed JSON response: {type(data)}")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, data, resp.status)
                    return data, None
                except json.JSONDecodeError:
                    debug("JSON parsing failed, returning as text")
                    if DEBUG_MODE:
                        self.save_api_response(endpoint, method, text, resp.status)
                    return text, None
        except Exception as e:
            debug(f"API Request exception: {str(e)}")
            if DEBUG_MODE:
                self.save_api_response(endpoint, method, None, 0, f"Connection error: {str(e)}")
            return None, f"Connection error: {str(e)}"
