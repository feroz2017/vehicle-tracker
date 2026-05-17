# TODO — Vehicle Tracker

Things understood but not implemented yet. Do these later.

---

## 1. Show next stop and arrival time on bus popup

We already fetch TripUpdate every 30s. The data is there, just not used.

Steps:
1. In `backend/ingestion/gtfs_parser.py` — `parse_trip_updates()`
   - Currently only looks for `delay` field (which Waltti never sends)
   - Also extract: `next_stop_id`, `next_stop_arrival_time` (first entry in stop_time_update)
   - Return these in the dict alongside trip_id

2. In `backend/processing/models.py` — `Vehicle` dataclass
   - Add fields: `next_stop_id: str | None`, `next_stop_arrival: int | None` (Unix timestamp)

3. In `backend/processing/vehicle_service.py` — `enrich_with_delays()`
   - Already joins vehicles + delays by trip_id
   - Also copy `next_stop_id` and `next_stop_arrival` onto the Vehicle

4. In `backend/ingestion/cache_writer.py` — `write_vehicles()`
   - Already serializes Vehicle to dict for Redis
   - Make sure new fields are included in serialization

5. In `reference-frontend/app.js` — `buildPopup(v)`
   - Compute `seconds_away = next_stop_arrival - Date.now() / 1000`
   - Show: "Next stop in 2 min 54 sec" in the popup

---

## 2. Show stops remaining and trip end time

Same TripUpdate data — last entry in stop_time_update is the terminus.

Steps:
1. In `parse_trip_updates()` — also extract:
   - `stops_remaining` = length of stop_time_update list
   - `terminus_arrival` = last entry's arrival.time (Unix timestamp)

2. Thread through models → vehicle_service → cache_writer (same as above)

3. In `buildPopup(v)`:
   - Show: "32 stops remaining"
   - Show: "Trip ends at 13:56"

---

## 3. Show license plate in popup

Already in the TripUpdate feed: `vehicle.license_plate = "IRV-865"`

Steps:
1. In `parse_trip_updates()` — extract `license_plate` from `entity.trip_update.vehicle`
2. Store on TripDelay or separate lookup dict keyed by vehicle_id
3. In `buildPopup(v)` — show plate next to bus label

---

## 4. Delay from static GTFS (hard — needs separate data source)

Waltti sends predicted absolute times, never delay offset seconds.
To show "5 min late" we need the ORIGINAL scheduled times to compare against.
Those are in the static GTFS ZIP (separate download, not the realtime feed).

Steps:
1. Download static GTFS ZIP from Waltti
   - URL: https://data.waltti.fi/jyvaskyla/api/ (check docs for static feed URL)
2. Parse stop_times.txt — scheduled arrival/departure per stop per trip
3. Load into Redis on startup (or a separate lookup table)
4. In vehicle_service.enrich_with_delays():
   - Compare predicted arrival vs scheduled arrival for next stop
   - delay = predicted - scheduled
5. Now `is_delay_realtime = True` and `delay_seconds` is a real value
6. Bus markers turn green/amber/red correctly
