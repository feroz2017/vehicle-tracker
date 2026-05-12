"""
Unit tests for processing/vehicle_service.py

Run:  cd backend && pytest tests/test_vehicle_service.py -v
"""
import time
import pytest
from processing.models import Vehicle, TripDelay, FreshnessLevel
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


# ── enrich_with_delays ────────────────────────────────────────────────────────

def test_enrich_adds_delay_when_trip_matches():
    vehicle = make_vehicle(trip_id="trip-1")
    delays  = [TripDelay(trip_id="trip-1", delay_seconds=120, is_realtime=True)]
    result  = vehicle_service.enrich_with_delays([vehicle], delays)
    assert result[0].delay_seconds     == 120
    assert result[0].is_delay_realtime is True


def test_enrich_no_update_leaves_zero_delay():
    vehicle = make_vehicle(trip_id="trip-1")
    result  = vehicle_service.enrich_with_delays([vehicle], [])
    assert result[0].delay_seconds     == 0
    assert result[0].is_delay_realtime is False


def test_enrich_vehicle_without_trip_id():
    vehicle = make_vehicle()
    vehicle.trip_id = None
    delays  = [TripDelay(trip_id="trip-1", delay_seconds=60, is_realtime=True)]
    result  = vehicle_service.enrich_with_delays([vehicle], delays)
    assert result[0].delay_seconds == 0


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
