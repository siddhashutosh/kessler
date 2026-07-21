# KESSLER — Launch announcement pack

Ready-to-paste drafts, one channel per day. Post from your own accounts; tweak
voice freely — these are written to sound like a person, not a press release.
Suggested order: HN → CelesTrak/SatNOGS forums → Reddit → LinkedIn → X → dev.to.

---

## 1 · Hacker News (Show HN)

**Title:**
```
Show HN: KESSLER – open-source conjunction assessment from public satellite data
```

**URL:** `https://github.com/siddhashutosh/kessler`

**First comment (post immediately after submitting):**
```
Hi HN — I built KESSLER because the tooling situation in space traffic awareness
surprised me: there are ~47,000 tracked objects in orbit, every satellite
operator receives standardized collision warnings (CDMs), and yet the reference
software for actually computing collision probability from them is MATLAB-only
(NASA CARA), and the most popular open-source Python astrodynamics library
(poliastro) was archived in 2023.

KESSLER is a pipeline that ingests the public Space-Track CDM feed and the
CelesTrak catalogue, collapses the duplicate/superseded reports (each
conjunction is published once per object's perspective, plus a new row per
screening update), computes collision probability two independent ways
(Foster 2-D numerical integration cross-checked against Chan's analytic
series), and ranks every event by urgency. There's a 3D dashboard on top, and
the math core is a standalone package: pip install kessler-toolkit.

Live demo (real data, refreshed every 30 min, on a $5 VPS — please be gentle):
http://13.127.244.0

A few things I tried to get right:
- Every probability is labelled with how it was computed: full-covariance math,
  source-reported, or a conservative covariance-free upper bound. The tool
  never pretends to know more than it does.
- The Pc engine is validated against the closed-form isotropic solution
  (<0.1% error) and the two methods must agree within 5% or the event is
  flagged.
- It's honest about limits: with public GP data + SGP4 this is triage-grade,
  not operational collision avoidance. The parser already accepts
  operator-grade CDMs with covariance for the real thing.

Stack: FastAPI + numpy + sgp4 backend (pure-math logic layer, separately
packaged), React + Three.js frontend. Apache-2.0. Happy to answer anything
about the orbital mechanics or the data-quality surprises in the public feed.
```

---

## 2 · CelesTrak / SatNOGS (Libre Space) community forum

**Title:** `KESSLER: open-source CDM parsing + collision probability toolkit (Python)`

```
Hello — sharing a new Apache-2.0 project that may be useful to this community.

KESSLER (github.com/siddhashutosh/kessler) is a conjunction assessment
pipeline over public data: Space-Track cdm_public + CelesTrak GP, with proper
rate-limit governance on both (cache-first, <20 req/min hard-capped for
Space-Track, per-object CATNR lookups cached including negative results —
I tried hard to be a polite consumer of both services).

The astrodynamics core is also on PyPI as `kessler-toolkit`:
- CCSDS 508.0-B-1 KVN CDM parser (incl. RTN covariance) + cdm_public JSON
- Foster 2-D Pc with Chan series cross-check, plus a labelled max-Pc bound
  when covariance is unavailable
- SGP4 screening (altitude sieve → coarse scan → refined TCA, RTN components)
- Risk triage with the usual 1e-4 / 1e-5 / 1e-7 thresholds

Live instance on real data: http://13.127.244.0

I'd particularly welcome scrutiny of the Pc implementation from people who
know this domain — tests validate against the closed-form isotropic case and
Foster/Chan agreement, but more eyes on the math would be very welcome.
Attribution to Space-Track and CelesTrak is carried on every data surface;
if anyone from either project sees an issue with how the data is used or
credited, please tell me and I'll fix it immediately.
```

---

## 3 · Reddit (r/satellites, r/orbitalmechanics; adapt for r/spacex)

**Title:** `I built an open-source tool that watches every conjunction in the public Space-Track feed and ranks them by risk (live demo)`

```
There are ~47k tracked objects in orbit and the public conjunction feed is...
rough: every event appears twice (once per object), plus a new row per
screening update, and the reference tooling to compute collision probability
is MATLAB-only.

So I built KESSLER: it dedupes the feed, computes Pc two independent ways
(and flags when they disagree), and ranks everything by urgency with a 3D
orbit view. Yesterday it was tracking a debris-on-debris event at Pc ~7e-4 —
that's the kind of collision that creates the next Fengyun-1C-style cloud.

Live (real data): http://13.127.244.0
Source (Apache-2.0): https://github.com/siddhashutosh/kessler
Math as a library: pip install kessler-toolkit

Honest limits: public GP + SGP4 = triage-grade, kilometre-scale accuracy over
days. It tells you where to look, not when to burn. Feedback very welcome —
especially from anyone who operates actual hardware up there.
```

---

## 4 · LinkedIn (the build-story angle)

```
I just open-sourced KESSLER — a conjunction assessment toolkit for the space
industry — and I want to share the build story, because the process mattered
as much as the product.

The gap: 47,000+ tracked objects in orbit. Every satellite operator receives
collision warnings (CDMs). The reference software to process them requires a
MATLAB license, and the leading open-source Python astrodynamics library was
archived in 2023. Meanwhile the US TraCSS programme is now distributing CDMs
to thousands of operators who have never parsed one.

What I shipped:
🛰️ A six-agent pipeline: ingest → dedupe → dual-method collision probability
(Foster 2-D cross-checked against Chan's series) → risk triage → 3D dashboard
📐 Aerospace-style rigor: SRS, HLD, LLD and a signed QA report, with 50 tests
validating the math against closed-form solutions
📦 The core as a library: pip install kessler-toolkit
💰 Production on a $5 VPS at 66 MB RAM — live at http://13.127.244.0

The part I'm proudest of: every probability the system shows is labelled with
how it was computed — full covariance, source-reported, or a conservative
upper bound. In safety-adjacent tooling, knowing what your number means is
the feature.

Built in the open from India 🇮🇳 — where 250+ NewSpace startups are
concentrated upstream while downstream tooling (70% of global commercial
space activity) stays underserved.

Repo: github.com/siddhashutosh/kessler
If you operate smallsats or work in SSA, I'd genuinely love your feedback.

#SpaceTech #OpenSource #NewSpace #SSA #Python
```

---

## 5 · X / Twitter thread

```
1/ There are 47,000 tracked objects in orbit. Every operator gets collision
warnings. The software to read them? MATLAB-only, or dead since 2023.

So I built KESSLER — open-source conjunction assessment. Live demo, real data:
http://13.127.244.0 🧵

2/ The public feed is messier than you'd think: every conjunction is published
TWICE (once per object's perspective), plus a new row per screening update.
KESSLER collapses ~100 duplicate rows per cycle into clean, ranked events.

3/ Collision probability is computed two independent ways — Foster 2-D
numerical integration cross-checked against Chan's analytic series. If they
disagree by >5%, the event gets flagged instead of hidden.

4/ And when there's no covariance data? It shows a labelled worst-case upper
bound instead of pretending. In safety tooling, knowing what your number
means IS the product.

5/ The whole thing — ingestion, math, API, 3D dashboard — runs in 66 MB of
RAM on a $5 VPS. The math is pip-installable: `pip install kessler-toolkit`

6/ Apache-2.0, full aerospace-style docs (SRS/HLD/LLD/QA), 50 tests validated
against closed-form solutions.

github.com/siddhashutosh/kessler — feedback welcome, especially from people
with hardware in orbit 🛰️
```

---

## 6 · dev.to / blog article (outline — expand from SRS/HLD content)

**Title:** `Computing satellite collision probability in Python — from public data to a live dashboard`

1. The Kessler Syndrome in one paragraph; why 2026 (TraCSS) makes this urgent
2. The public data landscape: Space-Track cdm_public quirks (dual perspectives,
   superseded updates, rate limits), CelesTrak GP, licensing/attribution
3. The math: encounter-plane projection, Foster 2-D integration, Chan's series,
   why cross-checking two methods matters, the max-Pc bound derivation
4. Architecture: pure logic layer vs service layer, cache-first as a hard
   constraint, the six-agent pipeline
5. War stories: the OOM that a 12k-object re-parse caused, negative caching,
   surviving on 414 MB of RAM
6. Honest limits: SGP4 error budgets, triage vs operational
7. What's next: operator CDMs, probabilistic space-weather forecasting

---

## Posting notes

- Space-Track's user agreement: attribution is already on every surface; if
  anyone questions data usage, the citation language is in the README footer.
- If the demo gets hammered: nginx rate-limits per IP and the app serves
  cached data under load. Worst case `sudo systemctl restart kessler` via SSH.
- Expect the "SGP4 isn't accurate enough for this" comment — the answer is in
  the Q&A table in DEMO-SCRIPT.md (we agree, it's triage-grade, labelled as
  such, and the operator-CDM path exists).
```
