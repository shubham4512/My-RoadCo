# Haryana Roadways Tracker (Commercial-ready Baseline)

A production-friendly bus tracking system inspired by "Where is My Train", adapted for Haryana Roadways:
- FastAPI backend
- PostgreSQL schema
- HTML + Leaflet frontend
- WebSocket live updates
- Driver update API key authentication
- Docker deployment baseline
- Request ID + response-time headers for observability

## 1) First-time setup (Windows)

Create your environment file:

```bash
copy .env.example .env
```

Edit `.env` and set a strong `DRIVER_API_KEYS` value.

## 2) Run backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open API docs: `http://127.0.0.1:8000/docs`

Quick one-click option:

```bash
run_backend.bat
```

## 3) Run frontend

Open `frontend/index.html` in browser.

## 4) Simulate moving buses

In another terminal:

```bash
cd backend
python simulate_driver.py --bus-id 1 --interval 3 --api-key dev-driver-key
```

Then click **Start live stream (WebSocket)** in frontend.

Run both simulators automatically:

```bash
run_simulators.bat
```

## 5) Import SQL schema

Use `sql/schema.sql` in PostgreSQL:

```sql
\i /absolute/path/to/sql/schema.sql
```

## 6) Key endpoints

- `GET /buses`
- `GET /buses/{id}`
- `GET /buses/{id}/live`
- `POST /buses/{id}/location` (requires `X-API-Key` header)
- `GET /routes/{id}`
- `GET /routes/{id}/timeline`
- `POST /routes/search` with `{ "from_stop": "Chandigarh", "to_stop": "Delhi" }`
- `GET /stops/{id}/eta?route_id=1`
- `GET /search?q=panipat`
- `GET /health/ready`
- `WS /ws/buses/{id}/live`

## Haryana sample data included

- Chandigarh ISBT -> Kurukshetra -> Karnal -> Panipat -> Delhi ISBT
- Hisar -> Bhiwani -> Rewari -> Gurugram

`/routes/search` now returns:
- stops between source and destination
- total distance in km
- expected travel time
- live delay minutes
- nearest running bus ETA

## 7) Production deployment (Docker)

1. Create `.env` from `.env.example`.
2. Set `CORS_ORIGINS` to your frontend domain.
3. Set strong `DRIVER_API_KEYS`.
4. Run:

```bash
docker compose up --build -d
```

API will be available at `http://localhost:8000`.

## 8) Commercial readiness checklist

- Add real Haryana timetable ingestion (PDF/CSV -> DB cron job)
- Replace in-memory demo with PostgreSQL tables for routes, stops, buses, trips, and locations
- Add authentication for rider/admin apps (JWT)
- Add monitoring (Sentry + uptime checks + log aggregation)
- Add API rate limiting and abuse protection at gateway (Cloudflare/Nginx)
