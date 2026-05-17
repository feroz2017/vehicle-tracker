import time
from datetime import datetime
from config import DELAYED_THRESHOLD, STALE_THRESHOLD
from processing.models import Vehicle, TripUpdate, FreshnessStatus, FreshnessLevel


def filter_by_route(vehicles: list[Vehicle], route_id: str) -> list[Vehicle]:
    """Return only vehicles matching route_id."""
    return [v for v in vehicles if v.route_id == route_id]


def get_all_route_ids(vehicles: list[Vehicle]) -> list[str]:
    """Extract sorted unique route IDs from a list of vehicles."""
    return sorted({v.route_id for v in vehicles if v.route_id})


def enrich_with_updates(
    vehicles: list[Vehicle],
    trip_updates: list[TripUpdate],
    scheduled_arrivals: dict[str, int] | None = None,
) -> list[Vehicle]:
    """
    Cross-reference vehicle list with TripUpdates feed.
    Adds next stop, terminus arrival, stops remaining, and delay to each vehicle.

    scheduled_arrivals — optional dict {trip_id: scheduled_seconds_since_midnight}
    pre-loaded from Redis by the worker (one HGET per vehicle, pipelined).
    When provided, delay_seconds and is_delay_realtime are computed here.
    When None (tests, first boot before GTFS loaded) delay fields stay at defaults.
    """
    update_map: dict[str, TripUpdate] = {u.trip_id: u for u in trip_updates}

    for vehicle in vehicles:
        if not vehicle.trip_id or vehicle.trip_id not in update_map:
            continue

        tu = update_map[vehicle.trip_id]
        vehicle.next_stop_id      = tu.next_stop_id
        vehicle.next_stop_arrival = tu.next_stop_arrival
        vehicle.terminus_arrival  = tu.terminus_arrival
        vehicle.stops_remaining   = tu.stops_remaining

        # ── Delay computation ─────────────────────────────────────────────────
        # Requires static GTFS schedule (loaded by gtfs_loader.py).
        # predicted arrival (Unix timestamp) − scheduled arrival (seconds since midnight)
        if (
            scheduled_arrivals
            and vehicle.trip_id in scheduled_arrivals
            and vehicle.next_stop_arrival is not None
        ):
            sched_secs = scheduled_arrivals[vehicle.trip_id]
            pred_dt    = datetime.fromtimestamp(vehicle.next_stop_arrival)
            pred_secs  = pred_dt.hour * 3600 + pred_dt.minute * 60 + pred_dt.second
            vehicle.delay_seconds     = pred_secs - sched_secs
            vehicle.is_delay_realtime = True

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
