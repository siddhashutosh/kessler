"""Duplicate-CDM collapse: A×B vs B×A perspectives and superseded updates."""
from datetime import datetime, timedelta, timezone

from app.logic.cdm_parser import Cdm, CdmObject
from app.service.conjunction_service import _dedupe_cdms

TCA = datetime(2026, 7, 22, 15, 15, 34, tzinfo=timezone.utc)
CREATED = datetime(2026, 7, 21, 3, 0, 0, tzinfo=timezone.utc)


def make_cdm(cdm_id, sat1, sat2, miss_m, created, tca=TCA):
    return Cdm(
        cdm_id=cdm_id, tca=tca, miss_distance_m=miss_m,
        sat1=CdmObject(designator=sat1), sat2=CdmObject(designator=sat2),
        created=created, source="test",
    )


def test_reverse_perspective_collapsed():
    a = make_cdm("1", "111", "222", 277_000, CREATED)
    b = make_cdm("2", "222", "111", 277_000, CREATED + timedelta(minutes=1))
    result = _dedupe_cdms([a, b])
    assert len(result) == 1
    assert result[0].cdm_id == "2"  # freshest CREATED wins


def test_superseded_update_collapsed_keeping_latest():
    old = make_cdm("1", "111", "222", 277_000, CREATED)
    mid = make_cdm("2", "111", "222", 126_000, CREATED + timedelta(hours=2))
    new = make_cdm("3", "222", "111", 61_000, CREATED + timedelta(hours=4))
    result = _dedupe_cdms([old, mid, new])
    assert len(result) == 1
    assert result[0].miss_distance_m == 61_000


def test_distinct_events_preserved():
    a = make_cdm("1", "111", "222", 100_000, CREATED)
    b = make_cdm("2", "111", "333", 100_000, CREATED)  # different pair
    c = make_cdm("3", "111", "222", 100_000, CREATED,
                 tca=TCA + timedelta(hours=5))  # same pair, different TCA
    assert len(_dedupe_cdms([a, b, c])) == 3


def test_missing_created_falls_back_to_tca():
    a = make_cdm("1", "111", "222", 100_000, None)
    b = make_cdm("2", "222", "111", 90_000, CREATED)
    result = _dedupe_cdms([a, b])
    assert len(result) == 1
    assert result[0].cdm_id == "2"
