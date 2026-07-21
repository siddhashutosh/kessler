# KESSLER

**Open Orbital Conjunction Assessment & Risk Toolkit** — an open-source pipeline that ingests
public space-surveillance data (Conjunction Data Messages + GP orbital elements), computes and
verifies collision probability (Pc), classifies orbital-collision risk, and presents everything
through a REST API and a 3D web dashboard.

> Named for the Kessler Syndrome — the debris-cascade scenario this class of tooling exists to prevent.

## Why

- NASA's reference conjunction-assessment tooling (CARA) is MATLAB-only; no lightweight open
  Python library covers CDM parsing + Pc computation.
- The US TraCSS programme is beginning to distribute standardized CDMs to all satellite
  operators — a wave of new consumers who need free tooling.
- Full research and requirements: see `documents/` (SRS, HLD, LLD as PDF).

## Architecture (short version)

```
CelesTrak (OMM/JSON)  Space-Track (cdm_public)      <- free, public, rate-limit-respected
        │                     │
        ▼                     ▼
  ┌─ service layer ─ orchestration, caching (SQLite, cache-first), clients ─┐
  │  ┌─ logic layer ─ pure astrodynamics & risk math ────────────────────┐  │
  │  │  CDM parser (KVN + JSON) · SGP4 propagation · screening sieve     │  │
  │  │  Foster 2D Pc + Chan cross-check + Max-Pc bound · risk engine     │  │
  │  └─────────────────────────────────────────────────────────────────-┘  │
  └── FastAPI /api/v1 ──────────────────────────────────────────────────---┘
        │
        ▼
  React + Three.js dashboard  ·  live n8n-style pipeline diagram
```

Six pipeline "agents" (Catalog Sync → CDM Ingest → Parser → Pc Engine → Risk Analyst →
Publisher) — visualised live at `/pipeline` in the UI and in
`documents/diagrams/pipeline-flow.html`.

## Repository layout

```
documents/   SRS, HLD, LLD (PDF + HTML sources), n8n-style diagram, QA report
backend/     Python 3.11+ · FastAPI  (app/logic = pure math, app/service = orchestration)
ui/          Vite + React + TypeScript + Three.js
```

## Run locally

### Backend (port 8000)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Runs in **Demo Mode** out of the box (bundled sample CDMs + catalogue, zero credentials).
For live data, copy `.env.example` to `.env` and add Space-Track credentials; add
`KESSLER_ANTHROPIC_API_KEY` to enable AI analyst briefings (falls back to templates otherwise).

### UI (port 5173)

```powershell
cd ui
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` to the backend.

### Tests

```powershell
cd backend
.venv\Scripts\python -m pytest tests -q
```

## API

Interactive docs at http://localhost:8000/docs. Key endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/conjunctions` | Urgency-ranked conjunction events |
| `GET /api/v1/conjunctions/{id}` | Full event detail (Pc method, cross-check, action) |
| `GET /api/v1/conjunctions/{id}/insight` | AI/template analyst briefing |
| `POST /api/v1/screening/run` | Screen an asset against the catalogue (SGP4) |
| `GET /api/v1/satellites/{norad}/track` | Ground track + ECI orbit points |
| `GET /api/v1/pipeline/status` | Live agent pipeline status |

## Data sources & attribution

Orbital data courtesy of **Space-Track.org** (USSPACECOM) and **CelesTrak**. Basic SSA data is
redistributed under USSPACECOM's blanket approval with citation. Space-Track rate limits
(<30 req/min, <300 req/hr) are enforced by a client-side governor; the architecture is
cache-first by design. Screening results are triage-grade (SGP4/GP accuracy limits apply) —
this is not an operational collision-avoidance service.

## Roadmap

- Operator-grade KVN CDMs with full covariance (parser already supports them)
- AWS deployment (EventBridge scheduler, RDS/S3 behind the existing `CacheService` seam)
- Probabilistic space-weather driver forecasting (phase 2 — "open orbital risk stack")
