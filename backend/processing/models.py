from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ── Freshness ─────────────────────────────────────────────────────────────────

class FreshnessLevel(str, Enum):
    LIVE    = "LIVE"     # data age < 60s
    DELAYED = "DELAYED"  # data age 60–120s
    STALE   = "STALE"    # data age > 120s


@dataclass
class FreshnessStatus:
    level:       FreshnessLevel
    age_seconds: int
    label:       str              # e.g. "Live · updated 12s ago"


# ── Geocoding ─────────────────────────────────────────────────────────────────

@dataclass
class Location:
    name: str
    lat:  float
    lon:  float
    type: str             # "stop" | "station" | "address" | "place"
    id:   Optional[str] = None


# ── Vehicle positions (from Waltti GTFS-RT VehiclePositions feed) ─────────────

@dataclass
class Vehicle:
    id:                 str
    label:              str             # bus number shown to driver/public
    route_id:           str
    lat:                float
    lon:                float
    bearing:            Optional[float]  # degrees 0–360, None if not reported
    speed_kmh:          Optional[float]  # None if not reported
    trip_id:            Optional[str]
    delay_seconds:      int  = 0         # enriched from TripUpdates feed
    is_delay_realtime:  bool = False     # False = no TripUpdate found for this vehicle
    current_stop:       Optional[str] = None
    next_stop:          Optional[str] = None
    timestamp:          Optional[int] = None   # Unix time of GPS reading

    @property
    def delay_label(self) -> str:
        if not self.is_delay_realtime:
            return "No delay data"
        if abs(self.delay_seconds) < 60:
            return "On time"
        mins = abs(self.delay_seconds) // 60
        return f"{mins} min late" if self.delay_seconds > 0 else f"{mins} min early"


# ── Trip delays (from Waltti GTFS-RT TripUpdates feed) ───────────────────────

@dataclass
class TripDelay:
    trip_id:        str
    delay_seconds:  int
    is_realtime:    bool


# ── Service alerts (from Waltti GTFS-RT Alerts feed) ─────────────────────────

@dataclass
class ServiceAlert:
    id:          str
    header:      str
    description: str
    effect:      str          # "NO_SERVICE" | "REDUCED_SERVICE" | "DETOUR" | "OTHER"
    cause:       str          # "CONSTRUCTION" | "ACCIDENT" | "MAINTENANCE" | "OTHER"
    route_ids:   list[str] = field(default_factory=list)


# ── Route planning (from Digitransit API) ─────────────────────────────────────

@dataclass
class RouteLeg:
    mode:             str           # "WALK" | "BUS" | "TRAM"
    route_id:         Optional[str]
    route_name:       Optional[str]
    from_name:        str
    to_name:          str
    departure_time:   str           # "14:32"
    arrival_time:     str           # "14:45"
    duration_minutes: int
    distance_meters:  float
    geometry:         list = field(default_factory=list)  # [[lat, lon], ...] decoded from legGeometry


@dataclass
class Route:
    route_id:           str
    route_name:         str
    departure_time:     str
    arrival_time:       str
    duration_minutes:   int
    walk_distance_meters: float = 0.0
    legs:               list[RouteLeg] = field(default_factory=list)


@dataclass
class PlanResult:
    routes:        list[Route]
    from_location: Location
    to_location:   Location
    is_stale:      bool         = False   # True if served from expired cache
    error:         Optional[str] = None   # set when Digitransit failed
