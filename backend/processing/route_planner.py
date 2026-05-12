from processing.models import Route, RouteLeg, Location, PlanResult
from datetime import datetime


def parse_plan_response(raw: dict, from_loc: Location, to_loc: Location) -> PlanResult:
    """
    Convert Digitransit route planning GraphQL response into a PlanResult.

    TODO: implement once Digitransit API key is confirmed.
    Digitransit returns itineraries from:
        POST https://api.digitransit.fi/routing/v2/routers/finland/index/graphql

    GraphQL query returns itineraries → each has legs → each leg has:
        mode, route { shortName }, from { name }, to { name },
        startTime (ms epoch), endTime (ms epoch), duration, distance
    """
    routes: list[Route] = []

    itineraries = raw.get("data", {}).get("plan", {}).get("itineraries", [])

    for itin in itineraries:
        legs_raw = itin.get("legs", [])
        legs: list[RouteLeg] = []

        for leg in legs_raw:
            # TODO: null-check every field — Digitransit can omit route info for walk legs
            route_info = leg.get("route") or {}
            start_ms = leg.get("startTime", 0)
            end_ms   = leg.get("endTime", 0)

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
            ))

        if not legs:
            continue

        # Use the first transit leg for the route identity
        transit_legs = [l for l in legs if l.mode != "WALK"]
        main_leg     = transit_legs[0] if transit_legs else legs[0]

        routes.append(Route(
            route_id=main_leg.route_id or "WALK",
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
