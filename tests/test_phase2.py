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
    summary, dist = interannual.run(cfg, headline[0], builder, YEARS, 2015, 2010, 300, KW)
    assert len(dist) == len(YEARS)
    assert summary["lcoe_p05"] <= summary["lcoe_median"] <= summary["lcoe_p95"]
    assert summary["ghi_spread_pct"] > 0
    assert summary["design_year"] == 2015 and summary["median_year"] == 2010
    assert summary["median_binding_year"] in YEARS


def test_binding_year_is_the_year_with_most_unmet_demand():
    import pandas as pd
    import interannual
    d = pd.DataFrame({"weather_year": [2005, 2006, 2007],
                      "worst_year_unmet_fraction": [0.04, 0.07, 0.05]})
    assert interannual.binding_year(d) == 2006


def test_design_year_comes_from_params_with_median_fallback():
    import types
    from pipeline import Ctx
    ctx = Ctx(types.SimpleNamespace(params="params.yaml", synthetic=True, results=None,
                                    quick=True))
    for site in ctx.sites:
        assert ctx.design_year(site) in ctx.all_years(site)
    c = ctx.params["countries"]["rwanda"]
    ctx.params["countries"]["rwanda"] = {k: v for k, v in c.items() if k != "design_year"}
    assert ctx.design_year("rwanda") == c["representative_year"]


# ------------------------------------------------ the fine window keeps moving
def test_search_result_is_a_local_optimum_in_pv(cfg, builder, headline):
    """No neighbouring PV size, with any battery the fine grid allows, is
    cheaper. Before the window re-centred, the Kenya check stopped on the
    window edge 1.3% above the full-grid optimum."""
    s, m = headline
    for pv in (s["pv_kw"] - 5.0, s["pv_kw"] + 5.0):
        bt = np.arange(max(0, s["battery_kwh"] - 100), s["battery_kwh"] + 200 + 1e-9, 20.0)
        g, gm, _ = full_grid_search(cfg, builder, RES, 300, [pv], bt)
        assert gm is None or m["lcoe"] <= gm["lcoe"] + 1e-9


def test_window_recentres_when_the_coarse_optimum_is_off(cfg, monkeypatch):
    """A cost surface with a known optimum and a coarse screen biased towards
    large PV, as the end-of-life screen is in the Kenya check. Without
    re-centring the search stops on the window edge; with it, it reaches the
    full-grid optimum."""
    import sizing

    need = lambda pv: 100_000.0 / pv                       # battery for 5% unmet

    def fake_sim(cfg, s, builder, res, tariff_mode="flat"):
        u = 0.0 if s["battery_kwh"] >= need(s["pv_kw"]) - 1e-9 else 0.10
        return None, {"lcoe": (s["pv_kw"] + 0.3 * s["battery_kwh"]) / 1000, "npv": 0.0,
                      "unmet_fraction": u, "worst_year_unmet_fraction": u,
                      "unmet_fraction_by_year": [u] * 20}

    def biased_screen(cfg, s, builder, res, dy, fade=1.0):   # 2x too strict below 250 kW
        k = 2.0 if s["pv_kw"] < 250 else 1.0
        return 0.0 if s["battery_kwh"] >= k * need(s["pv_kw"]) else 0.10

    monkeypatch.setattr(sizing, "simulate", fake_sim)
    monkeypatch.setattr(sizing, "design_year_unmet", biased_screen)
    monkeypatch.setattr(sizing, "inverter_for", lambda *a, **k: {})
    kw = dict(pv_range=(10, 600), batt_range=(0, 2000))
    _, stuck, _ = sizing.size_system(cfg, None, None, 300, max_recentre=0, **kw)
    _, found, _ = sizing.size_system(cfg, None, None, 300, **kw)
    _, grid, _ = sizing.full_grid_search(cfg, None, None, 300, np.arange(10, 600.1, 5.0),
                                         np.arange(0, 2000.1, 20.0))
    assert stuck["lcoe"] > grid["lcoe"] + 1e-6          # the old behaviour
    assert found["lcoe"] == pytest.approx(grid["lcoe"])


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


def test_published_designs_hold_in_every_weather_year():
    """Sized on the design weather year, each headline system keeps unserved
    demand within the limit in every project year under all 20 weather years;
    the median-year design, kept as the comparison, does not."""
    import pandas as pd
    from pathlib import Path
    R = Path(__file__).resolve().parents[1] / "results" / "interannual_summary.csv"
    if not R.exists():
        pytest.skip("run `python src/pipeline.py interannual`")
    s = pd.read_csv(R)
    if "design_year" not in s:
        pytest.skip("interannual_summary.csv predates the design-year change")
    assert (s.weather_years_breaching == 0).all()
    assert (s.worst_year_unmet_max_over_weather <= 0.05 + 1e-12).all()
    assert (s.median_weather_years_breaching > 0).all()
    assert (s.median_lcoe < s.lcoe_design_year).all()
