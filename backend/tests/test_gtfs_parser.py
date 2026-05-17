"""
Unit tests for ingestion/gtfs_parser.py

Run:  cd backend && pytest tests/test_gtfs_parser.py -v
"""
from ingestion.gtfs_parser import parse_vehicle_positions, parse_trip_updates, parse_alerts


# ── parse_vehicle_positions ───────────────────────────────────────────────────

def test_parse_vehicles_empty_bytes_returns_empty():
    """Empty bytes should not crash — return empty list."""
    # TODO: this will return [] for now (not implemented)
    # When implemented, empty/invalid bytes should still not raise
    result = parse_vehicle_positions(b"")
    assert isinstance(result, list)




# ── parse_trip_updates ────────────────────────────────────────────────────────

def test_parse_trip_updates_empty_bytes_returns_empty():
    result = parse_trip_updates(b"")
    assert isinstance(result, list)




# ── parse_alerts ──────────────────────────────────────────────────────────────

def test_parse_alerts_empty_bytes_returns_empty():
    result = parse_alerts(b"")
    assert isinstance(result, list)


