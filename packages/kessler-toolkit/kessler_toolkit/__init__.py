"""kessler-toolkit — open conjunction assessment primitives.

Generated modules are synced from the KESSLER backend logic layer
(backend/app/logic), which is the source of truth.
"""
from kessler_toolkit.cdm_parser import Cdm, CdmObject, parse_cdm_kvn, parse_cdm_public_row
from kessler_toolkit.collision_probability import (
    PcResult,
    compute_pc,
    encounter_plane_projection,
    pc_chan,
    pc_foster,
    pc_max,
)
from kessler_toolkit.exceptions import (
    CdmParseError,
    KesslerError,
    PropagationError,
)
from kessler_toolkit.propagation import (
    ground_track,
    load_satrec,
    refine_tca,
    rtn_components,
    state_teme,
)
from kessler_toolkit.risk_engine import classify, recommend, urgency
from kessler_toolkit.screening import CloseApproachHit, altitude_band, screen

__version__ = "0.1.1"

__all__ = [
    "Cdm", "CdmObject", "parse_cdm_kvn", "parse_cdm_public_row",
    "PcResult", "compute_pc", "encounter_plane_projection",
    "pc_chan", "pc_foster", "pc_max",
    "KesslerError", "CdmParseError", "PropagationError",
    "load_satrec", "state_teme", "refine_tca", "rtn_components", "ground_track",
    "classify", "urgency", "recommend",
    "screen", "altitude_band", "CloseApproachHit",
    "__version__",
]
