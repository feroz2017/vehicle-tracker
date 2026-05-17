import httpx
from config import DIGITRANSIT_API_KEY, DIGITRANSIT_BASE_URL


def _headers() -> dict:
    if not DIGITRANSIT_API_KEY:
        return {}
    return {"digitransit-subscription-key": DIGITRANSIT_API_KEY}


async def geocode(query: str) -> dict:
    """
    Search for a location by name using Digitransit geocoding API.

    Endpoint: GET /geocoding/v1/search
    Returns raw GeoJSON FeatureCollection — parsed by processing/geocoder.py
    Results are biased toward Jyväskylä city centre via focus.point params.
    """
    url = f"{DIGITRANSIT_BASE_URL}/geocoding/v1/search"
    params = {
        "text":             query,
        "lang":             "fi",
        "size":             5,
        # Bias results toward Jyväskylä city centre
        "focus.point.lat":  62.2416,
        "focus.point.lon":  25.7209,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=_headers(), params=params)
        response.raise_for_status()
        return response.json()


async def plan_route(
    from_lat: float,
    from_lon: float,
    to_lat:   float,
    to_lon:   float,
) -> dict:
    """
    Find routes between two coordinates using Digitransit routing API.

    Endpoint: POST /routing/v2/waltti/gtfs/v1  (Waltti-region routes — covers LINKKI)
    Returns raw GraphQL JSON — parsed by processing/route_planner.py
    """
    url = f"{DIGITRANSIT_BASE_URL}/routing/v2/waltti/gtfs/v1"

    # GraphQL query — returns up to 5 route options
    query = """
    {
      plan(
        from: { lat: %(from_lat)s, lon: %(from_lon)s }
        to:   { lat: %(to_lat)s,   lon: %(to_lon)s   }
        numItineraries: 5
      ) {
        itineraries {
          duration
          walkDistance
          legs {
            mode
            startTime
            endTime
            duration
            distance
            from { name }
            to   { name }
            route { gtfsId shortName }
            legGeometry { points }
          }
        }
      }
    }
    """ % {
        "from_lat": from_lat,
        "from_lon": from_lon,
        "to_lat":   to_lat,
        "to_lon":   to_lon,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            url,
            headers={**_headers(), "Content-Type": "application/json"},
            json={"query": query},
        )
        response.raise_for_status()
        return response.json()


async def fetch_trip_shape(trip_id: str) -> list:
    """
    Return the full road-snapped shape for a trip as [[lat, lon], ...].

    Digitransit stores shapes in pattern.geometry — these are the actual GPS
    coordinates the vehicle follows along the road network, not straight lines.
    trip_id is the raw GTFS trip_id (without the LINKKI: feed prefix); we add
    the prefix here when calling the GraphQL API.

    Returns [] if the trip is unknown or the API fails.
    """
    url   = f"{DIGITRANSIT_BASE_URL}/routing/v2/waltti/gtfs/v1"
    query = """
    {
      trip(id: "LINKKI:%s") {
        pattern {
          geometry { lat lon }
        }
      }
    }
    """ % trip_id

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            url,
            headers={**_headers(), "Content-Type": "application/json"},
            json={"query": query},
        )
        response.raise_for_status()
        data = response.json()

    trip = (data.get("data") or {}).get("trip")
    if not trip:
        return []

    geometry = (trip.get("pattern") or {}).get("geometry") or []
    return [[p["lat"], p["lon"]] for p in geometry if p.get("lat") is not None]
