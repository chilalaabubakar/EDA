"""Phase 2 (defensibility) regression tests. Synthetic resource throughout:
these test behaviour, not the paper's numbers."""
import numpy as np
import pytest

import final_cfg
from solar_resource import synthetic_years
from run_scenarios import make_load_builder
from sizing import full_grid_search, size_system

YEARS = synthetic_years("rwanda")
RES = YEARS[2015]
KW = dict(pv_range=(10, 600), batt_range=(0, 2000))


@pytest.fixture(scope="module")
def cfg():
    return final_cfg.country_cfg("rwanda")


@pytest.fixture(scope="module")
def builder(cfg):
    return make_load_builder(cfg, 300, 1.0, 0.0, 42)


@pytest.fixture(scope="module")
def headline(cfg, builder):
    s, m, _ = size_system(cfg, builder, RES, 300, **KW)
    return s, m


# ------------------------------------------------------ inverter sized to load
def test_inverter_is_sized_to_load_not_pv(cfg, builder, headline):
    s, m = headline
    assert cfg["bos"]["inverter_sizing"] == "load"
    peak = builder(20).max()
    assert peak <= s["inverter_kw"] <= 1.25 * peak + 5
    assert s["inverter_kw"] != pytest.approx(s["pv_kw"] / cfg["bos"]["dc_ac_ratio"])
    assert s["inverter_limits_battery"]


# ------------------------------------------------------- staged / design year
def test_staged_design_meets_constraint_and_costs_less(cfg, builder, headline):
    import expansion
    st = expansion.size_staged(cfg, builder, RES, 300, sizing_kw=KW)
    from model import simulate
    _, m = simulate(cfg, st, builder, RES)
    assert m["worst_year_unmet_fraction"] <= 0.05 + 1e-12
    assert m["lcoe"] < headline[1]["lcoe"]
    a, b = st["stages"]
    assert b["from_year"] == cfg["battery"]["replacement_year"] + 1
    assert b["pv_kw"] >= a["pv_kw"]


def test_design_year_constraint_is_scoped_to_design_year(cfg, builder):
    s5, m5, _ = size_system(cfg, builder, RES, 300, design_year=5, **KW)
    assert max(m5["unmet_fraction_by_year"][:5]) <= 0.05 + 1e-12
    assert m5["worst_year_unmet_fraction"] > 0.05      # breaches later, by design


def test_expansion_capital_lands_the_year_before_the_stage(cfg, builder):
    from model import simulate
    s = {"pv_kw": 150.0, "battery_kwh": 400.0, "connections": 300}
    st = {**s, "stages": [{"from_year": 1, **s},
                          {"from_year": 11, "pv_kw": 250.0, "battery_kwh": 700.0}]}
    df, _ = simulate(cfg, st, builder, RES)
    add = df.set_index("year").capex_addition
    assert add[10] > 0 and add.drop(10).sum() == 0
    assert df.set_index("year").replacement[10] == pytest.approx(
        700 * cfg["capex"]["battery_per_kwh"])


def test_stage_must_start_after_battery_replacement(cfg, builder):
    from model import simulate
    s = {"pv_kw": 150.0, "battery_kwh": 400.0, "connections": 300}
    bad = {**s, "stages": [{"from_year": 1, **s}, {"from_year": 6, **s}]}
    with pytest.raises(ValueError):
        simulate(cfg, bad, builder, RES)


# ---------------------------------------------- search vs exhaustive full grid
def test_search_matches_full_grid_on_its_own_resolution(cfg, builder, headline):
    s, m = headline
    pv = np.arange(s["pv_kw"] - 25, s["pv_kw"] + 25 + 1e-9, 5.0)
    bt = np.arange(max(0, s["battery_kwh"] - 100), s["battery_kwh"] + 100 + 1e-9, 20.0)
    g, gm, _ = full_grid_search(cfg, builder, RES, 300, pv, bt)
    assert m["lcoe"] <= gm["lcoe"] + 1e-9


# ------------------------------------------------------- interannual variability
def test_interannual_outputs(cfg, builder, headline):
    import interannual
    summary, dist = interannual.run(cfg, headline[0], builder, YEARS, 2015, 300, KW)
    assert len(dist) == len(YEARS)
    assert summary["lcoe_p05"] <= summary["lcoe_median"] <= summary["lcoe_p95"]
    assert summary["ghi_spread_pct"] > 0


# ---------------------------------------------------------------- ensemble
def test_ensemble_summary_has_cis():
    import ensemble
    import pandas as pd
    df = pd.DataFrame({q: np.random.default_rng(0).normal(10, 1, 24)
                       for q in ensemble.QUANTITIES})
    s = ensemble.summarise(df).set_index("quantity")
    assert (s.ci95_lo < s["mean"]).all() and (s["mean"] < s.ci95_hi).all()
    assert (s.n_seeds == 24).all()


# ------------------------------------------------------------------ ToU sweep
def test_avoided_storage_is_a_step_function_of_discount(cfg):
    """Why '90 kWh per US cent' cannot stand: the modelled response is a step."""
    import tou_sweep
    df, _ = tou_sweep.sweep(cfg, RES, 300, 300, phis=(0.5,),
                            discounts=(0.0, 0.005, 0.02, 0.05), sizing_kw=KW)
    assert tou_sweep.is_step_function(df)
    assert df[df.discount == 0].avoided_battery_kwh.iloc[0] == 0
    # revenue cost grows with discount even though avoided storage does not
    pos = df[df.discount > 0].sort_values("discount")
    assert pos.operator_npv_gain.is_monotonic_decreasing


def test_elastic_response_does_scale_with_discount(cfg):
    import tou_sweep
    df, _ = tou_sweep.sweep(cfg, RES, 300, 300, phis=(0.5,), response="elastic",
                            discounts=(0.005, 0.02), d_sat=0.02, sizing_kw=KW)
    a, b = df.sort_values("discount").avoided_battery_kwh.values
    assert b > a


# ---------------------------------------------------------------- ESMAP
def test_esmap_components_sum_to_lcoe(cfg, builder, headline):
    import esmap
    c = esmap.lcoe_components(cfg, headline[0], builder, RES)
    assert c["total"] == pytest.approx(c["lcoe_check"], rel=1e-9)


def test_esmap_waterfall_moves_towards_benchmark(cfg, builder):
    import esmap
    wf = esmap.waterfall(cfg, builder, RES, 300, KW)
    assert wf.lcoe.is_monotonic_decreasing
