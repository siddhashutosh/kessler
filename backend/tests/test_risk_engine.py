"""Risk classification threshold and urgency monotonicity tests (FR-RSK)."""
from datetime import datetime, timedelta, timezone

from app.logic import risk_engine

NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)


class TestClassify:
    def test_thresholds(self):
        assert risk_engine.classify(2e-4, "computed", 5000, True) == "CRITICAL"
        assert risk_engine.classify(1e-4, "computed", 5000, True) == "CRITICAL"
        assert risk_engine.classify(9.9e-5, "computed", 5000, True) == "WARNING"
        assert risk_engine.classify(1e-5, "computed", 5000, True) == "WARNING"
        assert risk_engine.classify(9.9e-6, "computed", 5000, True) == "MONITOR"
        assert risk_engine.classify(1e-7, "computed", 5000, True) == "MONITOR"
        assert risk_engine.classify(9.9e-8, "computed", 5000, True) == "NEGLIGIBLE"

    def test_close_miss_without_covariance_escalates(self):
        base = risk_engine.classify(5e-6, "max", 5000, False)
        escalated = risk_engine.classify(5e-6, "max", 800, False)
        order = ["NEGLIGIBLE", "MONITOR", "WARNING", "CRITICAL"]
        assert order.index(escalated) == order.index(base) + 1

    def test_escalation_caps_at_critical(self):
        assert risk_engine.classify(2e-4, "max", 500, False) == "CRITICAL"


class TestUrgency:
    def test_monotonic_in_risk_class(self):
        tca = NOW + timedelta(hours=48)
        scores = [
            risk_engine.urgency(r, tca, None, now=NOW)
            for r in ["NEGLIGIBLE", "MONITOR", "WARNING", "CRITICAL"]
        ]
        assert scores == sorted(scores)

    def test_monotonic_in_time_to_tca(self):
        near = risk_engine.urgency("WARNING", NOW + timedelta(hours=6), None, now=NOW)
        far = risk_engine.urgency("WARNING", NOW + timedelta(hours=60), None, now=NOW)
        assert near > far

    def test_stale_data_raises_urgency(self):
        tca = NOW + timedelta(hours=30)
        fresh = risk_engine.urgency("MONITOR", tca, NOW - timedelta(hours=1), now=NOW)
        stale = risk_engine.urgency("MONITOR", tca, NOW - timedelta(hours=40), now=NOW)
        assert stale > fresh

    def test_bounded(self):
        score = risk_engine.urgency("CRITICAL", NOW + timedelta(minutes=10),
                                    NOW - timedelta(hours=100), now=NOW)
        assert 0 <= score <= 100


class TestRecommend:
    def test_critical_mentions_operator_cdm(self):
        text = risk_engine.recommend("CRITICAL", NOW + timedelta(hours=20), False,
                                     now=NOW, pc_type="max")
        assert "operator" in text.lower()
        assert "upper bound" in text

    def test_reported_pc_without_covariance_notes_source(self):
        text = risk_engine.recommend("CRITICAL", NOW + timedelta(hours=20), False,
                                     now=NOW, pc_type="reported")
        assert "upper bound" not in text
        assert "source-reported" in text

    def test_covariance_available_omits_bound_note(self):
        text = risk_engine.recommend("MONITOR", NOW + timedelta(hours=20), True,
                                     now=NOW, pc_type="computed")
        assert "upper bound" not in text
