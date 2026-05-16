"""
GTFS-RT Protobuf parser.

Decodes raw bytes from Waltti feeds into plain Python dicts.
Every optional GTFS field is null-checked — the feed can omit any field.
"""
import logging
from google.transit import gtfs_realtime_pb2

logger = logging.getLogger(__name__)


def parse_vehicle_positions(raw_bytes: bytes) -> list[dict]:
    """
    Decode VehiclePositions protobuf feed → list of raw vehicle dicts.

    Each dict contains:
        id, route_id, trip_id, lat, lon, bearing, speed_kmh, label, timestamp

    Skips entities missing a position or with lat/lon of exactly 0.0 (GPS not ready).
    """
    if not raw_bytes:
        return []

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    vehicles = []
    skipped  = 0

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle

        if not v.HasField("position"):
            skipped += 1
            continue

        # lat/lon exactly 0.0 means the GPS fix is missing
        if v.position.latitude == 0.0 and v.position.longitude == 0.0:
            skipped += 1
            continue

        vehicles.append({
            "id":        entity.id,
            "route_id":  v.trip.route_id if v.HasField("trip") else None,
            "trip_id":   v.trip.trip_id  if v.HasField("trip") else None,
            "lat":       v.position.latitude,
            "lon":       v.position.longitude,
            "bearing":   v.position.bearing if v.position.bearing else None,
            "speed_kmh": round(v.position.speed * 3.6, 1) if v.position.speed else None,
            "label":     (v.vehicle.label or entity.id) if v.HasField("vehicle") else entity.id,
            "timestamp": v.timestamp or None,
        })

    if skipped:
        logger.warning("Skipped %d vehicle entities with missing position", skipped)

    return vehicles


def parse_trip_updates(raw_bytes: bytes) -> list[dict]:
    """
    Decode TripUpdates protobuf feed → list of trip delay dicts.

    Each dict contains:
        trip_id, delay_seconds, is_realtime

    delay_seconds is taken from the first stop_time_update that has a departure delay.
    Falls back to arrival delay if departure is not present.
    """
    if not raw_bytes:
        return []

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    delays = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update

        trip_id = tu.trip.trip_id if tu.HasField("trip") else None
        if not trip_id:
            continue

        delay = 0
        for stu in tu.stop_time_update:
            if stu.HasField("departure") and stu.departure.HasField("delay"):
                delay = stu.departure.delay
                break
            elif stu.HasField("arrival") and stu.arrival.HasField("delay"):
                delay = stu.arrival.delay
                break

        delays.append({"trip_id": trip_id, "delay_seconds": delay, "is_realtime": True})

    return delays


def parse_alerts(raw_bytes: bytes) -> list[dict]:
    """
    Decode Alerts protobuf feed → list of alert dicts.

    NOTE: Waltti/LINKKI does not currently publish a GTFS-RT alerts feed.
    This function is implemented but will always receive empty bytes from
    waltti_client.fetch_alerts(), so it will always return [].

    If Waltti adds an alerts feed in future, this code is ready.
    """
    if not raw_bytes:
        return []

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    alerts = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        a = entity.alert

        route_ids = [
            informed.route_id
            for informed in a.informed_entity
            if informed.route_id
        ]

        header = a.header_text.translation[0].text if a.header_text.translation else ""
        description = a.description_text.translation[0].text if a.description_text.translation else ""

        alerts.append({
            "id":          entity.id,
            "header":      header,
            "description": description,
            "effect":      a.effect.name if a.effect else "UNKNOWN_EFFECT",
            "cause":       a.cause.name  if a.cause  else "UNKNOWN_CAUSE",
            "route_ids":   route_ids,
        })

    return alerts
