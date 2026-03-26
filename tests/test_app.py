import pytest
from app import categorize_risk

@pytest.mark.parametrize("days,expected", [
    (1, 'CRITICAL'),
    (5, 'HIGH'),
    (10, 'MEDIUM'),
    (20, 'LOW'),
    (None, 'UNKNOWN'),
])
def test_categorize_risk(days, expected):
    assert categorize_risk(days) == expected
