import hashlib
import secrets

import httpx

APP_NAME = "media-library-manager"
API_VERSION = "1.16.1"


class NavidromeError(Exception):
    pass


def _auth_params(username: str, password: str) -> dict:
    salt = secrets.token_hex(6)
    token = hashlib.md5((password + salt).encode("utf-8")).hexdigest()
    return {
        "u": username,
        "t": token,
        "s": salt,
        "v": API_VERSION,
        "c": APP_NAME,
        "f": "json",
    }


async def _request(base_url: str, username: str, password: str, endpoint: str, extra: dict | None = None) -> dict:
    if not base_url:
        raise NavidromeError("Navidrome URL is not configured")
    url = f"{base_url.rstrip('/')}/rest/{endpoint}.view"
    params = _auth_params(username, password)
    if extra:
        params.update(extra)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise NavidromeError(f"Could not reach Navidrome: {exc}") from exc

    root = data.get("subsonic-response", {})
    if root.get("status") != "ok":
        err = root.get("error", {})
        raise NavidromeError(err.get("message", "Unknown Navidrome error"))
    return root


async def ping(base_url: str, username: str, password: str) -> dict:
    root = await _request(base_url, username, password, "ping")
    return {"ok": True, "server_version": root.get("version")}


async def start_scan(base_url: str, username: str, password: str) -> dict:
    root = await _request(base_url, username, password, "startScan")
    status = root.get("scanStatus", {})
    return {"scanning": status.get("scanning", True), "count": status.get("count")}


async def scan_status(base_url: str, username: str, password: str) -> dict:
    root = await _request(base_url, username, password, "getScanStatus")
    status = root.get("scanStatus", {})
    return {"scanning": status.get("scanning", False), "count": status.get("count")}
