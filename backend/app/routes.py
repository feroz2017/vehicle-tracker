import asyncio
import json
import logging
import random
import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.dependencies import get_redis
from processing import vehicle_service, geocoder, route_planner, alert_filter
from processing.models import (
    Location, Vehicle, ServiceAlert, Route, RouteLeg,
    PlanResult, FreshnessLevel, FreshnessStatus,
)
from ingestion import digitransit_client, cache_writer

logger = logging.getLogger(__name__)
router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# DUMMY DATA — remove section once real APIs are connected
# ══════════════════════════════════════════════════════════════════════════════

DUMMY_LOCATIONS = {
    "jyvaskyla": [
        Location("Jyväskylä railway station",    62.2415, 25.7187, "station",  "jyvaskyla-station"),
        Location("Jyväskylä city centre",         62.2416, 25.7209, "place",    "jyvaskyla-centre"),
        Location("Jyväskylä bus terminal",        62.2401, 25.7187, "stop",     "jyvaskyla-bus"),
    ],
    "university": [
        Location("University of Jyväskylä",       62.2289, 25.7427, "place",    "uoj"),
        Location("University (Mattilanniemi)",     62.2311, 25.7352, "stop",     "uoj-stop"),
    ],
    "default": [
        Location("Jyväskylä city centre",         62.2416, 25.7209, "place",    "jyvaskyla-centre"),
    ],
}

DUMMY_VEHICLES_BASE = {
    "4": [
        Vehicle("v-001", "601", "4", 62.2416, 25.7209, 45.0,  32.5, "trip-001", 120, True,  "Keskusta",       "Yliopisto"),
        Vehicle("v-002", "602", "4", 62.2380, 25.7150, 90.0,  28.0, "trip-002",   0, True,  "Asemakatu",      "Keskusta"),
        Vehicle("v-003", "603", "4", 62.2450, 25.7300, 180.0, 0.0,  "trip-003",  60, True,  "Yliopisto",      "Mattilanniemi"),
    ],
    "9": [
        Vehicle("v-010", "901", "9", 62.2450, 25.7250, 270.0, 45.0, "trip-010",   0, True,  "Keljo",          "Keskusta"),
        Vehicle("v-011", "902", "9", 62.2380, 25.7400, 0.0,   38.0, "trip-011", 180, True,  "Keskusta",       "Keljo"),
    ],
    "16": [
        Vehicle("v-020", "160", "16", 62.2500, 25.7100, 135.0, 52.0, "trip-020",  0, False, "Tikkakoski",     "Jkl centrum"),
    ],
}

DUMMY_ALERTS = [
    ServiceAlert("alert-1", "Route 4 — minor delay",
                 "Buses on route 4 are running approximately 2 minutes late due to traffic.",
                 "REDUCED_SERVICE", "OTHER", ["4"]),
    ServiceAlert("alert-2", "Roadworks on Keskussairaalantie",
                 "Roadworks between Keljo and city centre affecting routes 9 and 16.",
                 "DETOUR", "CONSTRUCTION", ["9", "16"]),
]

DUMMY_ROUTES = [
    Route("4",  "Route 4 — Rautpohja–Yliopisto", "14:32", "14:58", 26, 320.0, [
        RouteLeg("WALK", None, None,  "Your location", "Asemakatu stop", "14:28", "14:32", 4,   300.0),
        RouteLeg("BUS",  "4",  "4",   "Asemakatu",     "Yliopisto",      "14:32", "14:54", 22, 4200.0),
        RouteLeg("WALK", None, None,  "Yliopisto stop","Destination",     "14:54", "14:58", 4,   350.0),
    ]),
    Route("9",  "Route 9 — Keljo–Keskusta",       "14:45", "15:10", 25, 280.0, [
        RouteLeg("WALK", None, None,  "Your location", "Keljo stop",     "14:41", "14:45", 4,   250.0),
        RouteLeg("BUS",  "9",  "9",   "Keljo",         "Keskusta",       "14:45", "15:06", 21, 4800.0),
        RouteLeg("WALK", None, None,  "Keskusta stop", "Destination",    "15:06", "15:10", 4,   300.0),
    ]),
]


def _jitter(base: float, amount: float = 0.0005) -> float:
    """Add a small random offset to simulate bus movement."""
    return base + random.uniform(-amount, amount)


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/geocode")
async def geocode(
    q:     str = Query(..., description="Location name to search for"),
    redis = Depends(get_redis),
):
    """
    Search for a location by name. Returns list of matching places with coordinates.

    Flow:
        1. Check Redis cache (key: geo:{q})
        2. Cache hit  → return immediately
        3. Cache miss → call Digitransit geocoding API → cache → return

    TODO: replace dummy response with real implementation once API key is set.
    """
    # ── DUMMY RESPONSE ───────────────────────────────────────────────────────
    query_lower = q.lower()
    matched = next(
        (locs for keyword, locs in DUMMY_LOCATIONS.items() if keyword in query_lower),
        DUMMY_LOCATIONS["default"],
    )
    return [
        {"name": loc.name, "lat": loc.lat, "lon": loc.lon, "type": loc.type, "id": loc.id}
        for loc in matched
    ]
    # ── REAL IMPLEMENTATION (uncomment when API key ready) ───────────────────
    # cache_key = f"geo:{q.lower().strip()}"
    # if redis:
    #     cached = await redis.get(cache_key)
    #     if cached:
    #         return json.loads(cached)
    # try:
    #     raw      = await digitransit_client.geocode(q)
    #     locations = geocoder.parse_geocoding_response(raw)
    #     result   = [{"name": l.name, "lat": l.lat, "lon": l.lon, "type": l.type} for l in locations]
    #     if redis:
    #         await cache_writer.write_geocode(redis, cache_key, result, ttl=86400)
    #     return result
    # except Exception as exc:
    #     logger.error("Geocoding failed: %s", exc)
    #     return JSONResponse({"error": "Geocoding service unavailable"}, status_code=503)


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
        1. Check Redis cache (key: plan:{hash(coords)})
        2. Cache hit  → return with is_stale flag if expired
        3. Cache miss → call Digitransit GraphQL → cache → return
        4. Digitransit failure → return last cached result with error flag

    TODO: replace dummy response with real implementation once API key is set.
    """
    # ── DUMMY RESPONSE ───────────────────────────────────────────────────────
    return {
        "from": {"name": body.from_name or "Origin",      "lat": body.from_lat, "lon": body.from_lon},
        "to":   {"name": body.to_name   or "Destination", "lat": body.to_lat,   "lon": body.to_lon},
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
                    }
                    for leg in r.legs
                ],
            }
            for r in DUMMY_ROUTES
        ],
        "is_stale": False,
        "error":    None,
    }
    # ── REAL IMPLEMENTATION (uncomment when API key ready) ───────────────────
    # import hashlib
    # cache_key = "plan:" + hashlib.md5(
    #     f"{body.from_lat},{body.from_lon},{body.to_lat},{body.to_lon}".encode()
    # ).hexdigest()
    # if redis:
    #     cached = await redis.get(cache_key)
    #     if cached:
    #         return json.loads(cached)
    # try:
    #     raw    = await digitransit_client.plan_route(body.from_lat, body.from_lon, body.to_lat, body.to_lon)
    #     from_loc = Location(body.from_name, body.from_lat, body.from_lon, "place")
    #     to_loc   = Location(body.to_name,   body.to_lat,   body.to_lon,   "place")
    #     result = route_planner.parse_plan_response(raw, from_loc, to_loc)
    #     # TODO: serialize result and cache
    #     return result
    # except Exception as exc:
    #     logger.error("Route planning failed: %s", exc)
    #     return JSONResponse({"error": "Route planning service unavailable", "routes": []}, status_code=503)


@router.get("/api/alerts/{route_id}")
async def get_alerts(route_id: str, redis = Depends(get_redis)):
    """
    Return active service alerts for a given route.

    TODO: read from Redis (key: alerts:{route_id}) once worker is writing real data.
    """
    # ── DUMMY RESPONSE ───────────────────────────────────────────────────────
    matching = alert_filter.filter_by_route(DUMMY_ALERTS, route_id)
    return [
        {
            "id":          a.id,
            "header":      a.header,
            "description": a.description,
            "effect":      a.effect,
            "cause":       a.cause,
        }
        for a in matching
    ]


@router.get("/api/routes")
async def get_routes(redis = Depends(get_redis)):
    """
    Return list of route IDs that currently have active vehicles.

    TODO: read from Redis (key: vehicles:route_ids) once worker is writing real data.
    """
    # ── DUMMY RESPONSE ───────────────────────────────────────────────────────
    return {"routes": sorted(DUMMY_VEHICLES_BASE.keys())}


@router.websocket("/ws/vehicles/{route_id}")
async def vehicle_stream(
    websocket: WebSocket,
    route_id:  str,
    redis = Depends(get_redis),
):
    """
    WebSocket endpoint — streams live vehicle positions to the client.

    Real flow (once worker + Redis are running):
        1. Accept connection
        2. Read current vehicles:{route_id} from Redis → send immediately
        3. Subscribe to Redis Pub/Sub channel 'vehicles:updated'
        4. On event: read fresh data from Redis → send to this client
        5. On disconnect: unsubscribe cleanly

    Dummy flow (current):
        1. Accept connection
        2. Send initial dummy positions for route_id
        3. Every 5s: send slightly moved dummy positions (simulates movement)
        4. On disconnect: exit loop
    """
    await websocket.accept()
    logger.info("WebSocket opened for route %s", route_id)

    try:
        # ── DUMMY STREAMING LOOP ─────────────────────────────────────────────
        # Sends updated dummy positions every 5 seconds so the frontend team
        # can test marker movement. Remove when real Redis Pub/Sub is wired up.
        base_vehicles = DUMMY_VEHICLES_BASE.get(route_id, [])
        tick = 0

        while True:
            fetched_at = time.time() - tick   # fake age increases each cycle
            freshness  = vehicle_service.compute_freshness(fetched_at)

            # Slightly jitter positions to simulate movement
            moved = [
                {
                    "id":               v.id,
                    "label":            v.label,
                    "route_id":         v.route_id,
                    "lat":              _jitter(v.lat),
                    "lon":              _jitter(v.lon),
                    "bearing":          v.bearing,
                    "speed_kmh":        v.speed_kmh,
                    "delay_seconds":    v.delay_seconds,
                    "is_delay_realtime":v.is_delay_realtime,
                    "delay_label":      v.delay_label,
                    "current_stop":     v.current_stop,
                    "next_stop":        v.next_stop,
                }
                for v in base_vehicles
            ]

            alerts  = alert_filter.filter_by_route(DUMMY_ALERTS, route_id)
            payload = {
                "route_id":     route_id,
                "vehicle_count":len(moved),
                "vehicles":     moved,
                "alerts": [
                    {"id": a.id, "header": a.header, "effect": a.effect}
                    for a in alerts
                ],
                "freshness": {
                    "level":       freshness.level.value,
                    "label":       freshness.label,
                    "age_seconds": freshness.age_seconds,
                },
            }

            await websocket.send_text(json.dumps(payload))
            tick += 5
            await asyncio.sleep(5)

        # ── REAL IMPLEMENTATION (uncomment when Redis + worker are ready) ────
        # # Send current state immediately
        # raw = await redis.get(f"vehicles:{route_id}")
        # if raw:
        #     await websocket.send_text(raw)
        #
        # # Subscribe to Pub/Sub channel
        # pubsub = redis.pubsub()
        # await pubsub.subscribe("vehicles:updated")
        #
        # async for message in pubsub.listen():
        #     if message["type"] != "message":
        #         continue
        #     raw = await redis.get(f"vehicles:{route_id}")
        #     if raw:
        #         await websocket.send_text(raw)
        # ────────────────────────────────────────────────────────────────────

    except WebSocketDisconnect:
        logger.info("WebSocket closed for route %s", route_id)
    except Exception as exc:
        logger.error("WebSocket error for route %s: %s", route_id, exc)
