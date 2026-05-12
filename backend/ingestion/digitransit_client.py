import httpx
from config import DIGITRANSIT_API_KEY, DIGITRANSIT_BASE_URL


def _headers() -> dict:
    """
    TODO: confirm header name with team.
    Digitransit typically uses 'digitransit-subscription-key'.
    """
    if not DIGITRANSIT_API_KEY:
        return {}
    return {"digitransit-subscription-key": DIGITRANSIT_API_KEY}


async def geocode(query: str) -> dict:
    """
    Search for a location by name using Digitransit geocoding API.

    Endpoint: GET /geocoding/v1/search
    Returns raw GeoJSON FeatureCollection — parsed by processing/geocoder.py

    TODO: add &focus.point.lat=62.24&focus.point.lon=25.72 to bias results
          towards Jyväskylä when API key is available.
    """
    url = f"{DIGITRANSIT_BASE_URL}/geocoding/v1/search"
    params = {
        "text":  query,
        "lang":  "fi",
        "size":  5,   # max results
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

    Endpoint: POST /routing/v2/routers/finland/index/graphql
    Returns raw GraphQL JSON — parsed by processing/route_planner.py

    TODO: adjust numItineraries, transportModes, and date/time once API key confirmed.
    """
    url = f"{DIGITRANSIT_BASE_URL}/routing/v2/routers/finland/index/graphql"

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
