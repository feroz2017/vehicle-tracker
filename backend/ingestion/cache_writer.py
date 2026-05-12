import json
import logging
from config import VEHICLE_CACHE_TTL, ALERTS_CACHE_TTL

logger = logging.getLogger(__name__)

PUBSUB_CHANNEL = "vehicles:updated"


async def write_vehicles(redis, vehicles: list[dict]) -> None:
    """
    Store vehicle positions in Redis, grouped by route_id.
    Publishes PUBSUB_CHANNEL event after writing so FastAPI WebSocket
    handlers push fresh data to connected clients.

    Key pattern:  vehicles:{route_id}
    TTL:          VEHICLE_CACHE_TTL (60s) — survives one missed worker cycle
    """
    # Group vehicles by route_id
    by_route: dict[str, list[dict]] = {}
    for v in vehicles:
        route_id = v.get("route_id")
        if not route_id:
            continue
        by_route.setdefault(route_id, []).append(v)

    # Write each route's vehicles to Redis
    for route_id, route_vehicles in by_route.items():
        key = f"vehicles:{route_id}"
        await redis.set(key, json.dumps(route_vehicles), ex=VEHICLE_CACHE_TTL)

    # Also write the full set for /api/routes (route ID discovery)
    all_route_ids = sorted(by_route.keys())
    await redis.set("vehicles:route_ids", json.dumps(all_route_ids), ex=VEHICLE_CACHE_TTL)

    # Notify all FastAPI instances that new data is available
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
