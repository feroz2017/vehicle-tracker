import httpx
from config import WALTTI_ID, WALTTI_SECRET, WALTTI_BASE_URL


def _auth() -> tuple[str, str] | None:
    """
    Waltti uses HTTP Basic Auth: (id, secret).
    Returns None if credentials are not set — caller falls back to dummy data.
    """
    if WALTTI_ID and WALTTI_SECRET:
        return (WALTTI_ID, WALTTI_SECRET)
    return None


async def fetch_vehicle_positions() -> bytes:
    """
    Fetch live vehicle positions from Waltti GTFS-RT feed.
    Returns raw protobuf bytes — decoded by gtfs_parser.py.

    Confirmed URL: {WALTTI_BASE_URL}/vehicleposition
    Auth: HTTP Basic (WALTTI_ID:WALTTI_SECRET)
    """
    auth = _auth()
    if not auth:
        return b""   # dummy mode — worker will use cached dummy data

    url = f"{WALTTI_BASE_URL}/vehicleposition"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
        return response.content


async def fetch_trip_updates() -> bytes:
    """
    Fetch trip updates (delays per stop) from Waltti GTFS-RT feed.
    Returns raw protobuf bytes — decoded by gtfs_parser.py.

    Confirmed URL: {WALTTI_BASE_URL}/tripupdate
    Auth: HTTP Basic (WALTTI_ID:WALTTI_SECRET)
    """
    auth = _auth()
    if not auth:
        return b""

    url = f"{WALTTI_BASE_URL}/tripupdate"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
        return response.content


async def fetch_alerts() -> bytes:
    """
    Fetch service alerts from Waltti GTFS-RT feed.
    Returns raw protobuf bytes — decoded by gtfs_parser.py.

    Confirmed URL: {WALTTI_BASE_URL}/servicealert
    Auth: HTTP Basic (WALTTI_ID:WALTTI_SECRET)
    """
    auth = _auth()
    if not auth:
        return b""

    url = f"{WALTTI_BASE_URL}/servicealert"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, auth=auth)
        response.raise_for_status()
        return response.content
