# Vehicle Tracker — Jyväskylä Public Transport

Real-time bus tracking for Jyväskylä using the Waltti GTFS-RT API and Digitransit route planner.

Built for TJTS5901 Continuous Software Engineering, University of Jyväskylä, 2026.

---

## Architecture overview

```
reference-frontend/   ← temporary UI (replaced by frontend team)
backend/
  app/               ← Application layer: FastAPI endpoints, WebSockets
  processing/        ← Processing layer: pure functions, models, business logic
  ingestion/         ← Ingestion layer: HTTP clients, protobuf parsing, Redis writes
  tests/             ← pytest unit tests
docs/
  system-design.html           ← course-appropriate design diagram
  system-design-reference.html ← production-grade reference design
  flow-diagram.html            ← request flow walkthrough
docker-compose.yml
.env.example
```

**Three services:**

| Service  | What it does |
|----------|-------------|
| `redis`  | Cache + Pub/Sub message bus |
| `fastapi`| Serves HTTP endpoints + WebSocket connections |
| `worker` | Polls Waltti GTFS-RT every 30 s, writes to Redis |

---

## Quick start (dummy mode — no API keys needed)

The app runs fully without API keys. All endpoints return realistic dummy data.

```bash
# 1. Clone and enter the project
cd vehicle-tracker

# 2. Copy and (optionally) edit env file
cp .env.example .env

# 3. Start everything
docker compose up --build

# 4. Open browser
open http://localhost:8000
```

---

## Local development (without Docker)

```bash
# Prerequisites: Python 3.12+, Redis running on localhost:6379

cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy env file to backend directory (config.py looks for .env here)
cp ../.env.example .env

# Terminal 1 — FastAPI
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Worker
python -m ingestion.worker
```

Open `http://localhost:8000` in your browser.

---

## Running tests

```bash
cd backend
pytest tests/ -v
```

All tests pass in dummy mode. Tests marked `pytest.skip` require real `.pb` fixture files — capture them by running the worker once with live API keys, then copy from `ingestion/` to `tests/fixtures/`.

---

## Enabling real data (once API keys are available)

1. Add your keys to `.env`:
   ```
   WALTTI_API_KEY=...
   DIGITRANSIT_API_KEY=...
   ```

2. Uncomment the real implementations (search for `# TODO: uncomment` in each file):
   - `ingestion/waltti_client.py` — real HTTP fetches
   - `ingestion/gtfs_parser.py` — protobuf decoding
   - `ingestion/digitransit_client.py` — real geocoding + route planning
   - `ingestion/worker.py` — `asyncio.gather` for concurrent feeds
   - `app/routes.py` — Redis-backed endpoints and WebSocket handler

3. Restart services: `docker compose up --build`

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Reference frontend |
| `GET`  | `/api/geocode?q=<query>` | Autocomplete locations |
| `POST` | `/api/plan` | Find transit routes between two points |
| `GET`  | `/api/alerts/{route_id}` | Active service alerts for a route |
| `GET`  | `/api/routes` | All known route IDs |
| `WS`   | `/ws/vehicles/{route_id}` | Live vehicle positions (push every 5 s) |

### WebSocket message shape

```json
{
  "route_id": "4",
  "vehicle_count": 3,
  "vehicles": [
    {
      "id": "v-4-1",
      "label": "601",
      "route_id": "4",
      "lat": 62.2416,
      "lon": 25.7209,
      "bearing": 45.0,
      "speed_kmh": 28.5,
      "delay_seconds": 0,
      "delay_label": "On time",
      "is_delay_realtime": false,
      "current_stop": null,
      "next_stop": null,
      "trip_id": "trip-4-morning"
    }
  ],
  "freshness": {
    "level": "LIVE",
    "age_seconds": 12.3,
    "label": "Live"
  }
}
```

---

## Project structure (detailed)

```
backend/
├── app/
│   ├── main.py            # FastAPI app, startup/shutdown, static file mount
│   ├── routes.py          # All endpoints + WebSocket handler
│   └── dependencies.py    # Redis connection dependency
├── processing/
│   ├── models.py          # Dataclasses: Vehicle, Route, Alert, etc.
│   ├── vehicle_service.py # filter_by_route, enrich_with_delays, compute_freshness
│   ├── route_planner.py   # parse_plan_response (Digitransit → PlanResult)
│   ├── geocoder.py        # parse_geocoding_response (Digitransit → list[Location])
│   └── alert_filter.py    # filter_by_route for ServiceAlert
├── ingestion/
│   ├── waltti_client.py   # fetch_vehicle_positions, fetch_trip_updates, fetch_alerts
│   ├── gtfs_parser.py     # parse_vehicle_positions, parse_trip_updates, parse_alerts
│   ├── digitransit_client.py # geocode, plan_route
│   ├── cache_writer.py    # write_vehicles, write_alerts, write_plan, write_geocode
│   └── worker.py          # Polling loop: fetch → parse → write Redis → publish
├── tests/
│   ├── fixtures/          # .pb binary fixtures (captured from live API)
│   ├── test_vehicle_service.py
│   ├── test_gtfs_parser.py
│   └── test_route_planner.py
├── config.py              # All settings from environment variables
├── requirements.txt
└── Dockerfile
```
# -vehicle-tracker-
