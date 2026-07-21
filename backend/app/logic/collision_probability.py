"""Collision probability (Pc) computation — the mathematical core (FR-PC).

Methods:
  * pc_foster : 2D numerical integration of the bivariate Gaussian over the
                hard-body disc in the encounter plane (Foster & Estes 1992).
  * pc_chan   : Chan (2008) equivalent-area analytic series — independent
                cross-check for pc_foster.
  * pc_max    : covariance-free conservative upper bound (triage grade).

All functions are pure (no I/O) and unit-tested against closed-form cases.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

from app.core.exceptions import PropagationError

logger = logging.getLogger(__name__)

_DIVERGENCE_TOLERANCE = 0.05  # FR-PC-2: methods must agree within 5%


@dataclass
class PcResult:
    value: float
    method: str
    pc_type: str  # "computed" | "max" | "reported"
    cross_check: float | None = None
    divergence_flag: bool = False


def encounter_plane_projection(
    r_rel_m: np.ndarray,
    v_rel_ms: np.ndarray,
    cov1_m2: np.ndarray,
    cov2_m2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project the miss vector and combined covariance onto the encounter plane.

    The encounter plane is perpendicular to the relative velocity at TCA;
    for hypervelocity conjunctions the along-track dimension integrates out,
    reducing Pc to a 2D problem (standard short-encounter assumption).

    Returns (mu_2d [m], C_2d [m^2]).
    """
    v_norm = float(np.linalg.norm(v_rel_ms))
    if v_norm < 1e-9:
        raise PropagationError(
            "Relative velocity ~0; short-encounter assumption invalid",
            detail={"v_rel_ms": v_rel_ms.tolist()},
        )

    ez = v_rel_ms / v_norm
    # ex: component of miss vector orthogonal to ez
    r_orth = r_rel_m - np.dot(r_rel_m, ez) * ez
    r_orth_norm = float(np.linalg.norm(r_orth))
    if r_orth_norm < 1e-12:
        # miss vector parallel to velocity — any orthogonal basis works
        candidate = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(candidate, ez)) > 0.9:
            candidate = np.array([0.0, 1.0, 0.0])
        ex = candidate - np.dot(candidate, ez) * ez
        ex /= np.linalg.norm(ex)
    else:
        ex = r_orth / r_orth_norm
    ey = np.cross(ez, ex)

    basis = np.vstack([ex, ey])  # 2x3
    combined = cov1_m2 + cov2_m2  # independent OD errors
    mu = basis @ r_rel_m
    c2d = basis @ combined @ basis.T
    # numerical symmetrisation
    c2d = 0.5 * (c2d + c2d.T)
    return mu, c2d


def pc_foster(
    mu_m: np.ndarray,
    cov_m2: np.ndarray,
    hbr_m: float,
    n_r: int = 60,
    n_theta: int = 90,
) -> float:
    """Foster 2D Pc: midpoint-rule polar integration of N(x; mu, C) over the HBR disc."""
    det = float(np.linalg.det(cov_m2))
    if det <= 0 or hbr_m <= 0:
        raise PropagationError(
            "Degenerate 2D covariance or non-positive HBR in Foster integration",
            detail={"det": det, "hbr_m": hbr_m},
        )
    inv = np.linalg.inv(cov_m2)
    norm_const = 1.0 / (2.0 * math.pi * math.sqrt(det))

    radii = (np.arange(n_r) + 0.5) * (hbr_m / n_r)
    thetas = (np.arange(n_theta) + 0.5) * (2.0 * math.pi / n_theta)
    r_grid, t_grid = np.meshgrid(radii, thetas, indexing="ij")
    x = r_grid * np.cos(t_grid) - mu_m[0]
    y = r_grid * np.sin(t_grid) - mu_m[1]
    quad = inv[0, 0] * x * x + 2.0 * inv[0, 1] * x * y + inv[1, 1] * y * y
    density = norm_const * np.exp(-0.5 * quad)
    d_area = (hbr_m / n_r) * (2.0 * math.pi / n_theta) * r_grid
    return float(np.clip(np.sum(density * d_area), 0.0, 1.0))


def pc_chan(mu_m: np.ndarray, cov_m2: np.ndarray, hbr_m: float, terms: int = 24) -> float:
    """Chan (2008) analytic series via equivalent-area isotropic transformation.

    Diagonalise C -> (sx^2, sy^2); u = hbr^2 / (sx*sy); v = scaled miss distance.
    Pc = e^(-v/2) * sum_{m=0}^{M} [ (v/2)^m / m! * (1 - e^(-u/2) sum_{k=0}^{m} (u/2)^k / k!) ]
    """
    eigvals, eigvecs = np.linalg.eigh(cov_m2)
    if np.any(eigvals <= 0) or hbr_m <= 0:
        raise PropagationError(
            "Degenerate 2D covariance or non-positive HBR in Chan series",
            detail={"eigvals": eigvals.tolist(), "hbr_m": hbr_m},
        )
    sx2, sy2 = float(eigvals[0]), float(eigvals[1])
    mu_rot = eigvecs.T @ mu_m
    u = hbr_m * hbr_m / math.sqrt(sx2 * sy2)
    v = mu_rot[0] ** 2 / sx2 + mu_rot[1] ** 2 / sy2

    # series with running factorial terms (numerically safe for small u, v)
    inner_sum = 0.0
    inner_term = 1.0
    exp_u = math.exp(-0.5 * u)
    outer_total = 0.0
    outer_term = 1.0  # (v/2)^m / m!
    for m in range(terms):
        if m > 0:
            outer_term *= (0.5 * v) / m
            inner_term *= (0.5 * u) / m
        inner_sum += inner_term  # sum_{k<=m} (u/2)^k/k!
        outer_total += outer_term * (1.0 - exp_u * inner_sum)
    return float(np.clip(math.exp(-0.5 * v) * outer_total, 0.0, 1.0))


def pc_max(miss_m: float, hbr_m: float) -> float:
    """Conservative covariance-free upper bound.

    For an isotropic 2D Gaussian, Pc(sigma) is maximised at sigma* = miss/sqrt(2),
    giving Pc_max = (hbr^2 / miss^2) * e^-1 (small-HBR limit), clipped to 1.
    Labelled triage-grade; documented in LLD §3.3.
    """
    if hbr_m <= 0:
        return 0.0
    if miss_m <= hbr_m:
        return 1.0
    return float(min(1.0, (hbr_m * hbr_m) / (miss_m * miss_m) * math.exp(-1.0)))


def compute_pc(
    *,
    miss_m: float,
    hbr_m: float,
    r_rel_m: np.ndarray | None = None,
    v_rel_ms: np.ndarray | None = None,
    cov1_m2: np.ndarray | None = None,
    cov2_m2: np.ndarray | None = None,
    pc_reported: float | None = None,
) -> PcResult:
    """Dispatch Pc computation per FR-PC.

    Full state + covariance -> Foster with Chan cross-check.
    Otherwise -> reported Pc if the source supplied one, else max-Pc bound.
    """
    has_full_state = (
        r_rel_m is not None
        and v_rel_ms is not None
        and cov1_m2 is not None
        and cov2_m2 is not None
    )
    if has_full_state:
        try:
            mu, c2d = encounter_plane_projection(r_rel_m, v_rel_ms, cov1_m2, cov2_m2)
            foster = pc_foster(mu, c2d, hbr_m)
            chan = pc_chan(mu, c2d, hbr_m)
            reference = max(foster, chan, 1e-300)
            divergence = abs(foster - chan) / reference > _DIVERGENCE_TOLERANCE
            if divergence:
                logger.warning(
                    "Pc method divergence: foster=%.3e chan=%.3e", foster, chan
                )
            return PcResult(
                value=foster,
                method="foster-2d",
                pc_type="computed",
                cross_check=chan,
                divergence_flag=divergence,
            )
        except PropagationError as exc:
            logger.warning("Full-state Pc failed (%s); falling back to max-Pc", exc.message)

    if pc_reported is not None and math.isfinite(pc_reported):
        return PcResult(value=float(pc_reported), method="source-reported", pc_type="reported")

    return PcResult(value=pc_max(miss_m, hbr_m), method="alfano-max", pc_type="max")
