"""The compiled dispatch kernel must reproduce the reference loop exactly.

model._dispatch_kernel replaces the v4 class-based hourly loop for speed. The
v4 loop is kept as model.dispatch_year_reference and serves as the oracle.
"""
import copy

import numpy as np
import pytest

import model
from model import Battery, dispatch_year, dispatch_year_reference
from test_model import CFG, BASE, make_resource


@pytest.mark.parametrize("limit_batt", [False, True])
@pytest.mark.parametrize("pv_kw,batt_kwh", [(150, 400), (40, 900), (400, 50),
                                            (0, 300), (200, 0)])
def test_kernel_matches_reference_over_three_years(pv_kw, batt_kwh, limit_batt):
    r = make_resource(3)
    sizing = {"pv_kw": pv_kw, "battery_kwh": batt_kwh, "connections": 240,
              "inverter_limits_battery": limit_batt}
    if limit_batt:
        sizing["inverter_kw"] = 60.0
    fast, slow = Battery.from_cfg(CFG, batt_kwh), Battery.from_cfg(CFG, batt_kwh)
    for y in (1, 2, 3):
        load = np.tile(BASE * 300, 365) * 1.05 ** (y - 1)
        a = dispatch_year(load, r["ghi"], r["tair"], CFG, sizing, fast, y)
        b = dispatch_year_reference(load, r["ghi"], r["tair"], CFG, sizing, slow, y)
        for k in ("served", "unmet", "pv_to_load", "batt_to_load", "curtailed"):
            np.testing.assert_allclose(a[k], b[k], rtol=0, atol=1e-9, err_msg=k)
        for attr in ("soc", "cumulative_discharge", "energy_in", "energy_out"):
            assert getattr(fast, attr) == pytest.approx(getattr(slow, attr),
                                                        abs=1e-7), attr


def test_hybrid_inverter_caps_total_ac_output():
    r = make_resource(1)
    sizing = {"pv_kw": 300, "battery_kwh": 800, "connections": 240,
              "inverter_kw": 25.0, "inverter_limits_battery": True}
    load = np.tile(BASE * 300, 365)
    out = dispatch_year(load, r["ghi"], r["tair"], CFG, sizing,
                        Battery.from_cfg(CFG, 800), 1)
    assert (out["pv_to_load"] + out["batt_to_load"]).max() <= 25.0 + 1e-9


def test_numba_is_active():
    """Not required for correctness, but the Phase 2 ensembles assume it."""
    assert model.HAVE_NUMBA
