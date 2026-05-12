import httpx
from config import WALTTI_API_KEY, WALTTI_BASE_URL


def _headers() -> dict:
    """
    Build auth headers for Waltti API.
    TODO: confirm exact header name with team once API key is received.
    """
    if not WALTTI_API_KEY:
        return {}
    return {"x-api-key": WALTTI_API_KEY}


async def fetch_vehicle_positions() -> bytes:
    """
    Fetch live vehicle positions from Waltti GTFS-RT feed.
    Returns raw protobuf bytes — decoded by gtfs_parser.py.

    Feed URL: {WALTTI_BASE_URL}/gtfs-rt/vehicle-positions
    TODO: confirm exact URL path from opendata.waltti.fi/docs
    """
    url = f"{WALTTI_BASE_URL}/gtfs-rt/vehicle-positions"

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=_headers())
        response.raise_for_status()
        return response.content


async def fetch_trip_updates() -> bytes:
    """
    Fetch trip updates (delays per stop) from Waltti GTFS-RT feed.
    Returns raw protobuf bytes — decoded by gtfs_parser.py.

    Feed URL: {WALTTI_BASE_URL}/gtfs-rt/trip-updates
    TODO: confirm exact URL path from opendata.waltti.fi/docs
    """
    url = f"{WALTTI_BASE_URL}/gtfs-rt/trip-updates"

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=_headers())
        response.raise_for_status()
        return response.content


async def fetch_alerts() -> bytes:
    """
    Fetch service alerts from Waltti GTFS-RT feed.
    Returns raw protobuf bytes — decoded by gtfs_parser.py.

    Feed URL: {WALTTI_BASE_URL}/gtfs-rt/alerts
    TODO: confirm exact URL path from opendata.waltti.fi/docs
    """
    url = f"{WALTTI_BASE_URL}/gtfs-rt/alerts"

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=_headers())
        response.raise_for_status()
        return response.content
