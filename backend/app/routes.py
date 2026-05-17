import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.dependencies import get_redis
from config import PLAN_CACHE_TTL, GEO_CACHE_TTL
from processing import vehicle_service, geocoder, route_planner
from processing.models import Location
from ingestion import digitransit_client, cache_writer

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/geocode")
async def geocode_endpoint(
    q:     str = Query(..., description="Location name to search for"),
    redis = Depends(get_redis),
):
    """
    Search for a location by name. Returns list of matching places with coordinates.

    Flow:
      1. Check Redis cache (geo:{q})
      2. Cache hit  → return immediately
      3. Cache miss → call Digitransit geocoding API → cache 24h → return
      4. Digitransit failure → return 503
    """
    cache_key = f"geo:{q.lower().strip()}"

    # ── Cache check ───────────────────────────────────────────────────────────
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis read failed for geocode: %s", exc)

    # ── Real API call ─────────────────────────────────────────────────────────
    try:
        raw       = await digitransit_client.geocode(q)
        locations = geocoder.parse_geocoding_response(raw)
        result    = [
            {"name": l.name, "lat": l.lat, "lon": l.lon, "type": l.type, "id": l.id}
            for l in locations
        ]
        if redis:
            await cache_writer.write_geocode(redis, cache_key, result, ttl=GEO_CACHE_TTL)
        return result
    except Exception as exc:
        logger.error("Geocoding failed: %s", exc)
        return JSONResponse({"error": "Geocoding service unavailable"}, status_code=503)


class PlanRequest(BaseModel):
    from_lat:  float
    from_lon:  float
    to_lat:    float
    to_lon:    float
    from_name: str = ""
    to_name:   str = ""


@router.post("/api/plan")
async def plan(body: PlanRequest, redis = Depends(get_redis)):
    """
    Find public transport routes between two coordinates.

    Flow:
      1. Check Redis cache (plan:{hash(coords)})
      2. Cache hit  → return immediately
      3. Cache miss → call Digitransit GraphQL → cache 5min → return
      4. Digitransit failure → 503
    """
    import hashlib
    cache_key = "plan:" + hashlib.md5(
        f"{body.from_lat:.5f},{body.from_lon:.5f},{body.to_lat:.5f},{body.to_lon:.5f}".encode()
    ).hexdigest()

    # ── Cache check ───────────────────────────────────────────────────────────
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Redis read failed for plan: %s", exc)

    # ── Real API call ─────────────────────────────────────────────────────────
    try:
        raw      = await digitransit_client.plan_route(body.from_lat, body.from_lon, body.to_lat, body.to_lon)
        from_loc = Location(body.from_name or "Origin",      body.from_lat, body.from_lon, "place")
        to_loc   = Location(body.to_name   or "Destination", body.to_lat,   body.to_lon,   "place")
        result   = route_planner.parse_plan_response(raw, from_loc, to_loc)

        # Serialize to dict for JSON response + caching
        payload = {
            "from":   {"name": from_loc.name, "lat": from_loc.lat, "lon": from_loc.lon},
            "to":     {"name": to_loc.name,   "lat": to_loc.lat,   "lon": to_loc.lon},
            "routes": [
                {
                    "route_id":             r.route_id,
                    "route_name":           r.route_name,
                    "departure_time":       r.departure_time,
                    "arrival_time":         r.arrival_time,
                    "duration_minutes":     r.duration_minutes,
                    "walk_distance_meters": r.walk_distance_meters,
                    "legs": [
                        {
                            "mode":             leg.mode,
                            "route_id":         leg.route_id,
                            "route_name":       leg.route_name,
                            "from_name":        leg.from_name,
                            "to_name":          leg.to_name,
                            "departure_time":   leg.departure_time,
                            "arrival_time":     leg.arrival_time,
                            "duration_minutes": leg.duration_minutes,
                            "geometry":         leg.geometry,
                        }
                        for leg in r.legs
                    ],
                }
                for r in result.routes
            ],
            "is_stale": result.is_stale,
            "error":    result.error,
        }

        if redis:
            await cache_writer.write_plan(redis, cache_key, payload, ttl=PLAN_CACHE_TTL)

        return payload

    except Exception as exc:
        logger.error("Route planning failed: %s", exc)
        return JSONResponse(
            {"error": "Route planning service unavailable", "routes": []},
            status_code=503,
        )


@router.get("/api/alerts/{route_id}")
async def get_alerts(route_id: str, redis = Depends(get_redis)):
    """
    Return active service alerts for a given route.

    Merges two Redis keys:
      alerts:{route_id}  — alerts that explicitly name this route
      alerts:ALL         — network-wide/stop-based alerts with no route_id

    LINKKI alerts are currently stop-based (informed_entity uses stop_id),
    so they land in alerts:ALL and are returned for every route.
    """
    if not redis:
        return []

    results = []
    try:
        for key in (f"alerts:{route_id}", "alerts:ALL"):
            raw = await redis.get(key)
            if raw:
                results.extend(json.loads(raw))
    except Exception as exc:
        logger.warning("Redis read failed for alerts: %s", exc)

    return results


@router.get("/api/shape/{trip_id:path}")
async def get_shape(trip_id: str, redis = Depends(get_redis)):
    """
    Return the road-snapped shape for a GTFS trip as {points: [[lat,lon], ...]}.

    Shape points come from Digitransit pattern.geometry — the actual road the
    vehicle travels, giving smooth road-following animation on the frontend.

    Cached 24 h because trip shapes never change within a service day.
    trip_id is the raw value from GTFS-RT (no LINKKI: prefix needed here).
    """
    cache_key = f"shape:{trip_id}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return {"points": json.loads(cached)}
        except Exception as exc:
            logger.warning("Redis read failed for shape: %s", exc)

    try:
        points = await digitransit_client.fetch_trip_shape(trip_id)
        if redis and points:
            await redis.set(cache_key, json.dumps(points), ex=GEO_CACHE_TTL)
        return {"points": points}
    except Exception as exc:
        logger.error("Shape fetch failed for %s: %s", trip_id, exc)
        return {"points": []}


@router.get("/api/trip/{trip_id}/stops")
async def get_trip_stops(trip_id: str, redis = Depends(get_redis)):
    """
    Return the ordered stop list for a trip, used by the bus journey sidebar.

    Flow:
      1. Check cache trip_stops:{trip_id} (24 h TTL — static data, never changes intraday)
      2. HGETALL schedule:{trip_id} → all stop_ids, scheduled seconds, sequences
         (schedule hash stores "{stop_id}" → seconds AND "{stop_id}:seq" → sequence_number)
      3. Pipeline HGETALL stop:{stop_id} for every stop → name + lat/lon
      4. Sort by sequence, format scheduled_time as "HH:MM", cache + return

    Returns [] if trip has no schedule data (GTFS not loaded yet).
    Returns 404 if trip_id is not found at all.
    """
    if not redis:
        return []

    cache_key = f"trip_stops:{trip_id}"

    # ── Cache check ───────────────────────────────────────────────────────────
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as exc:
        logger.warning("Redis read failed for trip_stops: %s", exc)

    # ── Read schedule hash ────────────────────────────────────────────────────
    try:
        schedule = await redis.hgetall(f"schedule:{trip_id}")
    except Exception as exc:
        logger.error("Failed to read schedule for trip %s: %s", trip_id, exc)
        return []

    if not schedule:
        return JSONResponse(
            {"error": "Trip not found in GTFS schedule"},
            status_code=404,
        )

    # The schedule hash contains two kinds of fields:
    #   "207579"      → "48780"   (seconds since midnight — scheduled arrival)
    #   "207579:seq"  → "12"      (stop_sequence — position in trip)
    # Split them into two dicts.
    stop_times: dict[str, int] = {}
    stop_seqs:  dict[str, int] = {}

    for field, value in schedule.items():
        if field.endswith(":seq"):
            stop_seqs[field[:-4]] = int(value)   # strip the ":seq" suffix
        else:
            try:
                stop_times[field] = int(value)
            except ValueError:
                continue

    stop_ids = list(stop_times.keys())
    if not stop_ids:
        return []

    # ── Fetch stop metadata via pipeline (one round trip) ────────────────────
    try:
        pipe = redis.pipeline()
        for stop_id in stop_ids:
            pipe.hgetall(f"stop:{stop_id}")
        stop_data_list = await pipe.execute()
    except Exception as exc:
        logger.error("Failed to fetch stop metadata for trip %s: %s", trip_id, exc)
        return []

    # ── Assemble + sort result ────────────────────────────────────────────────
    stops = []
    for stop_id, stop_data in zip(stop_ids, stop_data_list):
        if not stop_data:
            continue  # stop_id in schedule but missing from stops.txt — skip

        secs    = stop_times[stop_id]
        # Use mod 86400 so GTFS times > 24:00 (night buses) display as a
        # sensible clock time rather than "25:30"
        hours   = (secs % 86400) // 3600
        minutes = (secs % 3600)  // 60

        stops.append({
            "stop_id":        stop_id,
            "name":           stop_data.get("name", ""),
            "lat":            float(stop_data.get("lat", 0)),
            "lon":            float(stop_data.get("lon", 0)),
            "scheduled_time": f"{hours:02d}:{minutes:02d}",
            "sequence":       stop_seqs.get(stop_id, 0),
        })

    stops.sort(key=lambda s: s["sequence"])

    # ── Cache result (static data — safe to cache 24 h) ──────────────────────
    try:
        await redis.set(cache_key, json.dumps(stops), ex=GEO_CACHE_TTL)
    except Exception as exc:
        logger.warning("Failed to cache trip_stops %s: %s", trip_id, exc)

    return stops


@router.get("/api/routes")
async def get_routes(redis = Depends(get_redis)):
    """Return list of route IDs that currently have active vehicles."""
    if redis:
        try:
            raw = await redis.get("vehicles:route_ids")
            if raw:
                return {"routes": json.loads(raw)}
        except Exception as exc:
            logger.warning("Redis read failed for route_ids: %s", exc)

    return {"routes": []}


@router.websocket("/ws/vehicles/{route_id}")
async def vehicle_stream(
    websocket: WebSocket,
    route_id:  str,
    redis = Depends(get_redis),
):
    """
    WebSocket endpoint — streams live vehicle positions to the client.

    Flow:
      1. Accept connection
      2. Send current vehicles:{route_id} from Redis immediately
      3. Subscribe to Redis Pub/Sub "vehicles:updated"
      4. On each event: read fresh data + compute freshness → send
      5. On disconnect: unsubscribe cleanly
    """
    await websocket.accept()
    logger.info("WebSocket opened: route=%s", route_id)

    try:
        await _real_stream(websocket, route_id, redis)
    except WebSocketDisconnect:
        logger.info("WebSocket closed: route=%s", route_id)
    except Exception as exc:
        logger.error("WebSocket error route=%s: %s", route_id, exc)


async def _real_stream(websocket: WebSocket, route_id: str, redis) -> None:
    """Stream real vehicle data from Redis via Pub/Sub."""

    def _log_send(trigger: str, vehicle_count: int, freshness_level: str, age_seconds: int) -> None:
        """
        Emit a structured log line for every message sent to the frontend.

        trigger:
          "connect"   – first send on WebSocket open (client just connected)
          "pubsub"    – worker published new data; frontend gets a live push
          "heartbeat" – 10s keepalive; data may be unchanged
          "empty"     – no vehicles in Redis yet (worker hasn't run)

        Having this log means: if the frontend shows something wrong you can open
        the terminal and see exactly what was sent, when, and why.
        """
        logger.info(
            "ws_send",
            extra={
                "route_id":       route_id,
                "trigger":        trigger,
                "vehicle_count":  vehicle_count,
                "freshness":      freshness_level,
                "age_seconds":    age_seconds,
            },
        )

    async def _build_payload() -> tuple[str, int, str, int] | tuple[None, int, str, int]:
        """
        Build the WebSocket payload from Redis.
        Returns (json_str, vehicle_count, freshness_level, age_seconds).
        Returns (None, ...) if no vehicle data exists yet.
        """
        raw = await redis.get(f"vehicles:{route_id}")
        if not raw:
            return None, 0, "STALE", 0
        vehicles = json.loads(raw)

        fetched_at_raw = await redis.get("vehicles:fetched_at")
        fetched_at     = float(fetched_at_raw) if fetched_at_raw else 0.0
        freshness      = vehicle_service.compute_freshness(fetched_at)

        payload = json.dumps({
            "route_id":      route_id,
            "vehicle_count": len(vehicles),
            "vehicles":      vehicles,
            "alerts":        [],
            "freshness": {
                "level":       freshness.level.value,
                "label":       freshness.label,
                "age_seconds": freshness.age_seconds,
            },
        })
        return payload, len(vehicles), freshness.level.value, freshness.age_seconds

    # ── Initial send on connect ───────────────────────────────────────────────
    payload, v_count, f_level, f_age = await _build_payload()
    if payload:
        await websocket.send_text(payload)
        _log_send("connect", v_count, f_level, f_age)
    else:
        # Worker hasn't written anything yet — send empty state
        empty = json.dumps({
            "route_id": route_id, "vehicle_count": 0, "vehicles": [], "alerts": [],
            "freshness": {"level": "STALE", "label": "Waiting for data…", "age_seconds": 0},
        })
        await websocket.send_text(empty)
        _log_send("empty", 0, "STALE", 0)

    # ── Subscribe and stream updates ─────────────────────────────────────────
    pubsub = redis.pubsub()
    await pubsub.subscribe("vehicles:updated")

    try:
        last_send = time.time()
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            now     = time.time()

            is_pubsub    = message and message["type"] == "message"
            is_heartbeat = (now - last_send) >= 10

            # Send on Pub/Sub event OR every 10s as a heartbeat.
            # The heartbeat serves two purposes:
            #   1. Keeps the connection alive between 30s worker cycles
            #   2. Detects silently disconnected clients (send_text raises on dead socket)
            if is_pubsub or is_heartbeat:
                payload, v_count, f_level, f_age = await _build_payload()
                if payload:
                    await websocket.send_text(payload)
                    _log_send("pubsub" if is_pubsub else "heartbeat", v_count, f_level, f_age)
                    last_send = now

            await asyncio.sleep(0.05)
    finally:
        await pubsub.unsubscribe("vehicles:updated")
        await pubsub.aclose()


# ══════════════════════════════════════════════════════════════════════════════
# OBSERVABILITY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/health")
async def health(redis=Depends(get_redis)):
    """
    System health check.

    Returns a snapshot of key operational signals:
      redis            – can we reach the data store?
      gtfs_loaded      – is the static schedule available? (needed for delay colours)
      data_age_seconds – how stale are vehicle positions? (> 120 s → STALE badge)
      active_routes    – how many routes currently have live buses?
      total_vehicles   – total active vehicles across all routes

    HTTP 200 → healthy.  HTTP 503 → degraded (Redis down or exception).
    """
    result: dict = {
        "status":           "degraded",
        "redis":            "unavailable",
        "gtfs_loaded":      False,
        "data_age_seconds": None,
        "active_routes":    0,
        "total_vehicles":   0,
    }

    if not redis:
        return JSONResponse(result, status_code=503)

    try:
        await redis.ping()
        result["redis"] = "ok"

        # Is the static GTFS schedule loaded? Required for delay computation.
        gtfs_date = await redis.get("gtfs:loaded_date")
        result["gtfs_loaded"] = bool(gtfs_date)
        if gtfs_date:
            result["gtfs_loaded_date"] = gtfs_date

        # How old is the most recent vehicle snapshot?
        fetched_at_raw = await redis.get("vehicles:fetched_at")
        if fetched_at_raw:
            result["data_age_seconds"] = round(time.time() - float(fetched_at_raw))

        # How many routes/vehicles are active right now?
        route_ids_raw = await redis.get("vehicles:route_ids")
        result["active_routes"] = len(json.loads(route_ids_raw)) if route_ids_raw else 0

        total_vehicles_raw = await redis.get("stats:total_vehicles")
        result["total_vehicles"] = int(total_vehicles_raw) if total_vehicles_raw else 0

        result["status"] = "healthy"
        return result

    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        result["error"] = str(exc)
        return JSONResponse(result, status_code=503)


@router.get("/api/stats")
async def stats(redis=Depends(get_redis)):
    """
    Operational telemetry counters.

    All values are best-effort — keys may not exist on first boot.
      fetch_cycles           – total worker cycles completed since startup
      last_cycle_ms          – duration of the most recent fetch cycle
      total_vehicles_tracked – vehicle count from the most recent cycle
    """
    if not redis:
        return {"error": "Redis unavailable"}

    try:
        fetch_count_raw, last_ms_raw, total_v_raw = await asyncio.gather(
            redis.get("stats:fetch_count"),
            redis.get("stats:last_cycle_ms"),
            redis.get("stats:total_vehicles"),
        )
        return {
            "fetch_cycles":           int(fetch_count_raw) if fetch_count_raw else 0,
            "last_cycle_ms":          int(last_ms_raw)     if last_ms_raw     else None,
            "total_vehicles_tracked": int(total_v_raw)     if total_v_raw     else 0,
        }

    except Exception as exc:
        logger.error("Stats endpoint error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=503)
