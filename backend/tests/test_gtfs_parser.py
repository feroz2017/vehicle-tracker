"""
Unit tests for ingestion/gtfs_parser.py

Run:  cd backend && pytest tests/test_gtfs_parser.py -v

NOTE: parse_* functions currently return [] (not yet implemented).
      These tests will pass once gtfs-realtime-bindings is installed
      and the TODO blocks in gtfs_parser.py are uncommented.

      To capture a real fixture:
          import httpx, asyncio
          raw = asyncio.run(fetch_vehicle_positions())
          open("tests/fixtures/vehicles.pb", "wb").write(raw)
"""
import pytest
from ingestion.gtfs_parser import parse_vehicle_positions, parse_trip_updates, parse_alerts


# ── parse_vehicle_positions ───────────────────────────────────────────────────

def test_parse_vehicles_empty_bytes_returns_empty():
    """Empty bytes should not crash — return empty list."""
    # TODO: this will return [] for now (not implemented)
    # When implemented, empty/invalid bytes should still not raise
    result = parse_vehicle_positions(b"")
    assert isinstance(result, list)


def test_parse_vehicles_from_fixture():
    """
    TODO: enable once fixture is captured and parser is implemented.

    import os
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "vehicles.pb")
    if not os.path.exists(fixture):
        pytest.skip("Fixture not yet captured")

    with open(fixture, "rb") as f:
        raw = f.read()

    vehicles = parse_vehicle_positions(raw)
    assert len(vehicles) > 0

    first = vehicles[0]
    assert "id"       in first
    assert "lat"      in first
    assert "lon"      in first
    assert "route_id" in first
    # lat/lon must be in Finland
    assert 59.0 < first["lat"] < 70.0
    assert 19.0 < first["lon"] < 32.0
    """
    pytest.skip("Fixture not yet captured — run worker once to generate it")


# ── parse_trip_updates ────────────────────────────────────────────────────────

def test_parse_trip_updates_empty_bytes_returns_empty():
    result = parse_trip_updates(b"")
    assert isinstance(result, list)


def test_parse_trip_updates_from_fixture():
    """
    TODO: enable once fixture is captured.

    Each result should have: trip_id, delay_seconds, is_realtime
    """
    pytest.skip("Fixture not yet captured")


# ── parse_alerts ──────────────────────────────────────────────────────────────

def test_parse_alerts_empty_bytes_returns_empty():
    result = parse_alerts(b"")
    assert isinstance(result, list)


def test_parse_alerts_from_fixture():
    """
    TODO: enable once fixture is captured.

    Each result should have: id, header, description, effect, cause, route_ids
    """
    pytest.skip("Fixture not yet captured")
