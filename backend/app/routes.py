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

    async def _build_payload() -> str | None:
        raw = await redis.get(f"vehicles:{route_id}")
        if not raw:
            return None
        vehicles = json.loads(raw)

        fetched_at_raw = await redis.get("vehicles:fetched_at")
        fetched_at     = float(fetched_at_raw) if fetched_at_raw else 0.0
        freshness      = vehicle_service.compute_freshness(fetched_at)

        return json.dumps({
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

    # Send current state immediately on connect
    payload = await _build_payload()
    if payload:
        await websocket.send_text(payload)
    else:
        # Worker hasn't written anything yet — send empty state
        await websocket.send_text(json.dumps({
            "route_id": route_id, "vehicle_count": 0, "vehicles": [], "alerts": [],
            "freshness": {"level": "STALE", "label": "Waiting for data…", "age_seconds": 0},
        }))

    # Subscribe and stream updates
    pubsub = redis.pubsub()
    await pubsub.subscribe("vehicles:updated")

    try:
        last_send = time.time()
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            now = time.time()
            # Send on Pub/Sub event OR every 10s as a heartbeat.
            # The heartbeat serves two purposes:
            #   1. Keeps the connection alive between 30s worker cycles
            #   2. Detects silently disconnected clients (send_text raises on dead socket)
            if message and message["type"] == "message" or (now - last_send) >= 10:
                payload = await _build_payload()
                if payload:
                    await websocket.send_text(payload)
                    last_send = now
            await asyncio.sleep(0.05)
    finally:
        await pubsub.unsubscribe("vehicles:updated")
        await pubsub.aclose()


