"""
Unit tests for processing/vehicle_service.py

Run:  cd backend && pytest tests/test_vehicle_service.py -v
"""
import time
import pytest
from processing.models import Vehicle, TripUpdate, FreshnessLevel
from processing import vehicle_service


def make_vehicle(id="v-1", route_id="4", trip_id="trip-1") -> Vehicle:
    return Vehicle(
        id=id, label="601", route_id=route_id,
        lat=62.24, lon=25.72, bearing=45.0, speed_kmh=30.0,
        trip_id=trip_id,
    )


# ── filter_by_route ───────────────────────────────────────────────────────────

def test_filter_by_route_returns_matching():
    vehicles = [make_vehicle("v1", "4"), make_vehicle("v2", "9"), make_vehicle("v3", "4")]
    result   = vehicle_service.filter_by_route(vehicles, "4")
    assert len(result) == 2
    assert all(v.route_id == "4" for v in result)


def test_filter_by_route_no_match_returns_empty():
    vehicles = [make_vehicle("v1", "4")]
    result   = vehicle_service.filter_by_route(vehicles, "99")
    assert result == []


def test_filter_by_route_empty_input():
    assert vehicle_service.filter_by_route([], "4") == []


# ── get_all_route_ids ─────────────────────────────────────────────────────────

def test_get_all_route_ids_returns_sorted_unique():
    vehicles = [make_vehicle(route_id="9"), make_vehicle(route_id="4"), make_vehicle(route_id="4")]
    result   = vehicle_service.get_all_route_ids(vehicles)
    assert result == ["4", "9"]


def test_get_all_route_ids_empty():
    assert vehicle_service.get_all_route_ids([]) == []


# ── enrich_with_updates ───────────────────────────────────────────────────────

def make_trip_update(trip_id="trip-1") -> TripUpdate:
    return TripUpdate(
        trip_id=trip_id,
        next_stop_id="207579",
        next_stop_arrival=1779014074,
        terminus_arrival=1779015364,
        stops_remaining=16,
    )


def test_enrich_adds_next_stop_when_trip_matches():
    vehicle = make_vehicle(trip_id="trip-1")
    result  = vehicle_service.enrich_with_updates([vehicle], [make_trip_update()])
    assert result[0].next_stop_id      == "207579"
    assert result[0].next_stop_arrival == 1779014074
    assert result[0].terminus_arrival  == 1779015364
    assert result[0].stops_remaining   == 16


def test_enrich_no_update_leaves_nones():
    vehicle = make_vehicle(trip_id="trip-1")
    result  = vehicle_service.enrich_with_updates([vehicle], [])
    assert result[0].next_stop_id      is None
    assert result[0].next_stop_arrival is None
    assert result[0].stops_remaining   is None


def test_enrich_vehicle_without_trip_id():
    vehicle = make_vehicle()
    vehicle.trip_id = None
    result  = vehicle_service.enrich_with_updates([vehicle], [make_trip_update()])
    assert result[0].next_stop_id is None


# ── enrich_with_updates — delay computation ───────────────────────────────────
#
# next_stop_arrival = 1779014074 → 13:34:34 local time
# scheduled_seconds = 13*3600 + 33*60 + 0 = 48780  (13:33:00)
# delay = (13*3600+34*60+34) − 48780 = 48874 − 48780 = 94 seconds late

def _next_stop_arrival_ts() -> int:
    """Unix timestamp for 13:34:34 on 2026-05-17 in local time."""
    return 1779014074   # known value from live feed sample


def _scheduled_secs() -> int:
    """13:33:00 expressed as seconds since midnight."""
    return 13 * 3600 + 33 * 60 + 0   # 48780


def test_enrich_computes_delay_when_schedule_available():
    """Delay = predicted arrival − scheduled arrival at next stop."""
    from datetime import datetime
    vehicle = make_vehicle(trip_id="trip-1")
    update  = TripUpdate(
        trip_id="trip-1",
        next_stop_id="207579",
        next_stop_arrival=_next_stop_arrival_ts(),
        terminus_arrival=1779015364,
        stops_remaining=16,
    )
    scheduled = {"trip-1": _scheduled_secs()}
    result    = vehicle_service.enrich_with_updates([vehicle], [update], scheduled)

    pred_dt   = datetime.fromtimestamp(_next_stop_arrival_ts())
    pred_secs = pred_dt.hour * 3600 + pred_dt.minute * 60 + pred_dt.second
    expected_delay = pred_secs - _scheduled_secs()

    assert result[0].is_delay_realtime is True
    assert result[0].delay_seconds     == expected_delay


def test_enrich_no_schedule_leaves_delay_defaults():
    """Without schedule data, delay fields stay at their defaults."""
    vehicle = make_vehicle(trip_id="trip-1")
    result  = vehicle_service.enrich_with_updates([vehicle], [make_trip_update()])
    assert result[0].is_delay_realtime is False
    assert result[0].delay_seconds     == 0


def test_enrich_early_bus_has_negative_delay():
    """A bus arriving before schedule has negative delay_seconds."""
    from datetime import datetime
    vehicle = make_vehicle(trip_id="trip-1")
    update  = TripUpdate(
        trip_id="trip-1",
        next_stop_id="207579",
        next_stop_arrival=_next_stop_arrival_ts(),
        terminus_arrival=1779015364,
        stops_remaining=16,
    )
    # Schedule says 13:40:00 — bus is actually early
    early_scheduled = 13 * 3600 + 40 * 60 + 0   # 49200
    result = vehicle_service.enrich_with_updates([vehicle], [update], {"trip-1": early_scheduled})

    assert result[0].is_delay_realtime is True
    assert result[0].delay_seconds     < 0   # early → negative


# ── compute_freshness ─────────────────────────────────────────────────────────

def test_freshness_live():
    freshness = vehicle_service.compute_freshness(time.time() - 10)
    assert freshness.level == FreshnessLevel.LIVE


def test_freshness_delayed():
    freshness = vehicle_service.compute_freshness(time.time() - 90)
    assert freshness.level == FreshnessLevel.DELAYED


def test_freshness_stale():
    freshness = vehicle_service.compute_freshness(time.time() - 300)
    assert freshness.level == FreshnessLevel.STALE


def test_freshness_zero_fetched_at():
    # fetched_at=0 means never fetched — should be STALE
    freshness = vehicle_service.compute_freshness(0)
    assert freshness.level == FreshnessLevel.STALE
