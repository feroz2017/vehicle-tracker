import json
import logging
from dataclasses import asdict
from config import VEHICLE_CACHE_TTL, ALERTS_CACHE_TTL

logger = logging.getLogger(__name__)

PUBSUB_CHANNEL = "vehicles:updated"


async def write_vehicles(redis, vehicles: list, fetched_at: float) -> None:
    """
    Store enriched Vehicle objects in Redis, grouped by route_id.

    Keys written:
      vehicles:{route_id}  → JSON list of vehicle dicts (TTL: VEHICLE_CACHE_TTL)
      vehicles:fetched_at  → unix timestamp string (so WS can compute live freshness)
      vehicles:route_ids   → JSON list of all active route IDs

    Publishes to PUBSUB_CHANNEL so every FastAPI instance pushes to its WebSocket clients.
    """
    by_route: dict[str, list[dict]] = {}
    for v in vehicles:
        if not v.route_id:
            continue
        d = asdict(v)
        d["delay_label"] = v.delay_label   # include computed property
        by_route.setdefault(v.route_id, []).append(d)

    for route_id, route_vehicles in by_route.items():
        await redis.set(f"vehicles:{route_id}", json.dumps(route_vehicles), ex=VEHICLE_CACHE_TTL)

    all_route_ids = sorted(by_route.keys())
    await redis.set("vehicles:route_ids", json.dumps(all_route_ids), ex=VEHICLE_CACHE_TTL)

    # Store fetch timestamp separately — WS reads this to compute freshness at send time
    await redis.set("vehicles:fetched_at", str(fetched_at), ex=VEHICLE_CACHE_TTL)

    await redis.publish(PUBSUB_CHANNEL, "updated")
    logger.info("Wrote %d routes to Redis, published to %s", len(by_route), PUBSUB_CHANNEL)


async def write_alerts(redis, alerts: list[dict]) -> None:
    """
    Store service alerts in Redis, grouped by route_id.
    Alerts with no route_ids are stored under key 'alerts:ALL' (network-wide).

    Key pattern:  alerts:{route_id} | alerts:ALL
    TTL:          ALERTS_CACHE_TTL (60s)
    """
    by_route: dict[str, list[dict]] = {"ALL": []}

    for alert in alerts:
        route_ids = alert.get("route_ids", [])
        if not route_ids:
            by_route["ALL"].append(alert)
        else:
            for route_id in route_ids:
                by_route.setdefault(route_id, []).append(alert)

    for key_suffix, route_alerts in by_route.items():
        await redis.set(
            f"alerts:{key_suffix}",
            json.dumps(route_alerts),
            ex=ALERTS_CACHE_TTL,
        )

    logger.info("Wrote alerts for %d route keys to Redis", len(by_route))


async def write_plan(redis, cache_key: str, result: dict, ttl: int) -> None:
    """Store a route plan result in Redis with given TTL."""
    await redis.set(cache_key, json.dumps(result), ex=ttl)


async def write_geocode(redis, cache_key: str, result: dict, ttl: int) -> None:
    """Store a geocoding result in Redis with given TTL."""
    await redis.set(cache_key, json.dumps(result), ex=ttl)
