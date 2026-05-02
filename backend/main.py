"""
MVP REST API for bus tracking — wire DATABASE_URL when PostgreSQL is available.
Fallback: in-memory demo data when DB is unreachable (for quick local demos).
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP_ENV = os.getenv("APP_ENV", "dev")
API_TITLE = os.getenv("API_TITLE", "Haryana Roadways Tracking API")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
DRIVER_API_KEYS = {k.strip() for k in os.getenv("DRIVER_API_KEYS", "dev-driver-key").split(",") if k.strip()}
allow_any_origin = "*" in ALLOWED_ORIGINS

app = FastAPI(title=API_TITLE, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=not allow_any_origin,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- In-memory demo (used if no DB or for tests) ----------
_DEMO_ROUTES = [
    {
        "id": 1,
        "code": "HR-CHD-DLI",
        "name": "Chandigarh ISBT to Delhi ISBT",
        "direction": "southbound",
        "active": True,
        "stop_ids_in_order": [1, 2, 3, 4, 5],
    },
    {
        "id": 2,
        "code": "HR-HSR-GGN",
        "name": "Hisar to Gurugram",
        "direction": "eastbound",
        "active": True,
        "stop_ids_in_order": [6, 7, 8, 9],
    },
]
_DEMO_STOPS = {
    1: {"id": 1, "code": "CHD", "name": "Chandigarh ISBT", "lat": 30.7333, "lng": 76.7794},
    2: {"id": 2, "code": "KKR", "name": "Kurukshetra Bus Stand", "lat": 29.9695, "lng": 76.8783},
    3: {"id": 3, "code": "KRL", "name": "Karnal Bus Stand", "lat": 29.6857, "lng": 76.9905},
    4: {"id": 4, "code": "PPT", "name": "Panipat Depot", "lat": 29.3909, "lng": 76.9635},
    5: {"id": 5, "code": "DLI", "name": "Delhi ISBT Kashmere Gate", "lat": 28.6675, "lng": 77.2273},
    6: {"id": 6, "code": "HSR", "name": "Hisar Bus Stand", "lat": 29.1492, "lng": 75.7217},
    7: {"id": 7, "code": "BWN", "name": "Bhiwani Bus Stand", "lat": 28.7930, "lng": 76.1397},
    8: {"id": 8, "code": "RWR", "name": "Rewari Bus Stand", "lat": 28.1990, "lng": 76.6188},
    9: {"id": 9, "code": "GGN", "name": "Gurugram Bus Stand", "lat": 28.4595, "lng": 77.0266},
}
_DEMO_BUSES = {
    1: {
        "id": 1,
        "number_plate": "HR55AB1234",
        "route_id": 1,
        "capacity": 45,
        "active": True,
    },
    2: {
        "id": 2,
        "number_plate": "HR66XY9999",
        "route_id": 2,
        "capacity": 40,
        "active": True,
    },
}
_DEMO_LOCATIONS = {
    1: {"bus_id": 1, "lat": 29.9500, "lng": 76.9000, "speed_mps": 11.5, "heading_deg": 180.0, "delay_minutes": 4},
    2: {"bus_id": 2, "lat": 28.8200, "lng": 76.2000, "speed_mps": 9.0, "heading_deg": 100.0, "delay_minutes": 1},
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))


class LocationUpdate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    speed_mps: Optional[float] = Field(None, ge=0)
    heading_deg: Optional[float] = None
    delay_minutes: Optional[int] = Field(0, ge=0)


class RouteSearchRequest(BaseModel):
    from_stop: str = Field(..., min_length=1, description="Stop name/code, e.g. DLI")
    to_stop: str = Field(..., min_length=1, description="Stop name/code, e.g. SNP")


def require_driver_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if not DRIVER_API_KEYS:
        raise HTTPException(status_code=500, detail="Driver API keys not configured")
    if x_api_key not in DRIVER_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key for driver update")


def _stop_matches(stop: dict[str, Any], query: str) -> bool:
    ql = query.lower().strip()
    return ql in stop["name"].lower() or ql in str(stop.get("code", "")).lower()


def _find_stop_ids(query: str) -> list[int]:
    return [sid for sid, stop in _DEMO_STOPS.items() if _stop_matches(stop, query)]


def _get_route_by_id(route_id: int) -> Optional[dict[str, Any]]:
    return next((r for r in _DEMO_ROUTES if r["id"] == route_id), None)


def _segment_distance_km(stop_ids: list[int]) -> float:
    if len(stop_ids) < 2:
        return 0.0
    total = 0.0
    for i in range(len(stop_ids) - 1):
        a = _DEMO_STOPS[stop_ids[i]]
        b = _DEMO_STOPS[stop_ids[i + 1]]
        total += haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
    return total


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "env": APP_ENV}


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = str(duration_ms)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "path": str(request.url.path),
                "status_code": exc.status_code,
            }
        },
    )


@app.get("/buses")
def get_buses() -> list[dict[str, Any]]:
    return [{"id": b["id"], **{k: v for k, v in b.items() if k != "id"}} for b in _DEMO_BUSES.values()]


@app.get("/buses/{bus_id}")
def get_bus(bus_id: int) -> dict[str, Any]:
    b = _DEMO_BUSES.get(bus_id)
    if not b:
        raise HTTPException(404, "Bus not found")
    return dict(b)


@app.get("/routes/{route_id}")
def get_route(route_id: int) -> dict[str, Any]:
    route = next((r for r in _DEMO_ROUTES if r["id"] == route_id), None)
    if not route:
        raise HTTPException(404, "Route not found")
    stops = [_DEMO_STOPS[sid] for sid in route["stop_ids_in_order"] if sid in _DEMO_STOPS]
    return {"route": {k: v for k, v in route.items() if k != "stop_ids_in_order"}, "stops_in_order": stops}


@app.get("/buses/{bus_id}/live")
def get_live_location(bus_id: int) -> dict[str, Any]:
    loc = _DEMO_LOCATIONS.get(bus_id)
    if not loc:
        raise HTTPException(404, "Live location not found")
    ts = datetime.now(timezone.utc).isoformat()
    return {**loc, "server_time": ts}


@app.post("/buses/{bus_id}/location")
async def update_bus_location(
    bus_id: int, body: LocationUpdate, _: None = Depends(require_driver_key)
) -> dict[str, Any]:
    if bus_id not in _DEMO_BUSES:
        raise HTTPException(404, "Bus not found")
    _DEMO_LOCATIONS[bus_id] = {
        "bus_id": bus_id,
        "lat": body.lat,
        "lng": body.lng,
        "speed_mps": body.speed_mps or _DEMO_LOCATIONS.get(bus_id, {}).get("speed_mps"),
        "heading_deg": body.heading_deg if body.heading_deg is not None else _DEMO_LOCATIONS.get(bus_id, {}).get("heading_deg"),
        "delay_minutes": body.delay_minutes if body.delay_minutes is not None else _DEMO_LOCATIONS.get(bus_id, {}).get("delay_minutes", 0),
    }
    await ws_manager.broadcast(bus_id, {**_DEMO_LOCATIONS[bus_id], "server_time": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "bus_id": bus_id, "updated": _DEMO_LOCATIONS[bus_id]}


@app.get("/stops/{stop_id}/eta")
def get_eta(stop_id: int, route_id: int = Query(..., description="Route context for sequencing")) -> dict[str, Any]:
    if stop_id not in _DEMO_STOPS:
        raise HTTPException(404, "Stop not found")

    buses_on_route = [bid for bid, b in _DEMO_BUSES.items() if b.get("route_id") == route_id]
    candidates: list[dict[str, Any]] = []

    route = next((r for r in _DEMO_ROUTES if r["id"] == route_id), None)
    if not route or stop_id not in route["stop_ids_in_order"]:
        raise HTTPException(400, "Stop not on this route")

    goal = _DEMO_STOPS[stop_id]

    for bid in buses_on_route:
        loc = _DEMO_LOCATIONS.get(bid)
        if not loc:
            continue
        dist_km = haversine_km(loc["lat"], loc["lng"], goal["lat"], goal["lng"])
        speed_kmh = max((loc.get("speed_mps") or 7.0) * 3.6, 15.0)
        eta_min_basic = round((dist_km / speed_kmh) * 60, 1)
        delay = int(loc.get("delay_minutes") or 0)
        eta_min_adjusted = round(eta_min_basic + delay, 1)
        candidates.append(
            {"bus_id": bid, "eta_minutes": eta_min_adjusted, "straight_line_km": round(dist_km, 3)}
        )

    if not candidates:
        return {"stop_id": stop_id, "route_id": route_id, "etas": [], "note": "No live buses"}

    candidates.sort(key=lambda x: x["eta_minutes"])
    return {"stop_id": stop_id, "route_id": route_id, "etas": candidates}


@app.get("/search")
def search(q: str = Query("", min_length=1)) -> dict[str, list]:
    ql = q.lower()
    buses = [
        dict(b)
        for b in _DEMO_BUSES.values()
        if ql in str(b["number_plate"]).lower()
    ]
    routes = [r for r in _DEMO_ROUTES if ql in r["code"].lower() or ql in r["name"].lower()]
    stops = [s for s in _DEMO_STOPS.values() if ql in s["name"].lower() or (s.get("code") and ql in s["code"].lower())]
    return {"buses": buses, "routes": routes, "stops": stops}


@app.post("/routes/search")
def search_routes_between_stops(body: RouteSearchRequest) -> dict[str, Any]:
    from_ids = _find_stop_ids(body.from_stop)
    to_ids = _find_stop_ids(body.to_stop)
    if not from_ids or not to_ids:
        return {"matches": [], "message": "No matching stop(s) found"}

    matches: list[dict[str, Any]] = []
    for route in _DEMO_ROUTES:
        order = route["stop_ids_in_order"]
        for f_id in from_ids:
            if f_id not in order:
                continue
            for t_id in to_ids:
                if t_id not in order:
                    continue
                i, j = order.index(f_id), order.index(t_id)
                if i >= j:
                    continue
                segment_stops = [_DEMO_STOPS[sid] for sid in order[i : j + 1]]
                segment_ids = order[i : j + 1]
                distance_km = round(_segment_distance_km(segment_ids), 1)
                # Haryana highway average for planning.
                expected_time_min = max(10, round((distance_km / 42.0) * 60))
                live_buses = [b for b in _DEMO_BUSES.values() if b["route_id"] == route["id"]]
                nearest_eta_min: Optional[float] = None
                current_delay_min = 0
                if live_buses:
                    for bus in live_buses:
                        loc = _DEMO_LOCATIONS.get(bus["id"])
                        if not loc:
                            continue
                        to_goal = haversine_km(loc["lat"], loc["lng"], _DEMO_STOPS[t_id]["lat"], _DEMO_STOPS[t_id]["lng"])
                        speed_kmh = max((loc.get("speed_mps") or 8.0) * 3.6, 20.0)
                        eta = (to_goal / speed_kmh) * 60 + int(loc.get("delay_minutes") or 0)
                        if nearest_eta_min is None or eta < nearest_eta_min:
                            nearest_eta_min = round(eta, 1)
                            current_delay_min = int(loc.get("delay_minutes") or 0)
                matches.append(
                    {
                        "route": {k: v for k, v in route.items() if k != "stop_ids_in_order"},
                        "from_stop": _DEMO_STOPS[f_id],
                        "to_stop": _DEMO_STOPS[t_id],
                        "stops_count": len(segment_stops),
                        "distance_km": distance_km,
                        "expected_time_min": expected_time_min,
                        "live_delay_min": current_delay_min,
                        "nearest_bus_eta_min": nearest_eta_min,
                        "stops_between": segment_stops,
                    }
                )

    matches.sort(key=lambda x: (x["nearest_bus_eta_min"] is None, x["nearest_bus_eta_min"] or 9999))
    return {"matches": matches}


@app.get("/routes/{route_id}/timeline")
def route_timeline(route_id: int) -> dict[str, Any]:
    route = _get_route_by_id(route_id)
    if not route:
        raise HTTPException(404, "Route not found")

    # Approximate stop timings for MVP (every 6 mins from first stop).
    base_hour = 6
    timeline: list[dict[str, Any]] = []
    for idx, sid in enumerate(route["stop_ids_in_order"]):
        hour = base_hour + (idx * 6) // 60
        minute = (idx * 6) % 60
        timeline.append(
            {
                "stop": _DEMO_STOPS[sid],
                "scheduled_time": f"{hour:02d}:{minute:02d}",
            }
        )
    return {"route": {k: v for k, v in route.items() if k != "stop_ids_in_order"}, "timeline": timeline}


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, bus_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.active.setdefault(bus_id, []).append(ws)

    def disconnect(self, bus_id: int, ws: WebSocket) -> None:
        clients = self.active.get(bus_id, [])
        if ws in clients:
            clients.remove(ws)
        if not clients and bus_id in self.active:
            del self.active[bus_id]

    async def broadcast(self, bus_id: int, payload: dict[str, Any]) -> None:
        clients = self.active.get(bus_id, [])
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(bus_id, ws)


ws_manager = ConnectionManager()


@app.websocket("/ws/buses/{bus_id}/live")
async def ws_bus_live(bus_id: int, ws: WebSocket) -> None:
    if bus_id not in _DEMO_BUSES:
        await ws.close(code=1008)
        return

    await ws_manager.connect(bus_id, ws)
    try:
        # Send initial snapshot.
        if bus_id in _DEMO_LOCATIONS:
            await ws.send_json({**_DEMO_LOCATIONS[bus_id], "server_time": datetime.now(timezone.utc).isoformat()})
        while True:
            # Keep socket alive; client can send ping text, ignored here.
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(bus_id, ws)
