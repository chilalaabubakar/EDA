"""Robustness: Kenya's headline results under the two ownership questions.

The Kenya MTF survey records appliance ownership twice for the same rural,
grid-connected households (n = 521): the M3 asset flags and the
core multi-select m_m_3_group, which reports 3 to 10 times higher ownership
(src/mtf_checks.py). The headline uses the core question; this reruns the
Kenyan headline numbers with each and writes them side by side.

    python src/pipeline.py kenya_check     ->  results/kenya_ownership_check.csv
"""
import pandas as pd

from bands import _band_rate, monthly_kwh_per_household
from final_cfg import country_cfg
from model import average_billed_rate, required_tariff
import operating_subsidy
from run_scenarios import make_load_builder, run, substitution_frontier
from viability import sizing_from_row

SOURCES = {"m3": "M3 asset flags", "core": "core multi-select (headline)",
           "core_2022": "core, five more years of growth"}
# The survey ran 2016-18; five years of the model's own 5% a year demand growth
# brings it to 2022. Rural ownership did rise: television 26.9% (2019 census,
# KNBS Vol. IV Table 2.36) to 38% (2022 KDHS summary report), radio 58.5% to 62%.
SURVEY_AGE_YEARS = 5


def _aged(cfg, years):
    import copy
    g = (1 + cfg["demand"]["annual_growth_rate"]) ** years
    out = copy.deepcopy(cfg)
    out["appliances"] = {k: (min(1.0, v[0] * g),) + tuple(v[1:])
                         for k, v in cfg["appliances"].items()}
    return out


def headline(source, resource, n_households, connections, seed=42):
    if source == "core_2022":
        cfg = _aged(country_cfg("kenya", kenya_source="core"), SURVEY_AGE_YEARS)
    else:
        cfg = country_cfg("kenya", kenya_source=source)
    return headline_for(cfg, resource, n_households, connections, seed)


def headline_for(cfg, resource, n_households, connections, seed=42):
    """The headline numbers for any country config (also used by
    site_ownership_check)."""
    S = run(cfg, resource, n_households, connections, seed=seed, verbose=False)
    flat = S[(S.tariff == "flat") & S.feasible].drop_duplicates("penetration") \
        .set_index("penetration").sort_index()
    F = substitution_frontier(S)
    F = F[(F.penetration == F.penetration.max()) & (F.discount == F.discount.max())]
    top = F.sort_values("phi").iloc[-1]

    pen = flat.index.max()
    sizing = sizing_from_row(flat.loc[pen], connections, n_households)
    b1 = make_load_builder(cfg, n_households, pen, 0.0, seed)
    b0 = make_load_builder(cfg, n_households, 0.0, 0.0, seed)
    tar, _ = required_tariff(cfg, sizing, b1, resource)
    reg = average_billed_rate(cfg, sizing, b1, resource)
    sub = operating_subsidy.cost(cfg, sizing, b1, resource, n_households)
    t = cfg["tariff"]
    kwh0 = monthly_kwh_per_household(b0, 1, n_households)
    kwh1 = monthly_kwh_per_household(b1, 1, n_households)

    lo, hi = flat.iloc[0], flat.iloc[-1]
    return {
        "kwh_per_household_month_no_cooking": kwh0,
        "kwh_per_household_month_full_cooking": kwh1,
        "pv_kw_no_cooking": lo.pv_kw, "battery_kwh_no_cooking": lo.battery_kwh,
        "pv_kw_full": hi.pv_kw, "battery_kwh_full": hi.battery_kwh,
        "lcoe_no_cooking": lo.lcoe, "lcoe_half": flat.loc[0.5].lcoe if 0.5 in flat.index else None,
        "lcoe_full": hi.lcoe,
        "lcoe_reduction_pct": 100 * (1 - hi.lcoe / lo.lcoe),
        "battery_avoided_pct_phi_max": top.avoided_battery_pct,
        "tou_lcoe_change_pct": top.lcoe_change_pct,
        "cost_reflective_multiple": tar / reg if tar else None,
        "opsub_usd_per_connection_year": sub.get("opsub_grant0_usd_per_conn_year"),
        "band_factor_year1": _band_rate(kwh1, t) / _band_rate(kwh0, t),
    }


def compare(resource, n_households=300, connections=300, seed=42):
    out = {src: headline(src, resource, n_households, connections, seed) for src in SOURCES}
    df = pd.DataFrame(out)
    df.index.name = "quantity"
    df["change_pct"] = 100 * (df["core"] / df["m3"] - 1)
    df["aged_change_pct"] = 100 * (df["core_2022"] / df["core"] - 1)
    return df.reset_index()
