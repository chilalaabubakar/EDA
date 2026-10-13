"""Phase 3 (contribution) regression tests. Synthetic resource throughout."""
import numpy as np
import pytest

import final_cfg
from solar_resource import synthetic_years
from run_scenarios import make_load_builder
from sizing import size_system

RES = synthetic_years("rwanda")[2015]
KW = dict(pv_range=(10, 600), batt_range=(0, 2000))


@pytest.fixture(scope="module")
def setup():
    cfg = final_cfg.country_cfg("rwanda")
    b = make_load_builder(cfg, 300, 1.0, 0.0, 42)
    s, m, _ = size_system(cfg, b, RES, 300, **KW)
    return cfg, b, {**s, "households": 300}, m


# ------------------------------------------------------- operating subsidy
def test_operating_subsidy_solver_hits_target_irr(setup):
    from model import required_operating_subsidy
    cfg, b, s, _ = setup
    sub, irr = required_operating_subsidy(cfg, s, b, RES)
    assert sub is not None and sub > 0
    assert irr == pytest.approx(cfg["finance"]["target_irr"], abs=2e-3)


def test_capital_grant_reduces_but_does_not_remove_operating_subsidy(setup):
    from model import required_operating_subsidy
    cfg, b, s, _ = setup
    s0, _ = required_operating_subsidy(cfg, s, b, RES, grant_fraction=0.0)
    s95, _ = required_operating_subsidy(cfg, s, b, RES, grant_fraction=0.95)
    assert 0 < s95 < s0


def test_operating_subsidy_costing_outputs(setup):
    import operating_subsidy as O
    cfg, b, s, _ = setup
    out = O.cost(cfg, s, b, RES)
    assert out["opsub_grant0_usd_per_village_year1"] == pytest.approx(
        out["opsub_grant0_usd_per_conn_year"] * 300)
    # more non-renewable biomass -> more CO2 avoided -> cheaper per tonne
    assert out["usd_per_tco2_fnrb0.8"] < out["usd_per_tco2_fnrb0.1"]
    assert out["rwanda_rbf_per_connection_usd"] == "source needed"


def test_wood_parity_parameter():
    import operating_subsidy as O
    assert O.wood_kg_per_kwh() == pytest.approx(3.6 * 0.8 / (0.15 * 15.6))


# -------------------------------------------------- household band check
def test_household_monthly_preserves_village_totals(setup):
    import household_bands as H
    cfg, b, _, _ = setup
    hh = H.household_monthly(cfg, 300, 1.0, 0.0, 42)
    assert hh.sum() == pytest.approx((b.noncooking + b.cooking).sum(), rel=1e-6)


def test_telescopic_schedule_mean_household_understates_revenue(setup):
    """Rwanda's telescopic schedule is convex: Jensen says billing the mean
    household cannot exceed billing households individually."""
    import household_bands as H
    cfg, _, _, _ = setup
    df = H.check(cfg, 300, 0.0, 0.0, 42, years=(10,))
    assert df.bias_pct.iloc[0] <= 1e-9


def test_household_rates_exclude_zero_consumers():
    import household_bands as H
    df = H.check(final_cfg.country_cfg("kenya"), 300, 0.0, 0.0, 42, years=(1,))
    assert df.blended_rate_household_p10.iloc[0] > 0


# ------------------------------------------------------- peak and curtailment
def test_shifting_raises_coincident_peak():
    cfg = final_cfg.country_cfg("rwanda")
    a = make_load_builder(cfg, 300, 1.0, 0.0, 42)(1).max()
    b = make_load_builder(cfg, 300, 1.0, 0.5, 42)(1).max()
    assert b > a


# ----------------------------------------------------------------- Ringiti
def test_ringiti_benchmark_refuses_to_invent_the_installation():
    """Without published figures the comparison says so instead of guessing."""
    import ringiti
    blank = {k: None for k in ringiti.RINGITI_ACTUAL}
    df = ringiti.run(final_cfg.country_cfg("kenya"), synthetic_years("kenya")[2007],
                     actual=blank, penetrations=(1.0,), sizing_kw=KW)
    assert df.basis.str.contains("SOURCE NEEDED").any()


def test_ringiti_benchmark_uses_only_published_figures():
    import ringiti
    a = ringiti.RINGITI_ACTUAL
    assert a["source"] and a["pv_kw"] == 20.0 and a["connections"] == 140
    assert a["battery_kwh"] is None and a["tariff_usd_per_kwh"] is None   # unpublished
    df = ringiti.run(final_cfg.country_cfg("kenya"), synthetic_years("kenya")[2007],
                     penetrations=(1.0,), sizing_kw=KW).set_index("basis")
    inst = df.filter(like="installed", axis=0).iloc[0]
    assert inst.w_per_connection == pytest.approx(1000 * 20 / 140)
    # the most solar energy each customer could get, at the model's own yield
    assert inst.max_solar_kwh_per_connection_year == pytest.approx(
        20 * inst.ac_kwh_per_kw_year1 / 140)
    model = df.loc["model, eCooking 100%"]
    assert model.connections == 140 and model.pv_multiple_of_installed > 1


# ---------------------------------------------------------- household cost
def test_household_cost_includes_appliance_and_band_effect():
    import household_cost as HC
    cfg = final_cfg.country_cfg("rwanda")
    df = HC.compare(cfg, 6.0, 30.0).set_index("option")
    e = df.loc["electric (EPC)"]
    assert e.of_which_appliance > 0
    # telescopic: incremental rate on cooking kWh exceeds the lifeline rate
    assert e.incremental_rate_usd_kwh > cfg["tariff"]["bands"][0][1]
    assert df.loc["firewood, collected (cash)"].cash_usd_year == 0


def test_kenya_check_headline_column_matches_published_results():
    """kenya_ownership_check's "core" column is the published Kenyan headline;
    if it drifts, the robustness comparison in s4.5 is against the wrong base."""
    import pandas as pd
    from pathlib import Path
    R = Path(__file__).resolve().parents[1] / "results"
    if not (R / "kenya_ownership_check.csv").exists():
        pytest.skip("run `python src/pipeline.py kenya_check`")
    k = pd.read_csv(R / "kenya_ownership_check.csv").set_index("quantity")["core"]
    S = pd.read_csv(R / "scenarios_both.csv")
    flat = S[(S.site == "kenya") & (S.tariff == "flat") & S.feasible].sort_values("penetration")
    assert k["lcoe_no_cooking"] == pytest.approx(flat.lcoe.iloc[0], rel=1e-9)
    assert k["lcoe_full"] == pytest.approx(flat.lcoe.iloc[-1], rel=1e-9)
    D = pd.read_csv(R / "discount_sweep.csv")
    m = D[(D.site == "kenya") & (D.discount_rate == 0.12)].multiple_of_regulated.iloc[0]
    assert k["cost_reflective_multiple"] == pytest.approx(m, rel=1e-6)


# ------------------------------------------- island census check and phi share
def test_site_check_scales_only_census_items_and_caps_at_one():
    import site_ownership_check as S
    rw = final_cfg.country_cfg("rwanda")["appliances"]
    out = S.scaled_appliances(rw, "rwanda")
    r = S.ratios("rwanda")
    assert out["tv_colour"][0] == pytest.approx(rw["tv_colour"][0] * r["television"])
    assert out["mobile_charger"][0] == pytest.approx(min(1, rw["mobile_charger"][0] * r["mobile phone"]))
    assert out["cfl_bulb"] == rw["cfl_bulb"]                    # not in the census
    assert out["tv_colour"][1:] == rw["tv_colour"][1:]           # wattage and use unchanged
    big = {"radio": (0.99, 10, 60, "all")}
    assert S.scaled_appliances(big, "rwanda")["radio"][0] == 1.0
    assert rw["tv_colour"][0] == final_cfg.APPLIANCES_RWANDA["tv_colour"][0]   # no mutation


def test_daytime_share_of_cooking_rises_with_phi():
    import cooking_shift
    cfg = final_cfg.country_cfg("rwanda")
    a, b, c = (cooking_shift.daytime_share(cfg, 60, phi) for phi in (0.0, 0.3, 0.5))
    assert 0 < a < b < c < 1
