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
from processing.models       import Vehicle, TripDelay
from processing              import vehicle_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
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


def _raw_to_delays(raw: list[dict]) -> list[TripDelay]:
    """Convert raw dicts from gtfs_parser into TripDelay domain objects."""
    delays = []
    for d in raw:
        trip_id = d.get("trip_id")
        if not trip_id:
            continue
        delays.append(TripDelay(
            trip_id=trip_id,
            delay_seconds=d.get("delay_seconds", 0),
            is_realtime=d.get("is_realtime", True),
        ))
    return delays


async def run_cycle(redis) -> None:
    """
    One full fetch cycle:
      1. Fetch all 3 Waltti GTFS-RT feeds concurrently
      2. Parse each feed
      3. Convert raw dicts → domain objects, enrich vehicles with delays
      4. Write enriched data to Redis and publish Pub/Sub event

    Each step is wrapped in try/except — a failure in one feed
    does not stop the others.
    """
    fetched_at = time.time()
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
    raw_vehicles, raw_delays, raw_alerts = [], [], []

    try:
        raw_vehicles = parse_vehicle_positions(positions_bytes)
        logger.info("Parsed %d vehicles", len(raw_vehicles))
    except Exception as exc:
        logger.error("Failed to parse vehicle positions: %s", exc)

    try:
        raw_delays = parse_trip_updates(updates_bytes)
        logger.info("Parsed %d trip delays", len(raw_delays))
    except Exception as exc:
        logger.error("Failed to parse trip updates: %s", exc)

    try:
        raw_alerts = parse_alerts(alerts_bytes)
        logger.info("Parsed %d alerts", len(raw_alerts))
    except Exception as exc:
        logger.error("Failed to parse alerts: %s", exc)

    # ── 3. Convert + enrich ───────────────────────────────────────────────────
    vehicles = _raw_to_vehicles(raw_vehicles)
    delays   = _raw_to_delays(raw_delays)
    enriched = vehicle_service.enrich_with_delays(vehicles, delays)
    logger.info("Enriched %d vehicles with delay data", len(enriched))

    # ── 4. Write to Redis ─────────────────────────────────────────────────────
    try:
        await write_vehicles(redis, enriched, fetched_at)
        await write_alerts(redis, raw_alerts)
    except Exception as exc:
        logger.error("Failed to write to Redis: %s", exc)


async def main() -> None:
    """Main worker loop — runs forever until interrupted."""
    logger.info("Worker starting. Interval: %ds", WORKER_INTERVAL)

    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)

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
