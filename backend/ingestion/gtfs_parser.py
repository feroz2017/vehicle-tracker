"""
GTFS-RT Protobuf parser.

Decodes raw bytes from Waltti feeds into plain Python dicts.
Every optional GTFS field is null-checked — the feed can omit any field.

TODO: install gtfs-realtime-bindings once API key is ready:
    pip install gtfs-realtime-bindings

The import below will fail until the package is installed.
For now, all parse_* functions return empty lists (dummy mode).
"""
import logging

logger = logging.getLogger(__name__)

# TODO: uncomment once gtfs-realtime-bindings is installed
# from google.transit import gtfs_realtime_pb2


def parse_vehicle_positions(raw_bytes: bytes) -> list[dict]:
    """
    Decode VehiclePositions protobuf feed → list of raw vehicle dicts.

    Each dict contains:
        id, route_id, trip_id, lat, lon, bearing, speed_kmh, label, timestamp

    Skips entities that are missing required fields (position, lat, lon).
    Logs how many entities were skipped.
    """
    # TODO: replace with real implementation once package is installed
    # feed = gtfs_realtime_pb2.FeedMessage()
    # feed.ParseFromString(raw_bytes)
    #
    # vehicles = []
    # skipped  = 0
    #
    # for entity in feed.entity:
    #     if not entity.HasField("vehicle"):
    #         continue
    #     v = entity.vehicle
    #
    #     # REQUIRED: skip if no position
    #     if not v.HasField("position"):
    #         skipped += 1
    #         continue
    #
    #     # REQUIRED: skip if lat/lon are exactly 0 (likely missing)
    #     if v.position.latitude == 0.0 and v.position.longitude == 0.0:
    #         skipped += 1
    #         continue
    #
    #     vehicles.append({
    #         "id":        entity.id,
    #         "route_id":  v.trip.route_id  if v.HasField("trip")     else None,
    #         "trip_id":   v.trip.trip_id   if v.HasField("trip")     else None,
    #         "lat":       v.position.latitude,
    #         "lon":       v.position.longitude,
    #         # bearing and speed are optional scalars — default 0.0 if not set
    #         "bearing":   v.position.bearing if v.position.bearing  else None,
    #         "speed_kmh": round(v.position.speed * 3.6, 1) if v.position.speed else None,
    #         "label":     v.vehicle.label or entity.id if v.HasField("vehicle") else entity.id,
    #         "timestamp": v.timestamp or None,
    #     })
    #
    # if skipped:
    #     logger.warning("Skipped %d vehicle entities with missing position", skipped)
    #
    # return vehicles

    logger.info("parse_vehicle_positions: returning empty list (not yet implemented)")
    return []


def parse_trip_updates(raw_bytes: bytes) -> list[dict]:
    """
    Decode TripUpdates protobuf feed → list of trip delay dicts.

    Each dict contains:
        trip_id, delay_seconds, is_realtime

    delay_seconds is taken from the first stop_time_update that has a departure delay.
    Falls back to arrival delay if departure is missing.
    """
    # TODO: replace with real implementation once package is installed
    # feed = gtfs_realtime_pb2.FeedMessage()
    # feed.ParseFromString(raw_bytes)
    #
    # delays = []
    # for entity in feed.entity:
    #     if not entity.HasField("trip_update"):
    #         continue
    #     tu = entity.trip_update
    #
    #     trip_id = tu.trip.trip_id if tu.HasField("trip") else None
    #     if not trip_id:
    #         continue
    #
    #     delay = 0
    #     for stu in tu.stop_time_update:
    #         if stu.HasField("departure") and stu.departure.HasField("delay"):
    #             delay = stu.departure.delay
    #             break
    #         elif stu.HasField("arrival") and stu.arrival.HasField("delay"):
    #             delay = stu.arrival.delay
    #             break
    #
    #     delays.append({"trip_id": trip_id, "delay_seconds": delay, "is_realtime": True})
    #
    # return delays

    logger.info("parse_trip_updates: returning empty list (not yet implemented)")
    return []


def parse_alerts(raw_bytes: bytes) -> list[dict]:
    """
    Decode Alerts protobuf feed → list of alert dicts.

    Each dict contains:
        id, header, description, effect, cause, route_ids

    route_ids is a list — one alert can affect multiple routes.
    An empty route_ids list means the alert is network-wide.
    """
    # TODO: replace with real implementation once package is installed
    # feed = gtfs_realtime_pb2.FeedMessage()
    # feed.ParseFromString(raw_bytes)
    #
    # alerts = []
    # for entity in feed.entity:
    #     if not entity.HasField("alert"):
    #         continue
    #     a = entity.alert
    #
    #     # Extract affected route IDs from informed_entity list
    #     route_ids = []
    #     for informed in a.informed_entity:
    #         if informed.route_id:
    #             route_ids.append(informed.route_id)
    #
    #     # Header and description are TranslatedStrings — take first translation
    #     header = ""
    #     if a.header_text.translation:
    #         header = a.header_text.translation[0].text
    #
    #     description = ""
    #     if a.description_text.translation:
    #         description = a.description_text.translation[0].text
    #
    #     alerts.append({
    #         "id":          entity.id,
    #         "header":      header,
    #         "description": description,
    #         "effect":      a.effect.name if a.effect else "UNKNOWN_EFFECT",
    #         "cause":       a.cause.name  if a.cause  else "UNKNOWN_CAUSE",
    #         "route_ids":   route_ids,
    #     })
    #
    # return alerts

    logger.info("parse_alerts: returning empty list (not yet implemented)")
    return []
