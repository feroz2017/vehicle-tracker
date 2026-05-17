"""
Background worker — runs as a separate process.
Polls Waltti GTFS-RT every 30s and writes results to Redis.

Run:
    cd backend
    python -m ingestion.worker
"""
import asyncio
import logging
import time
import redis.asyncio as aioredis

from config import REDIS_URL, WORKER_INTERVAL
from ingestion.waltti_client import fetch_vehicle_positions, fetch_trip_updates, fetch_alerts
from ingestion.gtfs_parser   import parse_vehicle_positions, parse_trip_updates, parse_alerts
from ingestion.cache_writer  import write_vehicles, write_alerts
from ingestion               import gtfs_loader
from processing.models       import Vehicle, TripUpdate
from processing              import vehicle_service

from app.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)


def _raw_to_vehicles(raw: list[dict]) -> list[Vehicle]:
    """Convert raw dicts from gtfs_parser into Vehicle domain objects."""
    vehicles = []
    for v in raw:
        try:
            vehicles.append(Vehicle(
                id=v["id"],
                label=v.get("label") or v["id"],
                route_id=v.get("route_id") or "",
                lat=v["lat"],
                lon=v["lon"],
                bearing=v.get("bearing"),
                speed_kmh=v.get("speed_kmh"),
                trip_id=v.get("trip_id"),
                timestamp=v.get("timestamp"),
            ))
        except (KeyError, TypeError) as exc:
            logger.warning("Skipping malformed vehicle dict: %s", exc)
    return vehicles


def _raw_to_updates(raw: list[dict]) -> list[TripUpdate]:
    """Convert raw dicts from gtfs_parser into TripUpdate domain objects."""
    updates = []
    for d in raw:
        trip_id = d.get("trip_id")
        if not trip_id:
            continue
        updates.append(TripUpdate(
            trip_id=trip_id,
            next_stop_id=d.get("next_stop_id"),
            next_stop_arrival=d.get("next_stop_arrival"),
            terminus_arrival=d.get("terminus_arrival"),
            stops_remaining=d.get("stops_remaining", 0),
        ))
    return updates


async def _load_scheduled_arrivals(redis, updates: list[TripUpdate]) -> dict[str, int]:
    """
    For each TripUpdate that has a next_stop_id, fetch the scheduled arrival
    time (seconds since midnight) from the static GTFS Redis hash.

    All lookups are pipelined — one Redis round trip regardless of how many
    vehicles are active.

    Returns {trip_id: scheduled_seconds_since_midnight}.
    Empty dict if no schedule data is loaded yet (first boot or Redis flushed).
    """
    # Only look up trips that have a next stop to compare against
    lookups = [(u.trip_id, u.next_stop_id) for u in updates if u.trip_id and u.next_stop_id]
    if not lookups:
        return {}

    try:
        pipe = redis.pipeline()
        for trip_id, stop_id in lookups:
            pipe.hget(f"schedule:{trip_id}", stop_id)
        results = await pipe.execute()
    except Exception as exc:
        logger.warning("Failed to load scheduled arrivals: %s", exc)
        return {}

    scheduled: dict[str, int] = {}
    for (trip_id, _), val in zip(lookups, results):
        if val is not None:
            scheduled[trip_id] = int(val)

    return scheduled


async def run_cycle(redis) -> None:
    """
    One full fetch cycle:
      1. Fetch all 3 Waltti GTFS-RT feeds concurrently
      2. Parse each feed
      3. Convert raw dicts → domain objects, enrich vehicles with delays
      4. Write enriched data to Redis and publish Pub/Sub event
      5. Write telemetry counters (for /api/stats)

    Each step is wrapped in try/except — a failure in one feed
    does not stop the others.
    """
    cycle_start = time.monotonic()   # wall-clock start for duration tracking
    fetched_at  = time.time()
    logger.info("Fetching all Waltti feeds...")

    # ── 1. Fetch concurrently ─────────────────────────────────────────────────
    positions_bytes, updates_bytes, alerts_bytes = await asyncio.gather(
        fetch_vehicle_positions(),
        fetch_trip_updates(),
        fetch_alerts(),
        return_exceptions=True,   # one feed failure does not kill the others
    )

    # Log any fetch-level exceptions (waltti_client already returns b"" on no creds)
    for name, result in [("positions", positions_bytes), ("updates", updates_bytes), ("alerts", alerts_bytes)]:
        if isinstance(result, Exception):
            logger.error("Failed to fetch %s: %s", name, result)

    positions_bytes = positions_bytes if isinstance(positions_bytes, bytes) else b""
    updates_bytes   = updates_bytes   if isinstance(updates_bytes,   bytes) else b""
    alerts_bytes    = alerts_bytes    if isinstance(alerts_bytes,    bytes) else b""

    # ── 2. Parse ──────────────────────────────────────────────────────────────
    raw_vehicles, raw_trip_updates, raw_alerts = [], [], []

    try:
        raw_vehicles = parse_vehicle_positions(positions_bytes)
        logger.info("Parsed %d vehicles", len(raw_vehicles))
    except Exception as exc:
        logger.error("Failed to parse vehicle positions: %s", exc)

    try:
        raw_trip_updates = parse_trip_updates(updates_bytes)
        logger.info("Parsed %d trip updates", len(raw_trip_updates))
    except Exception as exc:
        logger.error("Failed to parse trip updates: %s", exc)

    try:
        raw_alerts = parse_alerts(alerts_bytes)
        logger.info("Parsed %d alerts", len(raw_alerts))
    except Exception as exc:
        logger.error("Failed to parse alerts: %s", exc)

    # ── 3. Convert + enrich ───────────────────────────────────────────────────
    vehicles = _raw_to_vehicles(raw_vehicles)
    updates  = _raw_to_updates(raw_trip_updates)

    # Load scheduled arrival times for each vehicle's next stop from Redis.
    # One HGET per vehicle — pipelined into a single round trip.
    scheduled = await _load_scheduled_arrivals(redis, updates)

    enriched = vehicle_service.enrich_with_updates(vehicles, updates, scheduled)
    logger.info(
        "Enriched %d vehicles — %d with real delay data",
        len(enriched),
        sum(1 for v in enriched if v.is_delay_realtime),
    )

    # ── 4. Write to Redis ─────────────────────────────────────────────────────
    try:
        await write_vehicles(redis, enriched, fetched_at)
        await write_alerts(redis, raw_alerts)
    except Exception as exc:
        logger.error("Failed to write to Redis: %s", exc)

    # ── 5. Telemetry counters (best-effort — never blocks the cycle) ──────────
    # These feed /api/stats so the system can answer "what has it been doing?"
    cycle_ms = round((time.monotonic() - cycle_start) * 1000)
    try:
        pipe = redis.pipeline()
        pipe.incr("stats:fetch_count")                      # total cycles ever
        pipe.set("stats:last_cycle_ms",    cycle_ms)        # last cycle wall-time
        pipe.set("stats:total_vehicles",   len(enriched))   # snapshot vehicle count
        await pipe.execute()
    except Exception:
        pass  # stats are observability data — a Redis blip must not crash the cycle

    logger.info(
        "cycle_complete",
        extra={
            "vehicle_count":    len(enriched),
            "realtime_delay":   sum(1 for v in enriched if v.is_delay_realtime),
            "duration_ms":      cycle_ms,
        },
    )


async def main() -> None:
    """Main worker loop — runs forever until interrupted."""
    logger.info("Worker starting. Interval: %ds", WORKER_INTERVAL)

    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)

    # Load static GTFS schedule before first cycle so delay data is available
    # immediately. Skipped if already loaded today (gtfs-loader service ran first).
    logger.info("Checking static GTFS schedule...")
    await gtfs_loader.load_if_needed(redis)

    backoff = WORKER_INTERVAL

    while True:
        start = time.monotonic()
        try:
            await run_cycle(redis)
            backoff = WORKER_INTERVAL   # reset on success
        except Exception as exc:
            logger.error("Unexpected error in cycle: %s", exc)
            backoff = min(backoff * 2, 300)   # exponential backoff, max 5 min
            logger.info("Backing off for %ds", backoff)

        elapsed = time.monotonic() - start
        sleep   = max(0, backoff - elapsed)
        logger.info("Cycle done in %.1fs, sleeping %.1fs", elapsed, sleep)
        await asyncio.sleep(sleep)


if __name__ == "__main__":
    asyncio.run(main())
