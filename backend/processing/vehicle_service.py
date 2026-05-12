import time
from config import DELAYED_THRESHOLD, STALE_THRESHOLD
from processing.models import Vehicle, TripDelay, FreshnessStatus, FreshnessLevel


def filter_by_route(vehicles: list[Vehicle], route_id: str) -> list[Vehicle]:
    """Return only vehicles matching route_id."""
    return [v for v in vehicles if v.route_id == route_id]


def get_all_route_ids(vehicles: list[Vehicle]) -> list[str]:
    """Extract sorted unique route IDs from a list of vehicles."""
    return sorted({v.route_id for v in vehicles if v.route_id})


def enrich_with_delays(
    vehicles: list[Vehicle],
    trip_delays: list[TripDelay],
) -> list[Vehicle]:
    """
    Cross-reference vehicle list with TripUpdates feed.
    Adds delay_seconds and is_delay_realtime to each vehicle.

    If no TripUpdate exists for a vehicle, delay stays 0 and is_delay_realtime = False.
    """
    # Build lookup: trip_id → TripDelay
    delay_map: dict[str, TripDelay] = {d.trip_id: d for d in trip_delays}

    for vehicle in vehicles:
        if vehicle.trip_id and vehicle.trip_id in delay_map:
            td = delay_map[vehicle.trip_id]
            vehicle.delay_seconds     = td.delay_seconds
            vehicle.is_delay_realtime = td.is_realtime
        # else: no update found — leave delay_seconds=0, is_delay_realtime=False

    return vehicles


def compute_freshness(fetched_at: float) -> FreshnessStatus:
    """
    Compute freshness level based on how old the cached data is.

    LIVE    → age < DELAYED_THRESHOLD (60s)
    DELAYED → DELAYED_THRESHOLD ≤ age < STALE_THRESHOLD (120s)
    STALE   → age ≥ STALE_THRESHOLD
    """
    age = int(time.time() - fetched_at) if fetched_at else 9999

    if age < DELAYED_THRESHOLD:
        return FreshnessStatus(
            level=FreshnessLevel.LIVE,
            age_seconds=age,
            label=f"Live · updated {age}s ago",
        )
    elif age < STALE_THRESHOLD:
        return FreshnessStatus(
            level=FreshnessLevel.DELAYED,
            age_seconds=age,
            label=f"Updated {age}s ago",
        )
    else:
        mins = age // 60
        return FreshnessStatus(
            level=FreshnessLevel.STALE,
            age_seconds=age,
            label=f"Stale · last updated {mins}m ago",
        )
