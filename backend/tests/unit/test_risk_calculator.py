import pytest
from archon.pipeline.analysis.risk_calculator import classify_risk

def test_classify_risk():
    assert classify_risk(0.10) == "LOW"
    assert classify_risk(0.30) == "MODERATE"
    assert classify_risk(0.59) == "MODERATE"
    assert classify_risk(0.60) == "HIGH"
    assert classify_risk(0.79) == "HIGH"
    assert classify_risk(0.80) == "CRITICAL"
    assert classify_risk(0.95) == "CRITICAL"
