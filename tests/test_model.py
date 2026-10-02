"""Verification suite for src/model.py. Run: python -m pytest tests -q

Each test corresponds to a defect found in the original assignment code.
If one of these fails, a paper-grade claim is no longer supported.
"""
import sys, copy
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import Battery, simulate, tariff_revenue, HOURS   # noqa: E402


CFG = {
    "pv": {"temp_coeff_per_c": -0.004, "noct_c": 45, "derate_factor": 0.85,
           "degradation_rate": 0.008},
    "battery": {"round_trip_efficiency": 0.90, "depth_of_discharge": 0.80,
                "cycle_life": 3000, "replacement_year": 10,
                "start_soc_fraction": 0.5, "max_c_rate": 0.5,
                "eol_capacity_loss": 0.2},
    "bos": {"inverter_eff": 0.97, "dc_ac_ratio": 1.2},
    "capex": {"pv_per_kw": 900, "battery_per_kwh": 350,
              "inverter_per_kw": 300, "connection_per_customer": 250,
              "soft_cost_fraction": 0.15},
    # These tests are about battery physics, energy balance and tariffs, not
    # about the OPEX basis, so they keep the original capex_fraction basis.
    # It is now named explicitly because model.py refuses to guess.
    "opex": {"basis": "capex_fraction",
             "om_fraction_of_capex_per_year": 0.03, "staff_annual": 3000,
             "escalation_rate": 0.03},
    "finance": {"discount_rate_real": 0.12, "tax_rate": 0.0,
                "project_life_years": 20},
    "tariff": {"flat_rate_per_kwh": 0.60, "daytime_discount_per_kwh": 0.10,
               "daytime_window_hours": [9, 16], "collection_rate": 0.95},
}
SIZING = {"pv_kw": 150, "battery_kwh": 400, "connections": 240}


def make_resource(seed=42):
    rng = np.random.default_rng(seed)
    h = np.arange(HOURS) % 24
    ghi = np.clip(np.sin((h - 6) / 12 * np.pi), 0, None) * 950 * (1 - 0.25 * rng.random(HOURS))
    tair = 22 + 6 * np.clip(np.sin((h - 7) / 12 * np.pi), 0, None)
    return {"ghi": ghi, "tair": tair}


BASE = np.array([.01,.01,.01,.01,.02,.04,.06,.05,.03,.02,.02,.02,
                 .02,.02,.02,.02,.04,.08,.15,.18,.10,.04,.02,.01])


def loads(y):
    return np.tile(BASE * 300, 365) * (1.05 ** (y - 1))


# --------------------------------------------------- fix 2: battery physics
def test_round_trip_efficiency_is_exact():
    b = Battery(100, rte=0.90, dod=0.80); b.soc = 0
    took = b.charge(50)
    got = b.discharge(1e6)
    assert took == pytest.approx(50, rel=1e-9)
    assert got / took == pytest.approx(0.90, rel=1e-6)


def test_depth_of_discharge_floor_respected():
    b = Battery(100, rte=1.0, dod=0.80)
    b.soc = b.usable
    total = sum(b.discharge(1e6) for _ in range(50))
    assert total <= b.usable + 1e-9, "delivered more than the usable window"
    assert b.soc >= -1e-9


def test_cannot_charge_beyond_usable_capacity():
    b = Battery(100, rte=1.0, dod=0.80); b.soc = 0
    for _ in range(50):
        b.charge(1e6)
    assert b.soc <= b.usable + 1e-9


def test_c_rate_limits_power():
    b = Battery(100, rte=1.0, dod=0.80, max_c_rate=0.5)
    b.soc = b.usable
    assert b.discharge(1e6) <= 50 + 1e-9


def test_fade_is_applied_not_merely_computed():
    b = Battery(10, rte=1.0, dod=0.80, cycle_life=1)
    cap0 = b.effective_capacity()
    for _ in range(200):
        b.soc = b.effective_capacity()
        b.discharge(1e6)
    assert b.fade > 0.5
    assert b.effective_capacity() < cap0, "fade computed but capacity unchanged"


def test_soc_clamped_when_fade_shrinks_capacity():
    b = Battery(10, rte=1.0, dod=0.80, cycle_life=1)
    b.soc = b.usable
    b.cumulative_discharge = b.throughput_limit      # force full fade
    b._clamp()
    assert b.soc <= b.effective_capacity() + 1e-9


def test_battery_physically_replaced_not_just_expensed():
    df, _ = simulate(CFG, SIZING, loads, make_resource())
    ry = CFG["battery"]["replacement_year"]
    before = df.loc[df.year == ry, "battery_fade"].iloc[0]
    after = df.loc[df.year == ry + 1, "battery_fade"].iloc[0]
    assert after < before, "fade did not reset after replacement"


# ------------------------------------------------------ fix 1: no global state
def test_simulate_does_not_mutate_its_inputs():
    cfg, sizing = copy.deepcopy(CFG), copy.deepcopy(SIZING)
    simulate(cfg, sizing, loads, make_resource())
    assert cfg == CFG and sizing == SIZING, "simulate mutated caller state"


def test_scenarios_are_independent():
    """Two sizings run in either order must give identical results."""
    r = make_resource()
    a1, _ = simulate(CFG, {**SIZING, "battery_kwh": 200}, loads, r)
    b1, _ = simulate(CFG, {**SIZING, "battery_kwh": 600}, loads, r)
    b2, _ = simulate(CFG, {**SIZING, "battery_kwh": 600}, loads, r)
    a2, _ = simulate(CFG, {**SIZING, "battery_kwh": 200}, loads, r)
    assert a1.served_kwh.sum() == pytest.approx(a2.served_kwh.sum())
    assert b1.served_kwh.sum() == pytest.approx(b2.served_kwh.sum())


# ------------------------------------------------------------ energy balance
def test_energy_balance_closes():
    _, m = simulate(CFG, SIZING, loads, make_resource())
    assert m["max_balance_residual_kw"] < 1e-6, "supply + unmet != demand"


def test_no_energy_created_by_battery():
    """Cumulative output must be strictly less than input: losses are real."""
    b = Battery(100, rte=0.90, dod=0.80); b.soc = 0
    for _ in range(500):
        b.charge(20); b.discharge(18)
    assert b.energy_out < b.energy_in, "battery returned more than it absorbed"
    realised = b.energy_out / b.energy_in
    assert realised == pytest.approx(0.90, abs=0.02), (
        f"realised round-trip efficiency {realised:.3f} != 0.90")


# --------------------------------------------------------- fix 3: wind gone
def test_wind_component_removed():
    import model
    assert not hasattr(model, "WindGenerator")


# --------------------------------------------------------- fix 4: LCOE exists
def test_lcoe_present_and_plausible():
    _, m = simulate(CFG, SIZING, loads, make_resource())
    assert "lcoe" in m and 0.05 < m["lcoe"] < 5.0


def test_lcoe_rises_when_capex_rises():
    cfg2 = copy.deepcopy(CFG); cfg2["capex"]["pv_per_kw"] *= 2
    _, a = simulate(CFG, SIZING, loads, make_resource())
    _, b = simulate(cfg2, SIZING, loads, make_resource())
    assert b["lcoe"] > a["lcoe"]


def test_lcoe_independent_of_tariff():
    """LCOE is a cost metric. Changing price must not move it."""
    _, a = simulate(CFG, SIZING, loads, make_resource(), tariff_mode="flat")
    _, b = simulate(CFG, SIZING, loads, make_resource(), tariff_mode="tou")
    assert a["lcoe"] == pytest.approx(b["lcoe"])


# ------------------------------------------------------- fix 5: tariffs, seeds
def test_tou_discount_reduces_revenue_when_nothing_shifts():
    served = np.tile(BASE * 300, 365)
    flat = tariff_revenue(served, CFG, "flat")
    tou = tariff_revenue(served, CFG, "tou")
    assert tou < flat, "ToU must cost revenue absent a behavioural response"


def test_tou_equals_flat_at_zero_discount():
    cfg2 = copy.deepcopy(CFG); cfg2["tariff"]["daytime_discount_per_kwh"] = 0.0
    served = np.tile(BASE * 300, 365)
    assert tariff_revenue(served, cfg2, "tou") == pytest.approx(
        tariff_revenue(served, cfg2, "flat"))


def test_discount_applies_only_inside_the_window():
    lo, hi = CFG["tariff"]["daytime_window_hours"]
    night = np.zeros(HOURS); night[(np.arange(HOURS) % 24) == (lo - 1)] = 1.0
    assert tariff_revenue(night, CFG, "tou") == pytest.approx(
        tariff_revenue(night, CFG, "flat"))
    day = np.zeros(HOURS); day[(np.arange(HOURS) % 24) == lo] = 1.0
    assert tariff_revenue(day, CFG, "tou") < tariff_revenue(day, CFG, "flat")


def test_deterministic_given_same_inputs():
    r = make_resource(seed=7)
    _, a = simulate(CFG, SIZING, loads, r)
    _, b = simulate(CFG, SIZING, loads, r)
    assert a["lcoe"] == pytest.approx(b["lcoe"])
    assert a["npv"] == pytest.approx(b["npv"])


def test_seeded_resource_is_reproducible():
    assert np.array_equal(make_resource(11)["ghi"], make_resource(11)["ghi"])
    assert not np.array_equal(make_resource(11)["ghi"], make_resource(12)["ghi"])


# ------------------------------------------------------------- sanity checks
def test_more_battery_reduces_unmet_demand():
    r = make_resource()
    _, small = simulate(CFG, {**SIZING, "battery_kwh": 100}, loads, r)
    _, big = simulate(CFG, {**SIZING, "battery_kwh": 800}, loads, r)
    assert big["unmet_fraction"] <= small["unmet_fraction"]


def test_zero_pv_and_zero_battery_serves_nothing():
    _, m = simulate(CFG, {"pv_kw": 0, "battery_kwh": 0,
                          "connections": 240}, loads, make_resource())
    assert m["unmet_fraction"] == pytest.approx(1.0)


# ============================ load builder =================================
from load_builder import (build_cooking_load, cooking_daypart_shares,   # noqa: E402
                          MEASURED_DAYPART, CookingParams)


def test_cooking_baseline_reproduces_measured_daypart_split():
    """phi=0 must return the Kenya MTF split. This is calibration, not an
    independent validation - the sampler draws from these probabilities."""
    s = cooking_daypart_shares(build_cooking_load(300, 1.0, 0.0, seed=1))
    for part, target in MEASURED_DAYPART.items():
        assert s[part] == pytest.approx(target, abs=0.02)


def test_phi_moves_energy_from_evening_to_afternoon():
    a = cooking_daypart_shares(build_cooking_load(300, 1.0, 0.0, seed=1))
    b = cooking_daypart_shares(build_cooking_load(300, 1.0, 0.5, seed=1))
    assert b["afternoon"] > a["afternoon"]
    assert b["evening"] < a["evening"]
    assert b["morning"] == pytest.approx(a["morning"], abs=0.02)


def test_phi_conserves_total_cooking_energy():
    """Shifting moves energy in time; it must not create or destroy it."""
    a = build_cooking_load(300, 1.0, 0.0, seed=1).sum()
    b = build_cooking_load(300, 1.0, 0.5, seed=1).sum()
    assert b == pytest.approx(a, rel=0.05)


def test_penetration_scales_cooking_energy():
    half = build_cooking_load(300, 0.5, 0.0, seed=1).sum()
    full = build_cooking_load(300, 1.0, 0.0, seed=1).sum()
    assert half == pytest.approx(full / 2, rel=0.08)
    assert build_cooking_load(300, 0.0, 0.0, seed=1).sum() == 0.0


def test_cooking_diversity_factor_is_realistic():
    """Aggregate peak must sit far below summed appliance ratings - the MECS
    diversity finding. A naive scaled average profile would fail this."""
    n, p = 300, CookingParams()
    load = build_cooking_load(n, 1.0, 0.0, seed=1)
    diversity = load.max() / (n * p.epc_power_kw)
    assert 0.02 < diversity < 0.35, f"implausible diversity factor {diversity:.3f}"


def test_cooking_load_is_reproducible():
    assert np.array_equal(build_cooking_load(100, 1.0, 0.2, seed=5),
                          build_cooking_load(100, 1.0, 0.2, seed=5))
    assert not np.array_equal(build_cooking_load(100, 1.0, 0.2, seed=5),
                              build_cooking_load(100, 1.0, 0.2, seed=6))
