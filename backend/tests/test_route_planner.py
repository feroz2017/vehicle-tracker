"""
Unit tests for processing/route_planner.py

Run:  cd backend && pytest tests/test_route_planner.py -v
"""
import pytest
from processing.models import Location
from processing.route_planner import parse_plan_response


FROM_LOC = Location("Station",    62.2415, 25.7187, "station")
TO_LOC   = Location("University", 62.2289, 25.7427, "place")


def make_itinerary(duration=1500, walk=300.0, legs=None):
    """Build a minimal Digitransit itinerary dict."""
    return {
        "duration":     duration,
        "walkDistance": walk,
        "legs": legs or [
            {
                "mode":      "WALK",
                "startTime": 1715000000000,
                "endTime":   1715000240000,
                "duration":  240,
                "distance":  300.0,
                "from": {"name": "Station"},
                "to":   {"name": "Bus stop A"},
                "route": None,
            },
            {
                "mode":      "BUS",
                "startTime": 1715000240000,
                "endTime":   1715001560000,
                "duration":  1320,
                "distance":  4200.0,
                "from": {"name": "Bus stop A"},
                "to":   {"name": "University stop"},
                "route": {"gtfsId": "LINKKI:4", "shortName": "4"},
            },
        ],
    }


def make_response(itineraries):
    return {"data": {"plan": {"itineraries": itineraries}}}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_parse_returns_plan_result():
    raw    = make_response([make_itinerary()])
    result = parse_plan_response(raw, FROM_LOC, TO_LOC)
    assert result.from_location == FROM_LOC
    assert result.to_location   == TO_LOC
    assert result.error is None


def test_parse_one_itinerary_returns_one_route():
    raw    = make_response([make_itinerary()])
    result = parse_plan_response(raw, FROM_LOC, TO_LOC)
    assert len(result.routes) == 1


def test_parse_multiple_itineraries():
    raw    = make_response([make_itinerary(), make_itinerary(duration=2000)])
    result = parse_plan_response(raw, FROM_LOC, TO_LOC)
    assert len(result.routes) == 2


def test_parse_empty_itineraries_returns_empty_routes():
    raw    = make_response([])
    result = parse_plan_response(raw, FROM_LOC, TO_LOC)
    assert result.routes == []


def test_parse_route_has_correct_legs():
    raw    = make_response([make_itinerary()])
    route  = parse_plan_response(raw, FROM_LOC, TO_LOC).routes[0]
    assert len(route.legs) == 2
    assert route.legs[0].mode == "WALK"
    assert route.legs[1].mode == "BUS"


def test_parse_missing_route_field_in_leg():
    """Walk legs have no route — should not crash."""
    itinerary = make_itinerary(legs=[{
        "mode": "WALK", "startTime": 1715000000000, "endTime": 1715000240000,
        "duration": 240, "distance": 300.0,
        "from": {"name": "A"}, "to": {"name": "B"}, "route": None,
    }])
    raw    = make_response([itinerary])
    result = parse_plan_response(raw, FROM_LOC, TO_LOC)
    assert len(result.routes) == 1
