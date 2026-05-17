from processing.models import Route, RouteLeg, Location, PlanResult
from datetime import datetime


def _decode_polyline(encoded: str) -> list[list[float]]:
    """
    Decode Google's encoded polyline format into [[lat, lon], ...] pairs.
    Digitransit returns leg geometry in this format via legGeometry.points.
    """
    coords = []
    index  = 0
    lat = lng = 0

    while index < len(encoded):
        for is_lng in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift  += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
            else:
                lat += delta
        coords.append([lat / 1e5, lng / 1e5])

    return coords


def parse_plan_response(raw: dict, from_loc: Location, to_loc: Location) -> PlanResult:
    """
    Convert Digitransit route planning GraphQL response into a PlanResult.

    Endpoint: POST /routing/v2/waltti/gtfs/v1
    Each itinerary has legs with: mode, route { gtfsId shortName },
    from/to { name }, startTime/endTime (ms epoch), duration, distance,
    and legGeometry { points } (Google encoded polyline — decoded here).
    """
    routes: list[Route] = []

    itineraries = raw.get("data", {}).get("plan", {}).get("itineraries", [])

    for itin in itineraries:
        legs_raw = itin.get("legs", [])
        legs: list[RouteLeg] = []

        for leg in legs_raw:
            route_info = leg.get("route") or {}  # walk legs have no route field
            start_ms = leg.get("startTime", 0)
            end_ms   = leg.get("endTime", 0)

            encoded = (leg.get("legGeometry") or {}).get("points", "")
            geometry = _decode_polyline(encoded) if encoded else []

            legs.append(RouteLeg(
                mode=leg.get("mode", "WALK"),
                route_id=route_info.get("gtfsId"),
                route_name=route_info.get("shortName"),
                from_name=leg.get("from", {}).get("name", ""),
                to_name=leg.get("to", {}).get("name", ""),
                departure_time=_ms_to_time(start_ms),
                arrival_time=_ms_to_time(end_ms),
                duration_minutes=int(leg.get("duration", 0) / 60),
                distance_meters=leg.get("distance", 0.0),
                geometry=geometry,
            ))

        if not legs:
            continue

        # Use the first transit leg for the route identity
        transit_legs = [l for l in legs if l.mode != "WALK"]
        main_leg     = transit_legs[0] if transit_legs else legs[0]

        # Strip feed prefix from gtfsId (e.g. "LINKKI:903" → "903")
        # so the route_id matches the raw route_id in the GTFS-RT vehicle feed
        # and the WebSocket can find the right Redis key.
        raw_id   = main_leg.route_id or ""
        route_id = raw_id.split(":")[-1] if ":" in raw_id else (raw_id or "WALK")

        routes.append(Route(
            route_id=route_id,
            route_name=main_leg.route_name or "Walk",
            departure_time=legs[0].departure_time,
            arrival_time=legs[-1].arrival_time,
            duration_minutes=int(itin.get("duration", 0) / 60),
            walk_distance_meters=itin.get("walkDistance", 0.0),
            legs=legs,
        ))

    return PlanResult(routes=routes, from_location=from_loc, to_location=to_loc)


def _ms_to_time(ms: int) -> str:
    """Convert millisecond epoch to HH:MM string."""
    if not ms:
        return "--:--"
    return datetime.fromtimestamp(ms / 1000).strftime("%H:%M")
