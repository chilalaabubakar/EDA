"""Tests for the changes made in answer to the review. Synthetic resource
throughout: these test behaviour, not the paper's numbers.

Each test names the review point it protects.
"""
import copy

import numpy as np
import pandas as pd
import pytest

import final_cfg
from model import (average_billed_rate, capex, required_operating_subsidy,
                   required_tariff, simulate)
from run_scenarios import anchor_profile, make_load_builder, scenario_row
from solar_resource import synthetic_years

RES = synthetic_years("rwanda")[2015]
KW = dict(pv_range=(10, 600), batt_range=(0, 2000))
N = 300


@pytest.fixture(scope="module")
def cfg():
    return final_cfg.country_cfg("rwanda")


@pytest.fixture(scope="module")
def full(cfg):
    """Base-case design with every household cooking."""
    import expansion
    b = make_load_builder(cfg, N, 1.0, 0.0, 42)
    s, m = expansion.size_design(cfg, b, RES, N, **KW)
    return b, {**s, "households": N}, m


@pytest.fixture(scope="module")
def none(cfg):
    import expansion
    b = make_load_builder(cfg, N, 0.0, 0.0, 42)
    s, m = expansion.size_design(cfg, b, RES, N, **KW)
    return b, {**s, "households": N}, m


# ------------------------------------------------ demand growth (point 5)
def test_cooking_energy_does_not_grow(cfg):
    """The same meals are cooked in year 20 as in year 1; only appliance
    demand grows."""
    b = make_load_builder(cfg, N, 1.0, 0.0, 42)
    assert cfg["demand"]["cooking_growth_rate"] == 0.0
    assert b.cooking_in_year(20).sum() == pytest.approx(b.cooking_in_year(1).sum())
    g = cfg["demand"]["annual_growth_rate"]
    assert b.noncooking_in_year(20).sum() == pytest.approx(
        b.noncooking.sum() * (1 + g) ** 19)
    assert b(20).sum() == pytest.approx(b.cooking.sum() + b.noncooking.sum() * (1 + g) ** 19)


def test_price_rise_no_longer_grows_with_assumed_cooking_growth(cfg):
    """A cooking household's monthly use in year 20 exceeds year 1 only by the
    growth in its appliance use."""
    from bands import monthly_kwh_per_household
    b1 = make_load_builder(cfg, N, 1.0, 0.0, 42)
    b0 = make_load_builder(cfg, N, 0.0, 0.0, 42)
    extra = monthly_kwh_per_household(b1, 20, N) - monthly_kwh_per_household(b1, 1, N)
    appliance = monthly_kwh_per_household(b0, 20, N) - monthly_kwh_per_household(b0, 1, N)
    assert extra == pytest.approx(appliance, rel=1e-9)


# --------------------------------------------- base case build (point 4)
def test_base_case_is_a_two_stage_build(cfg, full):
    _, s, m = full
    assert cfg["sizing"]["build"] == "staged"
    first, second = s["stages"]
    assert second["from_year"] == cfg["battery"]["replacement_year"] + 1
    assert second["pv_kw"] >= first["pv_kw"]
    assert m["worst_year_unmet_fraction"] <= cfg["reliability"]["max_unmet_demand_fraction"] + 1e-12


def test_scenario_rows_carry_both_stages_and_rebuild(cfg):
    from viability import sizing_from_row
    r = scenario_row(cfg, RES, N, N, 1.0, 0.0, "flat", 0.0, 42, sizing_kw=KW)
    assert r["pv_kw_stage2"] >= r["pv_kw"]
    assert r["battery_kwh_bought"] == r["battery_kwh"] + r["battery_kwh_stage2"]
    s = sizing_from_row(pd.Series(r), N, N)
    b = make_load_builder(cfg, N, 1.0, 0.0, 42)
    _, m = simulate(cfg, s, b, RES)
    assert m["lcoe"] == pytest.approx(r["lcoe"], rel=1e-9)


def test_operating_cost_grows_with_the_plant_and_not_with_time(cfg, full, none):
    """Operating cost is no longer fixed per connection, and it does not rise
    in real terms."""
    assert cfg["opex"]["basis"] == "split" and cfg["opex"]["escalation_rate"] == 0.0
    df1, _ = simulate(cfg, full[1], full[0], RES)
    df0, _ = simulate(cfg, none[1], none[0], RES)
    assert df1.opex.iloc[0] > df0.opex.iloc[0]              # bigger plant, more upkeep
    customer = cfg["opex"]["per_customer_year"] * N
    assert df0.opex.iloc[0] > customer
    # within a stage the cost is flat; it steps up only when the plant is enlarged
    assert df1.opex.iloc[:10].nunique() == 1 and df1.opex.iloc[10:].nunique() == 1
    assert df1.opex.iloc[-1] >= df1.opex.iloc[0]


def test_base_case_has_no_generator(cfg, full):
    _, s, m = full
    assert "generator_kw" not in s and m["generator_share"] == 0.0
    _, items = capex(cfg, s)
    assert "generator" not in items


def test_backup_generator_serves_what_solar_and_battery_cannot(cfg):
    import sensitivity
    b = make_load_builder(cfg, N, 1.0, 0.0, 42)
    s, m = sensitivity.size_hybrid(cfg, b, RES, N, coarse=(50.0, 200.0), fine=(25.0, 100.0))
    assert s["generator_kw"] >= b(20).max()
    assert m["worst_year_unmet_fraction"] == pytest.approx(0.0, abs=1e-9)
    assert 0.0 < m["generator_share"] < 1.0
    df, _ = simulate(cfg, s, b, RES)
    g = cfg["generator"]
    assert df.extra_opex.sum() == pytest.approx(
        df.generator_kwh.sum() * (g["fuel_l_per_kwh"] * g["fuel_price_per_l"] + g["om_per_kwh"]))
    # dearer fuel can only raise the cost of the same design
    c2 = copy.deepcopy(cfg)
    c2["generator"]["fuel_price_per_l"] = 2 * g["fuel_price_per_l"]
    assert simulate(c2, s, b, RES)[1]["lcoe"] > m["lcoe"]


def test_anchor_customer_is_billed_at_its_own_rate(cfg, full):
    b, s, _ = full
    prof = anchor_profile(120.0)
    assert prof.sum() == pytest.approx(120.0 * 6 / 7 * 365, rel=0.01)
    assert prof[(np.arange(8760) % 24) < 8].sum() == 0
    ba = make_load_builder(cfg, N, 1.0, 0.0, 42, anchor_kwh_day=120.0)
    assert ba(1).sum() == pytest.approx(b(1).sum() + prof.sum())
    import expansion
    sa, _ = expansion.size_design(cfg, ba, RES, N, **KW)     # sized for the anchor too
    sa = {**sa, "households": N}
    dfa, _ = simulate(cfg, sa, ba, RES)
    df, _ = simulate(cfg, s, b, RES)
    # households are billed on their own use, so the anchor does not move them
    # into a higher band
    assert average_billed_rate(cfg, sa, ba, RES) == pytest.approx(
        average_billed_rate(cfg, s, b, RES), rel=0.03)
    assert (dfa.revenue - dfa.revenue_households).iloc[0] > 0
    assert (df.revenue - df.revenue_households).abs().max() == pytest.approx(0.0, abs=1e-9)


# ------------------------------------- finance conventions (reconciliation)
def test_break_even_tariff_is_cost_over_collection(cfg, full):
    """Target return = discount rate, so the flat tariff that breaks even is
    the levelised cost divided by the share of bills collected."""
    b, s, m = full
    assert cfg["finance"]["target_irr"] == cfg["finance"]["discount_rate_real"]
    tar, _ = required_tariff(cfg, s, b, RES)
    assert tar == pytest.approx(m["lcoe"] / cfg["tariff"]["collection_rate"], rel=2e-3)


def test_subsidy_is_level_and_closes_the_loss(cfg, full):
    b, s, m = full
    sub, irr = required_operating_subsidy(cfg, s, b, RES)
    seen = []
    simulate(cfg, s, b, RES, operating_subsidy=lambda y: seen.append(y) or sub * N)
    df, m2 = simulate(cfg, s, b, RES, operating_subsidy=lambda y: sub * N)
    assert df.operating_subsidy.nunique() == 1               # same amount every year
    assert m2["npv"] == pytest.approx(0.0, abs=0.002 * abs(m["npv"]))


def test_no_subsidy_is_reported_when_the_tariff_already_pays(cfg, full):
    b, s, m = full
    c = copy.deepcopy(cfg)
    c["tariff"].update(flat_rate_per_kwh=3 * m["lcoe"], bands=None)
    sub, _ = required_operating_subsidy(c, s, b, RES)
    assert sub == 0.0


# --------------------------------------------- burden measure (point 3)
def test_incremental_subsidy_per_cooking_household(cfg, full, none):
    import operating_subsidy as O
    designs = {0.0: (none[1], none[0]), 1.0: (full[1], full[0])}
    bd = O.by_adoption(cfg, "rwanda", designs, RES, N).set_index("penetration")
    assert np.isnan(bd.loc[0.0, "incremental_usd_per_cooking_hh_year"])
    assert bd.loc[1.0, "incremental_usd_per_cooking_hh_year"] == pytest.approx(
        bd.loc[1.0, "opsub_usd_per_conn_year"] - bd.loc[0.0, "opsub_usd_per_conn_year"])
    # cooking lowers the cost per kWh and still enlarges the loss
    assert bd.loc[1.0, "lcoe"] < bd.loc[0.0, "lcoe"]
    assert bd.loc[1.0, "npv"] < bd.loc[0.0, "npv"]
    # it is sold below what it costs to supply
    assert bd.loc[1.0, "incremental_cost_per_cooking_kwh"] > bd.loc[1.0, "avg_price_paid"]


def test_carbon_uses_the_increment_and_two_wood_estimates(cfg, full, none):
    import operating_subsidy as O
    designs = {0.0: (none[1], none[0]), 1.0: (full[1], full[0])}
    bd = O.by_adoption(cfg, "rwanda", designs, RES, N)
    row = bd[bd.penetration == 1.0].iloc[0]
    c = O.carbon(row)
    assert set(c.wood_basis) == {"useful_energy", "cdm_default"}
    assert (c.incremental_usd_per_cooking_hh_year == row.incremental_usd_per_cooking_hh_year).all()
    # more wood displaced, or more of it non-renewable, means cheaper per tonne
    a = c[c.wood_basis == "useful_energy"].set_index("fnrb").usd_per_tco2
    d = c[c.wood_basis == "cdm_default"].set_index("fnrb").usd_per_tco2
    assert (d < a).all() and a.loc[0.8] < a.loc[0.1]
    assert c[c.wood_basis == "cdm_default"].wood_t_per_cooking_hh_year.iloc[0] == pytest.approx(2.0)


# ------------------------------------------- tariff scenarios (points 1, 2)
def test_a_higher_site_tariff_shrinks_the_subsidy_and_raises_the_bill(cfg):
    from viability import SITE_TARIFFS, tariff_scenarios
    rows = [dict(scenario_row(cfg, RES, N, N, pen, 0.0, "flat", 0.0, 42, sizing_kw=KW),
                 site="rwanda") for pen in (0.0, 1.0)]
    t = tariff_scenarios(pd.DataFrame(rows), {"rwanda": RES}, N, N).set_index("tariff")
    names = ["national tariff", *SITE_TARIFFS, "break-even tariff"]
    assert list(t.index) == names
    assert t.opsub_usd_per_conn_year.is_monotonic_decreasing
    assert t.bill_month_cooking.is_monotonic_increasing
    assert t.loc["break-even tariff", "opsub_usd_per_conn_year"] == pytest.approx(0.0, abs=1.0)
    assert t.loc["national tariff", "bill_multiple_of_national"] == pytest.approx(1.0)
    # cooking adds less to the subsidy the more it is charged
    assert t.incremental_usd_per_cooking_hh_year.is_monotonic_decreasing


# ------------------------------------------------ uncertainty (point 7)
def test_sensitivity_cases_move_the_right_inputs(cfg):
    import sensitivity as S
    names = [c[0] for c in S.cases(cfg)]
    for needed in ("Capital cost", "Appliance demand growth", "Bills collected",
                   "Energy per meal", "Discount rate"):
        assert needed in names
    lo = dict((c[0], c[2][0]) for c in S.cases(cfg))
    assert lo["Capital cost"]["capex"]["pv_per_kw"] == pytest.approx(0.7 * cfg["capex"]["pv_per_kw"])
    assert lo["Discount rate"]["finance"]["target_irr"] == lo["Discount rate"]["finance"]["discount_rate_real"]
    assert cfg["capex"]["pv_per_kw"] == final_cfg.BASE_CFG["capex"]["pv_per_kw"]   # base untouched


def test_previous_base_case_is_recoverable(cfg):
    import sensitivity as S
    p = S.previous_base(cfg)
    assert p["sizing"]["build"] == "single"
    assert p["demand"]["cooking_growth_rate"] == 0.05 and p["opex"]["escalation_rate"] == 0.05
    assert p["finance"]["target_irr"] == pytest.approx(cfg["finance"]["discount_rate_real"] + 0.03)
    assert cfg["sizing"]["build"] == "staged"


# ---------------------------------------- daytime discount (point 2, Fig. 4)
def test_break_even_discount_uses_up_the_gain(cfg):
    """At the break-even discount the operator is no better off than under
    the flat tariff."""
    import ensemble
    r = ensemble.one_seed(cfg, RES, N, N, 3, phis=(0.5,), sizing_kw=KW)
    d = r["break_even_discount_phi50"]
    cache = {}
    flat = scenario_row(cfg, RES, N, N, 1.0, 0.0, "flat", 0.0, 3, sizing_kw=KW, sizing_cache=cache)
    tou = scenario_row(cfg, RES, N, N, 1.0, 0.5, "tou", d, 3, sizing_kw=KW, sizing_cache=cache)
    assert tou["npv"] == pytest.approx(flat["npv"], abs=0.01 * abs(r["npv_gain_no_discount_phi50"]) + 1.0)
    assert r["incremental_usd_per_cooking_hh_year"] == pytest.approx(r["opsub_full"] - r["opsub_zero"])


# -------------------------------------------------- validation (point 6)
def test_table2_separates_calibration_from_checks():
    from manuscript_tables import table2
    from validate_cooking import validation_summary
    t = table2(validation_summary(300, seeds=range(2))).set_index("Quantity")
    assert t.loc["Diversity factor of cooking", "Status"] == "Calibration target"
    assert t.loc["Hour of the cooking peak", "Status"] == "Input"
    assert t.loc["Daily cooking energy per household", "Status"] == "Independent check"


def test_simulated_meal_energy_exceeds_the_drawn_mean():
    """Meals shorter than 20 minutes are lengthened to 20, so the simulated
    mean per meal (0.40 kWh) is above the 0.35 kWh drawn. The paper reports
    the simulated figure."""
    from validate_cooking import validation_summary
    v = validation_summary(300, seeds=range(3)).mean(numeric_only=True)
    assert v.kwh_per_meal_simulated > v.kwh_per_meal_drawn
    assert v.daily_kwh_per_hh == pytest.approx(v.kwh_per_meal_simulated * v.meals_per_day)
