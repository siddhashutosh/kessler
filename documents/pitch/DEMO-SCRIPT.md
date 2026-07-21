# KESSLER — Demo Script

Two formats: a **30-second elevator pitch** and a **3-minute live demo** with exact
clicks and talk-track. Deck: `kessler-pitch.html` (open in any browser, arrow keys
navigate) — use it before or after the live demo, not during.

---

## 30-second elevator pitch

> "There are 47,000 tracked objects in orbit, and every satellite operator now gets
> collision warnings — Conjunction Data Messages — from the US government. But the
> tooling to actually *read* them is MATLAB-locked or commercial. KESSLER is an
> open-source pipeline that ingests the live feed, deduplicates it, computes collision
> probability two independent ways, and ranks every event by how urgently a human
> should care — with a 3D dashboard on top. It's verified against closed-form math,
> fully documented aerospace-style, and it's running in production right now on a
> five-dollar server. I can show you a real debris conjunction it's tracking today."

---

## Pre-demo checklist (5 minutes before)

```bash
# 1. Tunnel to the live VPS deployment (real Space-Track data):
ssh -i ~/.ssh/lightsail-ap-south-1.pem -L 8000:localhost:8000 ubuntu@13.127.244.0
#    ...or run locally: backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 2. Sanity check — must say "data_mode": "live":
curl http://localhost:8000/api/v1/health

# 3. Open these tabs in order:
#    A  http://localhost:8000/            (dashboard)
#    B  http://localhost:8000/pipeline    (live agent diagram)
#    C  http://localhost:8000/docs        (OpenAPI)
#    D  kessler-pitch.html                (deck, for open/close)
```

Fallback: if the network dies, unset the credentials (`KESSLER_DEMO_MODE=true`) and
restart — Demo Mode runs the identical experience on bundled data, offline.

---

## 3-minute live demo

### Beat 1 — the hook (Tab A, dashboard) · 40s

*Point at the top CRITICAL event.*

> "This is live. These two objects — a piece of an SL-16 rocket body and a fragment
> of COSMOS 1375 — are converging right now, with a collision probability of about
> 2 in 10,000. That's over the threshold where a real operator would act. KESSLER
> pulled this from the US Space Force public feed minutes ago, collapsed the
> duplicate reports, and ranked it #1 out of everything happening in orbit today."

*Click through 2–3 events; point at the countdown timers and risk badges.*

> "Everything is ranked by urgency — probability, time-to-approach, data freshness —
> so a one-person satellite team sees in five seconds what matters."

### Beat 2 — the 3D view + honesty (Tab A, detail panel) · 40s

*Select an event; rotate the globe; point at the two orbit rings and red marker.*

> "Both orbits in 3D, and the closest-approach point marked. Now the part I'm
> proudest of —" *point at the Pc block in the detail panel* "— every probability
> tells you **how** it was computed. Full covariance math when we have it, the
> source's own value when reported, and when neither exists, a labelled worst-case
> upper bound. The tool never pretends to know more than it does — in this domain
> that honesty is a feature."

### Beat 3 — the pipeline is the architecture (Tab B) · 40s

*Let the diagram breathe for a moment — nodes lit green with item counts.*

> "This isn't a monitoring add-on — this **is** the architecture diagram, live. Six
> agents: catalog sync, CDM ingest, parsing, the probability engine — which computes
> every value two independent ways and flags any disagreement — risk triage, and
> publish. Green means the last run succeeded; you can see item counts flow through.
> If Space-Track goes down, these turn amber and the system degrades to cached data
> instead of falling over."

### Beat 4 — it's a platform, not an app (Tab C) · 30s

*Scroll the OpenAPI docs; run GET /api/v1/conjunctions once.*

> "Everything the dashboard does is a typed REST API — conjunction lists, per-event
> detail, on-demand screening of *your* satellite against the catalogue, orbit
> tracks. Any operator can integrate this in an afternoon."

### Beat 5 — the close · 30s

> "Here's what I want you to remember: aerospace-grade rigor — SRS, HLD, LLD, QA
> report, 49 passing tests validated against closed-form solutions — running on a
> five-dollar server, built in the open. The wave of new CDM consumers arriving with
> TraCSS has no open tooling. KESSLER is that tooling. Next up: operator-grade
> covariance, and probabilistic space-weather forecasting — the same pipeline
> pattern applied to the other half of orbital risk."

---

## Q&A ammunition

| Likely question | Answer |
|---|---|
| "How accurate is the screening?" | Triage-grade by design — SGP4 on public GP data is km-level over days. We say so in the UI. Operational avoidance needs operator ephemerides; the parser already accepts full-covariance KVN CDMs for exactly that upgrade path. |
| "What does it cost to run?" | 66 MB RAM, zero paid APIs. It shares a $5-class VPS with other workloads. Rate-limit governor keeps the free Space-Track account compliant. |
| "Why trust your Pc numbers?" | Two independent methods (Foster numerical, Chan analytic) cross-checked on every event, unit-tested against the closed-form isotropic solution to <0.1%. Divergence >5% flags the event visibly. |
| "What about the duplicate-data problem?" | Space-Track publishes each conjunction twice (once per object) plus every screening update. We collapse on unordered pair + TCA, keeping the freshest CDM — that alone halves operator noise. |
| "Who is this for?" | Smallsat operators without SSA teams, researchers who can't license MATLAB, and the TraCSS-era wave of first-time CDM consumers. India angle: 253+ NewSpace startups, almost all upstream — downstream tooling is the gap. |
| "What's the business model?" | Open core. The toolkit stays open; hosted alerting, multi-asset fleets, and operator-CDM integrations are the service layer. Adoption first. |
