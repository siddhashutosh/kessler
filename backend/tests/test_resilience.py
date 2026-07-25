"""Provider-protection tests: circuit breakers + login rate limiting.

These guard against the failure mode that suspended the Space-Track account:
auth/block responses turning into a request storm.
"""
import time

import pytest

from app.core.exceptions import DataSourceError, RateLimitError
from app.service.celestrak_client import CelestrakClient
from app.service.spacetrack_client import SpaceTrackClient


class TestCelestrakCircuit:
    def test_open_circuit_blocks_without_network(self):
        c = CelestrakClient()
        c._circuit_until = time.time() + 3600  # simulate a recent 403 block
        with pytest.raises(DataSourceError) as exc:
            c.fetch_group("active")
        assert "circuit breaker" in exc.value.message.lower()

    def test_closed_circuit_allows_attempt(self):
        c = CelestrakClient()
        # circuit closed by default; a real fetch would hit the network, so we
        # only assert the guard does not pre-empt (circuit_until is in the past)
        assert c._circuit_until == 0.0


class TestSpaceTrackCircuit:
    def _client(self, tmp_path):
        st = SpaceTrackClient(username="u@example.com", password="x")
        st._state_file = tmp_path / "state.json"
        return st

    def test_open_circuit_blocks_query(self, tmp_path):
        st = self._client(tmp_path)
        st._state["circuit_until"] = time.time() + 3600
        with pytest.raises(DataSourceError) as exc:
            st.fetch_cdm_public()
        assert "circuit breaker" in exc.value.message.lower()

    def test_login_is_rate_limited(self, tmp_path):
        st = self._client(tmp_path)
        st._state["last_login"] = time.time()  # just logged in
        with pytest.raises(RateLimitError):
            st._login()

    def test_circuit_state_persists(self, tmp_path):
        st = self._client(tmp_path)
        st._open_circuit(3600 * 24, "suspension signature")
        # a fresh client loading the same file sees the open circuit
        st2 = SpaceTrackClient(username="u@example.com", password="x")
        st2._state_file = st._state_file
        st2._state = st2._load_state()
        assert st2._circuit_open() > 0
