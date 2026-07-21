"""Screening tests on engineered geometries (FR-SCR)."""
from datetime import datetime, timezone

from app.logic.screening import altitude_band, bands_overlap, screen

BASE = {
    "EPOCH": "2026-07-20T18:00:00", "ECCENTRICITY": 0.0009, "INCLINATION": 53.02,
    "RA_OF_ASC_NODE": 120.0, "ARG_OF_PERICENTER": 45.0, "MEAN_ANOMALY": 10.0,
    "MEAN_MOTION": 15.1021, "BSTAR": 0.0001, "MEAN_MOTION_DOT": 0.0,
    "MEAN_MOTION_DDOT": 0.0,
}


def make_omm(norad, name, **overrides):
    omm = dict(BASE, NORAD_CAT_ID=norad, OBJECT_NAME=name, OBJECT_TYPE="PAYLOAD")
    omm.update(overrides)
    return omm


START = datetime(2026, 7, 21, 0, 0, 0, tzinfo=timezone.utc)


class TestSieve:
    def test_altitude_band_reasonable(self):
        perigee, apogee = altitude_band(BASE)
        assert 400 < perigee < 600
        assert apogee >= perigee

    def test_disjoint_bands_excluded(self):
        assert not bands_overlap((400, 420), (800, 900), pad_km=15)
        assert bands_overlap((400, 500), (490, 600), pad_km=15)


class TestScreen:
    def test_detects_engineered_close_pair(self):
        asset = make_omm(61001, "ASSET")
        # nearly identical orbit, slightly offset phase -> persistent close range
        intruder = make_omm(90001, "INTRUDER", MEAN_ANOMALY=10.06,
                            RA_OF_ASC_NODE=120.01, ECCENTRICITY=0.0011)
        screened, hits = screen(asset, [asset, intruder], START,
                                window_hours=6, threshold_km=25)
        assert screened == 1  # asset itself skipped
        assert hits, "engineered close pair must be detected"
        assert hits[0].norad_id == "90001"
        assert hits[0].miss_distance_m < 25_000
        assert len(hits[0].miss_rtn_m) == 3

    def test_altitude_sieve_excludes_disjoint_orbit(self):
        asset = make_omm(61001, "ASSET")
        far = make_omm(90002, "GEO-ISH", MEAN_MOTION=1.0027)  # ~GEO altitude
        screened, hits = screen(asset, [far], START, window_hours=2,
                                threshold_km=10)
        assert screened == 0
        assert hits == []

    def test_empty_catalog_noop(self):
        asset = make_omm(61001, "ASSET")
        screened, hits = screen(asset, [], START, window_hours=2, threshold_km=10)
        assert screened == 0 and hits == []
