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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
logger = logging.getLogger(__name__)


async def run_cycle(redis) -> None:
    """
    One full fetch cycle:
      1. Fetch all 3 Waltti GTFS-RT feeds concurrently
      2. Parse each feed
      3. Write to Redis
      4. Publish Pub/Sub event

    Each step is wrapped in try/except — a failure in one feed
    does not stop the others.
    """
    # ── 1. Fetch all feeds concurrently ──────────────────────────────────────
    logger.info("Fetching all Waltti feeds...")

    # TODO: uncomment when API key is ready
    # positions_bytes, updates_bytes, alerts_bytes = await asyncio.gather(
    #     fetch_vehicle_positions(),
    #     fetch_trip_updates(),
    #     fetch_alerts(),
    #     return_exceptions=True,   # don't let one failure kill the others
    # )

    # ── DUMMY MODE ── remove once real feeds are connected ───────────────────
    positions_bytes = b""   # placeholder
    updates_bytes   = b""   # placeholder
    alerts_bytes    = b""   # placeholder
    logger.info("DUMMY MODE: no real fetch, using empty bytes")
    # ────────────────────────────────────────────────────────────────────────

    # ── 2. Parse ─────────────────────────────────────────────────────────────
    vehicles = []
    try:
        vehicles = parse_vehicle_positions(positions_bytes)
        logger.info("Parsed %d vehicles", len(vehicles))
    except Exception as exc:
        logger.error("Failed to parse vehicle positions: %s", exc)

    trip_delays = []
    try:
        trip_delays = parse_trip_updates(updates_bytes)
        logger.info("Parsed %d trip delays", len(trip_delays))
    except Exception as exc:
        logger.error("Failed to parse trip updates: %s", exc)

    alerts = []
    try:
        alerts = parse_alerts(alerts_bytes)
        logger.info("Parsed %d alerts", len(alerts))
    except Exception as exc:
        logger.error("Failed to parse alerts: %s", exc)

    # ── 3. Write to Redis ─────────────────────────────────────────────────────
    try:
        await write_vehicles(redis, vehicles)
        await write_alerts(redis, alerts)
    except Exception as exc:
        logger.error("Failed to write to Redis: %s", exc)


async def main() -> None:
    """Main worker loop — runs forever until interrupted."""
    logger.info("Worker starting. Interval: %ds", WORKER_INTERVAL)

    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)

    backoff = WORKER_INTERVAL  # start with normal interval

    while True:
        start = time.monotonic()
        try:
            await run_cycle(redis)
            backoff = WORKER_INTERVAL  # reset backoff on success
        except Exception as exc:
            logger.error("Unexpected error in cycle: %s", exc)
            backoff = min(backoff * 2, 300)  # exponential backoff, max 5 min
            logger.info("Backing off for %ds", backoff)

        elapsed = time.monotonic() - start
        sleep   = max(0, backoff - elapsed)
        logger.info("Cycle done in %.1fs, sleeping %.1fs", elapsed, sleep)
        await asyncio.sleep(sleep)


if __name__ == "__main__":
    asyncio.run(main())
