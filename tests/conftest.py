import pytest


@pytest.fixture
def healthy_row():
    """
    Factory for a baseline truck row where none of the 18 rules should fire.
    Each rule test overrides only the field(s) relevant to that rule, so a
    failing assertion points at exactly one rule instead of an opaque dict.
    """
    def _make(**overrides):
        row = {
            "vehicle_id": "TEST-001",
            "engine_family": "DETROIT",
            "regen_active": 1,
            "dpf_outlet_temp_active_regen_f": 1000,   # >= REGEN_OUTLET_CRITICAL_F (1000), < REGEN_ACTIVE_OUTLET_WATCH_HIGH_F (1160)
            "dpf_outlet_temp_peak_f": 1050,            # under every family's high-critical
            "dpf_inlet_temp_f": 1010,                  # within 100°F of outlet
            "regen_count_7d": 1,                       # <= 2
            "back_pressure_inh2o": 2.0,                # <= 4.0 critical
        }
        row.update(overrides)
        return row
    return _make
