"""CDM parser fixtures: KVN round-trip, cdm_public rows, validation failures."""
import numpy as np
import pytest

from app.core.exceptions import CdmParseError
from app.logic.cdm_parser import parse_cdm_kvn, parse_cdm_public_row

KVN_FIXTURE = """
CCSDS_CDM_VERS = 1.0
CREATION_DATE = 2026-07-20T12:00:00.000
ORIGINATOR = KESSLER-TEST
MESSAGE_ID = TEST-KVN-001
TCA = 2026-07-22T14:32:08.500
MISS_DISTANCE = 192.0 [m]
RELATIVE_SPEED = 14320.0 [m/s]
RELATIVE_POSITION_R = 30.0 [m]
RELATIVE_POSITION_T = 140.0 [m]
RELATIVE_POSITION_N = 128.0 [m]
RELATIVE_VELOCITY_R = -100.0 [m/s]
RELATIVE_VELOCITY_T = 14300.0 [m/s]
RELATIVE_VELOCITY_N = 600.0 [m/s]
OBJECT = OBJECT1
OBJECT_DESIGNATOR = 61001
OBJECT_NAME = KESSLER-DEMO SAT
OBJECT_TYPE = PAYLOAD
CR_R = 1600.0 [m**2]
CT_R = 120.0 [m**2]
CT_T = 40000.0 [m**2]
CN_R = 10.0 [m**2]
CN_T = 60.0 [m**2]
CN_N = 900.0 [m**2]
OBJECT = OBJECT2
OBJECT_DESIGNATOR = 44012
OBJECT_NAME = DEMO DEBRIS OBJ
OBJECT_TYPE = DEBRIS
CR_R = 2500.0 [m**2]
CT_R = 200.0 [m**2]
CT_T = 90000.0 [m**2]
CN_R = 15.0 [m**2]
CN_T = 80.0 [m**2]
CN_N = 1600.0 [m**2]
"""


class TestKvn:
    def test_round_trip(self):
        cdm = parse_cdm_kvn(KVN_FIXTURE)
        assert cdm.cdm_id == "TEST-KVN-001"
        assert cdm.miss_distance_m == pytest.approx(192.0)
        assert cdm.tca.year == 2026 and cdm.tca.tzinfo is not None
        assert cdm.sat1.designator == "61001"
        assert cdm.sat2.object_type == "DEBRIS"
        assert cdm.covariance_available
        assert cdm.sat1.cov_rtn_m2.shape == (3, 3)
        # symmetry enforced
        assert np.allclose(cdm.sat1.cov_rtn_m2, cdm.sat1.cov_rtn_m2.T)
        assert cdm.rel_position_rtn_m is not None
        assert np.linalg.norm(cdm.rel_position_rtn_m) == pytest.approx(192.0, rel=0.02)

    def test_missing_tca_and_designator_reported_together(self):
        broken = "\n".join(
            line for line in KVN_FIXTURE.splitlines()
            if not line.startswith("TCA") and "OBJECT_DESIGNATOR = 61001" not in line
        )
        with pytest.raises(CdmParseError) as exc_info:
            parse_cdm_kvn(broken)
        detail = " ".join(exc_info.value.detail)
        assert "TCA" in detail
        assert "OBJECT_DESIGNATOR" in detail

    def test_non_psd_covariance_dropped(self):
        bad = KVN_FIXTURE.replace("CR_R = 1600.0 [m**2]", "CR_R = -99999.0 [m**2]")
        cdm = parse_cdm_kvn(bad)
        assert cdm.sat1.cov_rtn_m2 is None
        assert not cdm.covariance_available


class TestCdmPublic:
    ROW = {
        "CDM_ID": "1042001", "CREATED": "2026-07-21 03:10:11",
        "EMERGENCY_REPORTABLE": "Y", "TCA": "2026-07-22T14:32:08.500",
        "MIN_RNG": 0.192, "PC": 0.000214,
        "SAT_1_ID": "61001", "SAT_1_NAME": "KESSLER-DEMO SAT",
        "SAT1_OBJECT_TYPE": "PAYLOAD",
        "SAT_2_ID": "44012", "SAT_2_NAME": "DEMO DEBRIS OBJ",
        "SAT2_OBJECT_TYPE": "DEBRIS", "REL_SPEED": 14.32,
    }

    def test_parses_row(self):
        cdm = parse_cdm_public_row(self.ROW)
        assert cdm.cdm_id == "1042001"
        assert cdm.miss_distance_m == pytest.approx(192.0)  # km -> m
        assert cdm.relative_speed_ms == pytest.approx(14320.0)
        assert cdm.pc_reported == pytest.approx(0.000214)
        assert cdm.emergency_reportable is True
        assert not cdm.covariance_available

    def test_missing_fields_collected(self):
        row = dict(self.ROW)
        del row["TCA"]
        row["SAT_1_ID"] = ""
        with pytest.raises(CdmParseError) as exc_info:
            parse_cdm_public_row(row)
        detail = " ".join(exc_info.value.detail)
        assert "TCA" in detail and "SAT_1_ID" in detail

    def test_null_pc_accepted(self):
        row = dict(self.ROW, PC=None)
        cdm = parse_cdm_public_row(row)
        assert cdm.pc_reported is None
