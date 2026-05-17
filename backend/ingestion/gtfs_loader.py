"""
Static GTFS loader — downloads Jyväskylä timetable and loads stop schedules into Redis.

Waltti publishes a fresh ZIP nightly at 01:00 EET.
This script is run by the gtfs-loader Docker service at startup then every 24 h.
It can also be run manually:  python -m ingestion.gtfs_loader

Redis structure written:
    schedule:{trip_id}   Hash   {stop_id → seconds_since_midnight,
                                 stop_id:seq → stop_sequence}
    stop:{stop_id}       Hash   {name, lat, lon}
    gtfs:loaded_date     String  "2026-05-17"  (so we skip re-loading on same day)

The schedule keys are used by vehicle_service.enrich_with_updates() to compute
real delay (predicted arrival − scheduled arrival) for each vehicle's next stop.
The stop keys are used by GET /api/trip/{trip_id}/stops to build the sidebar
stop list with names and coordinates.
"""
import asyncio
import csv
import io
import logging
import zipfile
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis

from config import REDIS_URL, GTFS_STATIC_URL, GTFS_SCHEDULE_TTL

# No basicConfig here — library modules must not configure root logging.
# When run standalone (python -m ingestion.gtfs_loader), main() calls setup_logging().
# When imported by worker.py, worker's setup_logging() already owns the root logger.
logger = logging.getLogger(__name__)

LOADED_DATE_KEY = "gtfs:loaded_date"   # stores "YYYY-MM-DD" of last successful load


def _time_to_seconds(time_str: str) -> int:
    """
    Convert a GTFS time string to seconds since midnight.

    GTFS allows times > 24:00 for trips that run past midnight
    (e.g. "25:30:00" = 1:30 AM the following day = 91800 seconds).
    We store the raw value — the delay computation in vehicle_service
    handles the comparison correctly because both sides use the same
    convention (seconds since service-day midnight).
    """
    parts = time_str.strip().split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s


async def load_schedule(redis) -> int:
    """
    Download the static GTFS ZIP, parse stop_times.txt, and write to Redis.

    Each trip becomes one Redis Hash:
        Key:    schedule:{trip_id}
        Fields: {stop_id: seconds_since_midnight}
        TTL:    GTFS_SCHEDULE_TTL (25 h)

    Uses Redis pipelining — flushes every 500 trips to keep memory flat.
    Returns the total number of stop-time rows loaded.
    """
    logger.info("Downloading static GTFS from %s ...", GTFS_STATIC_URL)

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(GTFS_STATIC_URL)
        response.raise_for_status()
        zip_bytes = response.content

    logger.info("Downloaded %.1f MB, parsing stop_times.txt ...", len(zip_bytes) / 1_000_000)

    z = zipfile.ZipFile(io.BytesIO(zip_bytes))

    total_rows    = 0
    trips_in_pipe = 0
    pipe          = redis.pipeline()

    current_trip_id = None
    current_mapping: dict[str, int] = {}

    def _flush_trip() -> None:
        """Write accumulated stop mapping for current_trip_id into the pipeline."""
        nonlocal trips_in_pipe
        if not current_trip_id or not current_mapping:
            return
        pipe.hset(f"schedule:{current_trip_id}", mapping=current_mapping)
        pipe.expire(f"schedule:{current_trip_id}", GTFS_SCHEDULE_TTL)
        trips_in_pipe += 1

    with z.open("stop_times.txt") as raw_file:
        reader = csv.DictReader(io.TextIOWrapper(raw_file, encoding="utf-8"))

        for row in reader:
            trip_id  = row.get("trip_id", "").strip()
            stop_id  = row.get("stop_id", "").strip()
            arr_time = row.get("arrival_time", "").strip()

            if not trip_id or not stop_id or not arr_time:
                continue

            # New trip — flush previous trip's data
            if trip_id != current_trip_id:
                _flush_trip()

                # Execute pipeline every 500 trips to bound memory usage
                if trips_in_pipe >= 500:
                    await pipe.execute()
                    pipe          = redis.pipeline()
                    trips_in_pipe = 0

                current_trip_id = trip_id
                current_mapping = {}

            try:
                current_mapping[stop_id] = _time_to_seconds(arr_time)
                total_rows += 1
                # Also store stop_sequence so the endpoint can return stops in order.
                # Stored as "{stop_id}:seq" in the same hash to avoid extra Redis keys.
                seq = row.get("stop_sequence", "").strip()
                if seq:
                    current_mapping[f"{stop_id}:seq"] = int(seq)
            except (ValueError, IndexError):
                continue  # malformed time string — skip

    # Flush the final trip
    _flush_trip()
    if trips_in_pipe > 0:
        await pipe.execute()

    logger.info("Loaded %d stop-time entries into Redis", total_rows)

    # Load stop metadata (name, lat, lon) from stops.txt in the same ZIP.
    # Must be called after the stop_times loop so we reuse the already-open ZipFile.
    await _load_stops(z, redis)

    return total_rows


async def _load_stops(z: zipfile.ZipFile, redis) -> int:
    """
    Parse stops.txt from the already-downloaded GTFS ZIP and write stop metadata
    into Redis.

    Redis structure written:
        stop:{stop_id}   Hash   {name, lat, lon}
        TTL:             GTFS_SCHEDULE_TTL (25 h)

    Called from load_schedule() — reuses the open ZipFile so we don't re-download.
    Returns the number of stops loaded.
    """
    logger.info("Parsing stops.txt ...")

    pipe  = redis.pipeline()
    count = 0
    batch = 0

    with z.open("stops.txt") as raw_file:
        reader = csv.DictReader(io.TextIOWrapper(raw_file, encoding="utf-8"))

        for row in reader:
            stop_id = row.get("stop_id",   "").strip()
            name    = row.get("stop_name", "").strip()
            lat     = row.get("stop_lat",  "").strip()
            lon     = row.get("stop_lon",  "").strip()

            if not stop_id or not name or not lat or not lon:
                continue

            # Validate lat/lon are valid floats before storing
            try:
                float(lat)
                float(lon)
            except ValueError:
                continue

            pipe.hset(f"stop:{stop_id}", mapping={"name": name, "lat": lat, "lon": lon})
            pipe.expire(f"stop:{stop_id}", GTFS_SCHEDULE_TTL)
            count += 1
            batch += 1

            # Flush every 500 stops to keep memory flat
            if batch >= 500:
                await pipe.execute()
                pipe  = redis.pipeline()
                batch = 0

    if batch > 0:
        await pipe.execute()

    logger.info("Loaded %d stops into Redis", count)
    return count


async def load_if_needed(redis) -> bool:
    """
    Load the static GTFS schedule only if it hasn't been loaded today.

    Checks the 'gtfs:loaded_date' Redis key (format: "YYYY-MM-DD").
    Returns True if a fresh load was performed, False if already up to date.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        loaded_date = await redis.get(LOADED_DATE_KEY)
    except Exception as exc:
        logger.warning("Could not check gtfs:loaded_date: %s", exc)
        loaded_date = None

    if loaded_date == today:
        logger.info("Static GTFS already loaded for %s — skipping", today)
        return False

    try:
        await load_schedule(redis)
        # Mark today as loaded — expires after 25 h so tomorrow we reload
        await redis.set(LOADED_DATE_KEY, today, ex=GTFS_SCHEDULE_TTL)
        logger.info("Static GTFS loaded successfully for %s", today)
        return True
    except Exception as exc:
        logger.error("Failed to load static GTFS: %s", exc)
        # Non-fatal — app runs without delay data, shows "No delay data"
        return False


async def main() -> None:
    """
    Standalone entry point with APScheduler cron.

    Runs load_if_needed() immediately on startup, then schedules a daily
    reload at 01:30 EET — 30 minutes after Waltti publishes the new ZIP.

    Run:  python -m ingestion.gtfs_loader
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron     import CronTrigger
    from app.logging_config import setup_logging
    setup_logging()   # JSON logging when run as a standalone process

    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)

    # Load immediately on startup so schedule data is ready before first worker cycle
    await load_if_needed(redis)

    # Schedule nightly reload at 01:30 EET (UTC+3 in summer, UTC+2 in winter)
    # timezone="Europe/Helsinki" handles DST automatically
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        load_schedule,
        CronTrigger(hour=1, minute=30, timezone="Europe/Helsinki"),
        args=[redis],
        id="gtfs_nightly_reload",
        name="Nightly static GTFS reload",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — GTFS will reload nightly at 01:30 EET")

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(3600)   # heartbeat — wake up hourly to stay alive
    except (KeyboardInterrupt, SystemExit):
        logger.info("GTFS loader shutting down")
    finally:
        scheduler.shutdown()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
