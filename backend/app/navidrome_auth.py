import httpx


class NavidromeAuthError(Exception):
    pass


async def login(base_url: str, username: str, password: str) -> dict:
    """POSTs to Navidrome's native /auth/login (not the Subsonic API) and
    returns the decoded JSON on success — includes id, isAdmin, name,
    username, token, subsonicSalt, subsonicToken."""
    if not base_url:
        raise NavidromeAuthError("NAVIDROME_URL is not configured on the server")

    url = f"{base_url.rstrip('/')}/auth/login"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={"username": username, "password": password})
    except httpx.RequestError as exc:
        raise NavidromeAuthError(f"Could not reach Navidrome at {base_url}: {exc}")

    if r.status_code == 401:
        raise NavidromeAuthError("Invalid username or password")
    if r.status_code == 404:
        raise NavidromeAuthError("Navidrome login endpoint not found — check NAVIDROME_URL")
    if r.status_code != 200:
        raise NavidromeAuthError(f"Navidrome returned HTTP {r.status_code}")

    try:
        return r.json()
    except ValueError:
        raise NavidromeAuthError("Unexpected response from Navidrome")
