"""Reference-case tests for the Pc mathematical core (FR-PC-5)."""
import math

import numpy as np
import pytest

from app.logic.collision_probability import (
    compute_pc,
    encounter_plane_projection,
    pc_chan,
    pc_foster,
    pc_max,
)


def isotropic_closed_form(miss: float, sigma: float, hbr: float, terms: int = 200) -> float:
    """Exact Pc for isotropic 2D Gaussian (Rician integral series)."""
    v = (miss / sigma) ** 2
    u = (hbr / sigma) ** 2
    total = 0.0
    outer = 1.0
    inner_term = 1.0
    inner_sum = 1.0
    exp_u = math.exp(-0.5 * u)
    for m in range(terms):
        if m > 0:
            outer *= (0.5 * v) / m
            inner_term *= (0.5 * u) / m
            inner_sum += inner_term
        total += outer * (1.0 - exp_u * inner_sum)
    return math.exp(-0.5 * v) * total


class TestFoster:
    def test_matches_isotropic_closed_form(self):
        sigma, miss, hbr = 200.0, 500.0, 20.0
        mu = np.array([miss, 0.0])
        cov = np.eye(2) * sigma**2
        expected = isotropic_closed_form(miss, sigma, hbr)
        got = pc_foster(mu, cov, hbr)
        assert got == pytest.approx(expected, rel=1e-3)

    def test_tiny_miss_tight_covariance_near_one(self):
        mu = np.array([1.0, 0.0])
        cov = np.eye(2) * 25.0  # sigma 5 m
        assert pc_foster(mu, cov, hbr_m=20.0) > 0.95

    def test_huge_miss_near_zero(self):
        mu = np.array([50000.0, 0.0])
        cov = np.eye(2) * 100.0**2
        assert pc_foster(mu, cov, hbr_m=20.0) < 1e-12


class TestChanCrossCheck:
    @pytest.mark.parametrize("miss,sx,sy", [
        (500.0, 200.0, 200.0),
        (1200.0, 350.0, 150.0),
        (300.0, 100.0, 400.0),
    ])
    def test_agrees_with_foster(self, miss, sx, sy):
        mu = np.array([miss * 0.8, miss * 0.6])
        cov = np.diag([sx**2, sy**2])
        f = pc_foster(mu, cov, hbr_m=20.0)
        c = pc_chan(mu, cov, hbr_m=20.0)
        assert c == pytest.approx(f, rel=0.05)


class TestMaxPc:
    def test_upper_bounds_isotropic_pc(self):
        miss, hbr = 800.0, 20.0
        bound = pc_max(miss, hbr)
        for sigma in (50.0, 200.0, miss / math.sqrt(2), 2000.0):
            mu = np.array([miss, 0.0])
            cov = np.eye(2) * sigma**2
            assert pc_foster(mu, cov, hbr) <= bound * 1.01

    def test_contact_returns_one(self):
        assert pc_max(miss_m=10.0, hbr_m=20.0) == 1.0

    def test_zero_hbr(self):
        assert pc_max(miss_m=100.0, hbr_m=0.0) == 0.0


class TestEncounterPlane:
    def test_projection_preserves_miss_magnitude_when_orthogonal(self):
        r = np.array([1000.0, 0.0, 0.0])
        v = np.array([0.0, 7500.0, 0.0])  # orthogonal to miss vector
        mu, c2d = encounter_plane_projection(r, v, np.eye(3) * 1e4, np.eye(3) * 1e4)
        assert np.linalg.norm(mu) == pytest.approx(1000.0, rel=1e-9)
        assert c2d.shape == (2, 2)
        # combined isotropic covariance stays isotropic in-plane
        assert c2d[0, 0] == pytest.approx(2e4, rel=1e-9)

    def test_zero_relative_velocity_raises(self):
        from app.core.exceptions import PropagationError

        with pytest.raises(PropagationError):
            encounter_plane_projection(
                np.array([100.0, 0, 0]), np.zeros(3), np.eye(3), np.eye(3)
            )


class TestDispatch:
    def test_full_state_uses_foster_with_cross_check(self):
        result = compute_pc(
            miss_m=500.0, hbr_m=20.0,
            r_rel_m=np.array([500.0, 0.0, 0.0]),
            v_rel_ms=np.array([0.0, 12000.0, 0.0]),
            cov1_m2=np.eye(3) * 200.0**2,
            cov2_m2=np.eye(3) * 200.0**2,
        )
        assert result.method == "foster-2d"
        assert result.pc_type == "computed"
        assert result.cross_check is not None
        assert not result.divergence_flag

    def test_no_covariance_uses_reported_pc(self):
        result = compute_pc(miss_m=900.0, hbr_m=20.0, pc_reported=3.2e-5)
        assert result.pc_type == "reported"
        assert result.value == pytest.approx(3.2e-5)

    def test_nothing_available_uses_max_pc(self):
        result = compute_pc(miss_m=900.0, hbr_m=20.0)
        assert result.pc_type == "max"
        assert result.value == pytest.approx(pc_max(900.0, 20.0))
