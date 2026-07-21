# Contributing to KESSLER

Thanks for your interest — conjunction assessment tooling gets better with more eyes.

## Ground rules

- **`backend/app/logic/` is the source of truth** for all astrodynamics and risk math.
  It is pure Python (no I/O, no framework imports) and must stay that way. The
  installable `kessler-toolkit` package under `packages/` is generated from it via
  `python packages/sync.py` — never edit the package copies directly.
- Every change to the math requires a test. Pc changes must be validated against
  either a closed-form reference or Foster/Chan cross-agreement.
- Tests always run in Demo Mode (enforced by `backend/tests/conftest.py`) — they must
  never hit Space-Track or CelesTrak.
- Respect the data providers: never weaken the Space-Track rate-limit governor
  (`spacetrack_client.py`); keep attribution strings intact.

## Dev setup

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Python 3.11+ (3.9 works via eval-type-backport)
.venv/bin/python -m pytest tests -q                                  # 49 tests, ~1 s

cd ../ui
npm install && npm run dev                                           # Vite dev server, /api proxied to :8000
```

Run the backend with `python -m uvicorn app.main:app --port 8000` — it works with
zero credentials (bundled demo data). See `README.md` for live-mode setup.

## Good first issues

- **SOCRATES cross-check** — compare KESSLER's screening output against CelesTrak's
  SOCRATES reports for the same epoch.
- **TLE file import** — accept a local 3LE/TLE file as a catalogue source alongside
  CelesTrak groups.
- **Docker image** — single-container build serving API + UI.
- **Operator CDM ingestion endpoint** — POST a KVN CDM (parser already supports full
  covariance) and get a full-fidelity Pc back.

## Pull requests

- One logical change per PR; include the *why* in the description.
- `pytest` green and, for UI changes, `npm run build` clean.
- Architecture-level changes should reference the relevant SRS/HLD/LLD section in
  `documents/` (and update it if behaviour diverges).

## License

By contributing you agree your contributions are licensed under Apache-2.0.
