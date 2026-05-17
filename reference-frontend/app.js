/* ════════════════════════════════════════════════════════════════════════════
   app.js — Vehicle Tracker reference frontend
   This file will be replaced by the frontend team.
   ════════════════════════════════════════════════════════════════════════════ */

const API_BASE    = "";       // same origin — FastAPI serves this file
const DEBOUNCE_MS = 400;      // geocode debounce delay
const WS_RETRY_MS = 5000;     // WebSocket reconnect interval

// ── State ─────────────────────────────────────────────────────────────────────
let map, markers = {}, selectedRoute = null, ws = null;
let fromLocation = null, toLocation = null;
let routeLines = [];         // active Leaflet polylines for the selected route
let routesData = [];         // full route objects from last /api/plan response
let userLocation = null;     // saved GPS fix — restored after clearSearch()
let userMarker   = null;     // blue "you are here" circle on the map
let selectedRouteName = null; // short name of the active route, e.g. "S3"

// ── Init map ──────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  map = L.map("map").setView([62.2416, 25.7209], 13);  // Jyväskylä city centre
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
  }).addTo(map);

  // Enter key triggers search from either input
  document.getElementById("input-from").addEventListener("keydown", e => { if (e.key === "Enter") search(); });
  document.getElementById("input-to").addEventListener("keydown",   e => { if (e.key === "Enter") search(); });

  // Geocode on input (debounced)
  document.getElementById("input-from").addEventListener("input", () => onInput("from"));
  document.getElementById("input-to").addEventListener("input",   () => onInput("to"));

  // Auto-fill "From" with the user's current position if the browser allows it
  requestUserLocation();
});

// ── User geolocation ──────────────────────────────────────────────────────────
function requestUserLocation() {
  if (!navigator.geolocation) return;   // browser doesn't support it — silent skip

  navigator.geolocation.getCurrentPosition(
    pos => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;

      userLocation = { name: "My Location", lat, lon, type: "place" };
      fromLocation = userLocation;
      document.getElementById("input-from").value = "My Location";

      // Pan to the user and zoom in slightly
      map.setView([lat, lon], 14);

      // Blue pulsing dot so the user can see where "My Location" is
      if (userMarker) map.removeLayer(userMarker);
      userMarker = L.circleMarker([lat, lon], {
        radius:      9,
        color:       "#1d4ed8",
        fillColor:   "#3b82f6",
        fillOpacity: 0.85,
        weight:      2,
      }).bindPopup("You are here").addTo(map);
    },
    err => {
      // Permission denied or timeout — the user can still type an address manually
      console.info("Geolocation unavailable:", err.message);
    },
    { timeout: 10000, maximumAge: 60000 },
  );
}

// ── Geocoding (debounced) ─────────────────────────────────────────────────────
let debounceTimer = null;

function onInput(field) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => fetchSuggestions(field), DEBOUNCE_MS);
}

async function fetchSuggestions(field) {
  const input = document.getElementById(`input-${field}`);
  const list  = document.getElementById(`suggestions-${field}`);
  const q     = input.value.trim();

  if (q.length < 2) { list.classList.add("hidden"); return; }

  try {
    const res  = await fetch(`${API_BASE}/api/geocode?q=${encodeURIComponent(q)}`);
    const data = await res.json();

    list.innerHTML = "";

    if (!data || data.length === 0) {
      const li = document.createElement("li");
      li.className   = "no-results";
      li.textContent = "No locations found";
      list.appendChild(li);
      list.classList.remove("hidden");
      return;
    }

    data.forEach(loc => {
      const li = document.createElement("li");
      li.textContent = loc.name;
      li.onclick = () => selectLocation(field, loc);
      list.appendChild(li);
    });

    list.classList.remove("hidden");
  } catch (e) {
    console.error("Geocode error:", e);
  }
}

function selectLocation(field, loc) {
  document.getElementById(`input-${field}`).value = loc.name;
  document.getElementById(`suggestions-${field}`).classList.add("hidden");
  if (field === "from") fromLocation = loc;
  else                  toLocation   = loc;
}

// Hide suggestions when clicking outside
document.addEventListener("click", e => {
  if (!e.target.closest(".search-field")) {
    document.querySelectorAll(".suggestions").forEach(el => el.classList.add("hidden"));
  }
});

// ── Search ────────────────────────────────────────────────────────────────────
async function search() {
  if (!fromLocation || !toLocation) {
    showError("Please select both a starting point and a destination from the suggestions.");
    return;
  }

  showLoading(true);
  hideError();
  document.getElementById("routes-panel").classList.add("hidden");
  closeWebSocket();
  clearMarkers();
  clearRouteLines();
  document.getElementById("status-bar").classList.add("hidden");
  document.getElementById("empty-state").classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/api/plan`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        from_lat:  fromLocation.lat,
        from_lon:  fromLocation.lon,
        to_lat:    toLocation.lat,
        to_lon:    toLocation.lon,
        from_name: fromLocation.name,
        to_name:   toLocation.name,
      }),
    });

    const data = await res.json();

    if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);

    if (!data.routes || data.routes.length === 0) {
      showError("No routes found between these two locations.");
      return;
    }

    routesData = data.routes;
    renderRoutes(data.routes);
  } catch (e) {
    showError("Could not find routes. " + e.message);
  } finally {
    showLoading(false);
  }
}

// ── Clear search ──────────────────────────────────────────────────────────────
function clearSearch() {
  closeWebSocket();
  clearMarkers();
  clearRouteLines();
  toLocation = selectedRoute = null;
  selectedRouteName = null;
  routesData = [];

  // Restore the GPS "From" if we have one, otherwise clear the input
  if (userLocation) {
    fromLocation = userLocation;
    document.getElementById("input-from").value = "My Location";
  } else {
    fromLocation = null;
    document.getElementById("input-from").value = "";
  }

  document.getElementById("input-to").value   = "";
  document.getElementById("routes-panel").classList.add("hidden");
  document.getElementById("status-bar").classList.add("hidden");
  document.getElementById("alert-banner").classList.add("hidden");
  document.getElementById("empty-state").classList.add("hidden");
  hideError();
}

// ── Render route cards ────────────────────────────────────────────────────────
function renderRoutes(routes) {
  const panel = document.getElementById("routes-panel");
  const list  = document.getElementById("routes-list");
  list.innerHTML = "";

  routes.forEach(route => {
    const card = document.createElement("div");
    card.className       = "route-card";
    card.dataset.routeId = route.route_id;

    const legSummary = buildLegSummary(route.legs);
    const walkLabel  = route.walk_distance_meters
      ? `${Math.round(route.walk_distance_meters)}m walk`
      : "";

    card.innerHTML = `
      <span class="route-badge">${route.route_name || route.route_id}</span>
      <div class="route-card-body">
        <div class="route-leg-summary">${legSummary}</div>
        <div class="route-time">
          ${route.departure_time} → ${route.arrival_time}
          &nbsp;·&nbsp; ${route.duration_minutes} min
          ${walkLabel ? `&nbsp;·&nbsp; ${walkLabel}` : ""}
        </div>
      </div>
    `;
    card.onclick = () => selectRoute(route.route_id, card);
    list.appendChild(card);
  });

  panel.classList.remove("hidden");
}

function buildLegSummary(legs) {
  if (!legs || legs.length === 0) return "";
  return legs
    .map(leg => leg.mode === "WALK"
      ? `Walk${leg.duration_minutes ? " " + leg.duration_minutes + " min" : ""}`
      : `Bus ${leg.route_name || leg.route_id}`)
    .join(" → ");
}

// ── Select route → open WebSocket ────────────────────────────────────────────
function selectRoute(routeId, card) {
  document.querySelectorAll(".route-card").forEach(c => c.classList.remove("active"));
  card.classList.add("active");

  closeWebSocket();
  clearMarkers();
  clearRouteLines();
  selectedRoute     = routeId;
  selectedRouteName = null;   // will be set below once we find the route object

  // Draw the route geometry for this route
  const route = routesData.find(r => r.route_id === routeId);
  if (route) {
    selectedRouteName = route.route_name || routeId;
    drawRoute(route);
  }

  document.getElementById("status-bar").classList.remove("hidden");
  document.getElementById("empty-state").classList.remove("hidden");

  // Show "Connecting…" immediately so the user sees feedback
  const badge = document.getElementById("freshness-badge");
  badge.className   = "badge badge-stale";
  badge.textContent = "Connecting…";
  document.getElementById("vehicle-count").textContent = "";

  fetchAlerts(routeId);
  openWebSocket(routeId);
}

function closeWebSocket() {
  if (ws) {
    ws.onclose = null;  // prevent auto-reconnect on intentional close
    ws.close();
    ws = null;
  }
}

function openWebSocket(routeId) {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${location.host}/ws/vehicles/${routeId}`);

  ws.onopen = () => console.log(`WS opened: route=${routeId}`);

  ws.onmessage = event => {
    const data = JSON.parse(event.data);
    updateFreshness(data.freshness);
    updateMarkers(data.vehicles || []);
    updateVehicleCount(data.vehicle_count || 0);
    document.getElementById("empty-state")
      .classList.toggle("hidden", (data.vehicle_count || 0) > 0);
  };

  ws.onerror = () => {
    showError("Live connection error. Reconnecting in 5s…");
  };

  ws.onclose = () => {
    console.log(`WS closed: route=${routeId}, retrying in ${WS_RETRY_MS}ms`);
    setTimeout(() => {
      if (selectedRoute === routeId) openWebSocket(routeId);
    }, WS_RETRY_MS);
  };
}

// ── Road-following bus animation ──────────────────────────────────────────────
//
// Strategy:
//   1. When a vehicle update arrives we know its GPS position and speed.
//   2. We fetch the trip's full road shape from /api/shape/{trip_id} once
//      and cache it in `shapeCache`.
//   3. We find the closest shape point to the reported GPS position.
//   4. Using the reported speed we compute how far the bus will travel in the
//      next ~30 s (the worker cycle) and build a path of shape points ahead.
//   5. A requestAnimationFrame loop walks the marker along those shape points
//      so it follows the road exactly instead of cutting across in a straight
//      line.
//
// If shape data is unavailable we fall back to placing the marker directly at
// the GPS coordinates (same behaviour as before, no animation).

const shapeCache = {};   // trip_id → [[lat,lon],...]  (fetched once, cached forever)
const animState  = {};   // vehicle_id → { marker, path, pathIdx, lastTs, mPerMs, bearing }

async function _fetchShape(tripId) {
  if (!tripId) return null;
  if (shapeCache[tripId] !== undefined) return shapeCache[tripId];
  shapeCache[tripId] = null;   // mark as "in-flight" to avoid duplicate requests
  try {
    const res  = await fetch(`${API_BASE}/api/shape/${encodeURIComponent(tripId)}`);
    const data = await res.json();
    shapeCache[tripId] = (data.points && data.points.length > 1) ? data.points : null;
  } catch (e) {
    console.warn("Shape fetch failed:", tripId, e);
    shapeCache[tripId] = null;
  }
  return shapeCache[tripId];
}

// Squared distance between two [lat,lon] pairs — cheap proxy for "closest point"
function _dist2(a, b) {
  const dlat = a[0] - b[0], dlon = a[1] - b[1];
  return dlat * dlat + dlon * dlon;
}

// Find index of the shape point closest to [lat, lon]
function _closestIdx(shape, lat, lon) {
  let best = 0, bestD = Infinity;
  const pt = [lat, lon];
  for (let i = 0; i < shape.length; i++) {
    const d = _dist2(shape[i], pt);
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

// Haversine distance in metres between two [lat,lon] pairs
function _haversine(a, b) {
  const R  = 6371000;
  const φ1 = a[0] * Math.PI / 180, φ2 = b[0] * Math.PI / 180;
  const Δφ = (b[0] - a[0]) * Math.PI / 180;
  const Δλ = (b[1] - a[1]) * Math.PI / 180;
  const s  = Math.sin(Δφ / 2), c = Math.sin(Δλ / 2);
  const x  = s * s + Math.cos(φ1) * Math.cos(φ2) * c * c;
  return 2 * R * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}

// Build an array of waypoints along `shape` starting from `startIdx` covering
// at least `targetMeters` of road distance.  Returns [] if shape is too short.
function _pathAhead(shape, startIdx, targetMeters) {
  const path = [shape[startIdx]];
  let dist = 0;
  for (let i = startIdx + 1; i < shape.length; i++) {
    dist += _haversine(shape[i - 1], shape[i]);
    path.push(shape[i]);
    if (dist >= targetMeters) break;
  }
  return path.length > 1 ? path : [];
}

// Bearing in degrees from point a to point b
function _bearing(a, b) {
  const φ1 = a[0] * Math.PI / 180, φ2 = b[0] * Math.PI / 180;
  const Δλ = (b[1] - a[1]) * Math.PI / 180;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

// rAF loop — runs for every tracked vehicle independently
function _tickVehicle(vid, ts) {
  const s = animState[vid];
  if (!s || !s.marker || s.path.length < 2) return;

  const elapsed = ts - s.lastTs;     // ms since last rAF
  s.lastTs = ts;
  s.travelled += elapsed * s.mPerMs; // metres along the path so far

  // Walk through path segments until we've consumed `travelled` metres
  while (s.segIdx < s.path.length - 1) {
    const segLen = _haversine(s.path[s.segIdx], s.path[s.segIdx + 1]);
    if (s.travelled <= segLen) break;
    s.travelled -= segLen;
    s.segIdx++;
  }

  if (s.segIdx >= s.path.length - 1) {
    // Reached the end of our projected path — hold at last point
    s.marker.setLatLng(s.path[s.path.length - 1]);
    return;   // don't schedule another frame; next WS update will restart
  }

  // Interpolate between current and next shape point
  const a   = s.path[s.segIdx];
  const b   = s.path[s.segIdx + 1];
  const seg = _haversine(a, b);
  const t   = seg > 0 ? Math.min(s.travelled / seg, 1) : 0;
  const lat = a[0] + t * (b[0] - a[0]);
  const lon = a[1] + t * (b[1] - a[1]);

  s.marker.setLatLng([lat, lon]);

  // Update icon bearing from road direction (only if colour bucket unchanged)
  const roadBearing = _bearing(a, b);
  const prev = s.marker.options._delayBucket;
  const next = _delayBucket(s.delaySeconds, s.isDelayRealtime);
  if (prev !== next) {
    s.marker.setIcon(buildBusIcon(roadBearing, s.delaySeconds, s.isDelayRealtime, s.routeName));
    s.marker.options._delayBucket = next;
  } else if (Math.abs(roadBearing - (s.lastBearing || 0)) > 5) {
    // Bearing changed enough to be visible — rebuild icon
    s.marker.setIcon(buildBusIcon(roadBearing, s.delaySeconds, s.isDelayRealtime, s.routeName));
    s.lastBearing = roadBearing;
  }

  s.rafId = requestAnimationFrame(t2 => _tickVehicle(vid, t2));
}

function _stopAnim(vid) {
  const s = animState[vid];
  if (s && s.rafId) { cancelAnimationFrame(s.rafId); s.rafId = null; }
}

async function updateMarkers(vehicles) {
  const seen = new Set();

  for (const v of vehicles) {
    seen.add(v.id);
    const popup = buildPopup(v);

    // ── create marker if new ──────────────────────────────────────────────
    if (!markers[v.id]) {
      const icon   = buildBusIcon(v.bearing, v.delay_seconds, v.is_delay_realtime, selectedRouteName);
      const marker = L.marker([v.lat, v.lon], { icon }).bindPopup(popup).addTo(map);
      marker.options._delayBucket = _delayBucket(v.delay_seconds, v.is_delay_realtime);
      markers[v.id] = marker;
    } else {
      markers[v.id].setPopupContent(popup);
    }

    const marker = markers[v.id];

    // ── try road-following animation ──────────────────────────────────────
    const shape = await _fetchShape(v.trip_id);

    if (shape) {
      _stopAnim(v.id);

      const startIdx     = _closestIdx(shape, v.lat, v.lon);
      const speedMps     = (v.speed_kmh || 30) / 3.6;   // default 30 km/h when unknown
      const targetMeters = speedMps * 30;                // distance in one 30s cycle
      const path         = _pathAhead(shape, startIdx, targetMeters);

      if (path.length >= 2) {
        // Place marker exactly at the GPS-reported position to start
        marker.setLatLng([v.lat, v.lon]);
        animState[v.id] = {
          marker,
          path,
          segIdx:           0,
          travelled:        0,
          mPerMs:           speedMps / 1000,
          lastTs:           performance.now(),
          delaySeconds:     v.delay_seconds || 0,
          isDelayRealtime:  v.is_delay_realtime || false,
          lastBearing:      v.bearing || 0,
          routeName:        selectedRouteName,
        };
        animState[v.id].rafId = requestAnimationFrame(ts => _tickVehicle(v.id, ts));
        continue;   // skip plain setLatLng below
      }
    }

    // ── fallback: plain marker placement (no shape available yet) ─────────
    marker.setLatLng([v.lat, v.lon]);
    const prev = marker.options._delayBucket;
    const next = _delayBucket(v.delay_seconds, v.is_delay_realtime);
    if (prev !== next) {
      marker.setIcon(buildBusIcon(v.bearing, v.delay_seconds, v.is_delay_realtime, selectedRouteName));
      marker.options._delayBucket = next;
    }
  }

  // Remove markers for buses no longer in the feed
  Object.keys(markers).forEach(id => {
    if (!seen.has(id)) {
      _stopAnim(id);
      delete animState[id];
      map.removeLayer(markers[id]);
      delete markers[id];
    }
  });
}

// Returns 0 / 1 / 2 / 3 — used to detect colour changes without icon rebuild
// 0=on-time(green)  1=slightly-late(amber)  2=very-late(red)  3=unknown(grey)
function _delayBucket(delaySeconds, isDelayRealtime) {
  if (!isDelayRealtime) return 3;
  const d = delaySeconds || 0;
  return d > 180 ? 2 : d > 60 ? 1 : 0;
}

function buildBusIcon(bearing, delaySeconds, isDelayRealtime, routeName) {
  const delay = delaySeconds || 0;
  const color = !isDelayRealtime ? "#9ca3af"   // grey  — no delay data
              : delay > 180      ? "#ef4444"   // red   — very late
              : delay > 60       ? "#f59e0b"   // amber — slightly late
              :                    "#22c55e";  // green — on time

  // Show the route short name (e.g. "S3") instead of a directional arrow.
  // Rotation is intentionally omitted: spinning text is illegible on the map.
  const label    = routeName || "?";
  const fontSize = label.length > 3 ? "9px" : "11px";  // shrink for long names

  return L.divIcon({
    className: "",
    html: `<div style="
      width:32px;height:32px;border-radius:50%;
      background:${color};border:2px solid white;
      display:flex;align-items:center;justify-content:center;
      color:white;font-size:${fontSize};font-weight:700;
      box-shadow:0 2px 6px rgba(0,0,0,.3);
      letter-spacing:-0.5px;">${label}</div>`,
    iconSize:   [32, 32],
    iconAnchor: [16, 16],
  });
}

function buildPopup(v) {
  const stops = (v.current_stop || v.next_stop)
    ? `<div style="color:#666;margin-bottom:4px">${v.current_stop || "—"} → ${v.next_stop || "—"}</div>`
    : "";

  return `
    <div style="min-width:180px;font-size:12px;">
      <strong>Route ${v.route_id} — Bus ${v.label || v.id}</strong>
      ${stops}
      <hr style="margin:6px 0;border:none;border-top:1px solid #eee;">
      <table style="width:100%">
        <tr><td style="color:#888">Delay</td><td><strong>${v.delay_label || "Unknown"}</strong></td></tr>
        <tr><td style="color:#888">Speed</td><td>${v.speed_kmh != null ? v.speed_kmh + " km/h" : "—"}</td></tr>
      </table>
    </div>`;
}

function clearMarkers() {
  Object.keys(markers).forEach(id => {
    _stopAnim(id);
    delete animState[id];
    map.removeLayer(markers[id]);
  });
  markers = {};
}

// ── Route polylines ───────────────────────────────────────────────────────────
function drawRoute(route) {
  const bounds = [];

  (route.legs || []).forEach(leg => {
    if (!leg.geometry || leg.geometry.length < 2) return;

    const isWalk = leg.mode === "WALK";
    const line = L.polyline(leg.geometry, {
      color:     isWalk ? "#9ca3af" : "#2563eb",
      weight:    isWalk ? 3 : 5,
      opacity:   isWalk ? 0.6 : 0.85,
      dashArray: isWalk ? "6 8" : null,
      lineJoin:  "round",
    }).addTo(map);

    routeLines.push(line);
    bounds.push(...leg.geometry);
  });

  // Fit the map to show the full route
  if (bounds.length > 0) {
    map.fitBounds(L.latLngBounds(bounds), { padding: [40, 40] });
  }
}

function clearRouteLines() {
  routeLines.forEach(l => map.removeLayer(l));
  routeLines = [];
}

// ── Alerts ────────────────────────────────────────────────────────────────────
async function fetchAlerts(routeId) {
  try {
    const res    = await fetch(`${API_BASE}/api/alerts/${routeId}`);
    const alerts = await res.json();
    const banner = document.getElementById("alert-banner");

    if (!alerts || alerts.length === 0) {
      banner.classList.add("hidden");
    } else {
      banner.innerHTML = alerts
        .map(a => `<strong>${a.effect}:</strong> ${a.header}`)
        .join(" &nbsp;·&nbsp; ");
      banner.classList.remove("hidden");
    }
  } catch (e) {
    console.error("Alerts fetch error:", e);
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function updateFreshness(freshness) {
  if (!freshness) return;
  const badge = document.getElementById("freshness-badge");
  const cls   = { LIVE: "badge-live", DELAYED: "badge-delayed", STALE: "badge-stale" };
  badge.className   = `badge ${cls[freshness.level] || "badge-stale"}`;
  badge.textContent = freshness.label;
}

function updateVehicleCount(count) {
  document.getElementById("vehicle-count").textContent =
    `${count} bus${count !== 1 ? "es" : ""}`;
}

function showLoading(visible) {
  document.getElementById("loading").classList.toggle("hidden", !visible);
  document.getElementById("btn-search").disabled = visible;
}

function showError(msg) {
  const box = document.getElementById("error-box");
  box.textContent = msg;
  box.classList.remove("hidden");
}

function hideError() {
  document.getElementById("error-box").classList.add("hidden");
}
