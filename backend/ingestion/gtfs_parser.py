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
    Decode TripUpdates protobuf feed → list of trip update dicts.

    Each dict contains:
        trip_id, next_stop_id, next_stop_arrival, stops_remaining, terminus_arrival

    Waltti sends absolute Unix timestamps only (arrival.time / departure.time).
    The `delay` field is not supported and never present — confirmed in Waltti docs.
    Delay computation requires the static GTFS schedule (see TODO.md item 4).

    The first entry in stop_time_update is always the next stop ahead of the bus
    (Waltti omits stops the bus has already passed).
    """
    if not raw_bytes:
        return []

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    updates = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update

        trip_id = tu.trip.trip_id if tu.HasField("trip") else None
        if not trip_id:
            continue

        stops = tu.stop_time_update
        if not stops:
            continue

        next_stop        = stops[0]
        last_stop        = stops[-1]

        next_stop_id      = next_stop.stop_id or None
        next_stop_arrival = next_stop.arrival.time  if next_stop.HasField("arrival")  else None
        terminus_arrival  = last_stop.arrival.time  if last_stop.HasField("arrival")  else None
        stops_remaining   = len(stops)

        updates.append({
            "trip_id":           trip_id,
            "next_stop_id":      next_stop_id,
            "next_stop_arrival": next_stop_arrival,
            "terminus_arrival":  terminus_arrival,
            "stops_remaining":   stops_remaining,
        })

    return updates


def parse_alerts(raw_bytes: bytes) -> list[dict]:
    """
    Decode Alerts protobuf feed → list of alert dicts.

    LINKKI alerts use stop_id (not route_id) in informed_entity, so route_ids
    will typically be empty. stop_ids is captured separately so the frontend
    can display location context. Alerts with no route_ids are treated as
    network-wide by cache_writer and returned for every route query.
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

        route_ids = [ie.route_id for ie in a.informed_entity if ie.route_id]
        stop_ids  = [ie.stop_id  for ie in a.informed_entity if ie.stop_id]

        header      = a.header_text.translation[0].text      if a.header_text.translation      else ""
        description = a.description_text.translation[0].text if a.description_text.translation else ""

        alerts.append({
            "id":          entity.id,
            "header":      header,
            "description": description,
            "effect":      gtfs_realtime_pb2.Alert.Effect.Name(a.effect) if a.effect else "UNKNOWN_EFFECT",
            "cause":       gtfs_realtime_pb2.Alert.Cause.Name(a.cause)   if a.cause  else "UNKNOWN_CAUSE",
            "route_ids":   route_ids,
            "stop_ids":    stop_ids,
        })

    return alerts
