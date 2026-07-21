# kessler-toolkit

Open conjunction assessment for Python: parse CCSDS Conjunction Data Messages,
compute collision probability three honest ways, screen a satellite against a
catalogue, and triage the results — no MATLAB license required.

Extracted from [KESSLER](https://github.com/siddhashutosh/kessler), where the same
code powers a live dashboard over the public Space-Track feed.

```bash
pip install kessler-toolkit
```

## What's inside

| Module | Purpose |
|---|---|
| `cdm_parser` | CCSDS 508.0-B-1 KVN CDMs (incl. RTN covariance) and Space-Track `cdm_public` JSON → typed `Cdm` |
| `collision_probability` | Foster 2-D numerical Pc, Chan analytic series (cross-check), covariance-free Max-Pc bound |
| `propagation` | SGP4 wrapper (TEME), close-approach refinement to sub-second TCA, ground tracks |
| `screening` | Catalogue screening: altitude sieve → coarse scan → refined TCA + RTN miss components |
| `risk_engine` | Operator-community risk classes (1e-4 / 1e-5 / 1e-7), urgency scoring, recommended actions |

## Quick start

```python
from kessler_toolkit import parse_cdm_kvn, compute_pc

cdm = parse_cdm_kvn(open("conjunction.cdm").read())

result = compute_pc(
    miss_m=cdm.miss_distance_m,
    hbr_m=20.0,
    r_rel_m=cdm.rel_position_rtn_m,
    v_rel_ms=cdm.rel_velocity_rtn_ms,
    cov1_m2=cdm.sat1.cov_rtn_m2,
    cov2_m2=cdm.sat2.cov_rtn_m2,
    pc_reported=cdm.pc_reported,
)
print(result.value, result.method, result.pc_type)
# e.g. 2.19e-04 foster-2d computed  — with Chan cross-check in result.cross_check
```

Every result carries `pc_type` — `"computed"` (full covariance), `"reported"`
(source value), or `"max"` (conservative upper bound) — so downstream code can
never mistake a triage bound for a measurement.

Validated against the closed-form isotropic solution (<0.1% error) and
Foster/Chan cross-agreement; screening results are triage-grade (SGP4/GP
accuracy limits apply) — not a substitute for operator ephemerides.

Apache-2.0. Orbital data used with KESSLER courtesy of Space-Track.org and CelesTrak.
