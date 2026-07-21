"""Force Demo Mode for the entire test suite — tests must be deterministic and
must never hit live external services, regardless of any .env credentials."""
import os

os.environ["KESSLER_DEMO_MODE"] = "true"
