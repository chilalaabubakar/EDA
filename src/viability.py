"""Viability under different tariffs: capital-grant, break-even-tariff and
operating-subsidy solvers, the discount-rate sweep and the tariff scenarios.

Operates on the least-cost design the sweep found for each country.

TARIFF SCENARIOS. Charging every mini-grid customer the national tariff is a
policy choice, not the rule: Kenya's public mini-grids do it, its private ones
charge site-specific tariffs approved by the regulator, and Tanzania capped
mini-grid tariffs at the utility's in 2020. `tariff_scenarios` therefore
reports each village under the national tariff (the base scenario), two
site-specific flat tariffs of the kind private mini-grids charge, and the
break-even tariff. Adoption is the same in all of them (the model has no price
response), so the household bill at each tariff is reported alongside: it
shows whether the adoption assumed is plausible at that price.
"""
import pandas as pd

from final_cfg import DISCOUNT_RATES, KES_USD, country_cfg
from model import (_band_rate, average_billed_rate, required_operating_subsidy,
                   required_subsidy, required_tariff, simulate)
from run_scenarios import make_load_builder

# Site-specific flat tariffs, US$/kWh.
#   Oloika mini-grid, Kenya: KES 40/kWh (Blunden et al. 2025).
#   AMDA's financial model of private Kenyan mini-grids: US$0.56/kWh
#   (AMDA, Cost and Pace of Minigrid Deployment in Kenya, 2024, Table 4).
SITE_TARIFFS = {"site tariff, Oloika (KES 40/kWh)": 40.0 / KES_USD,
                "site tariff, AMDA private model": 0.56}
# Kenya's base energy charges are only part of the bill: fuel, foreign-exchange
# and inflation adjustments, levies and VAT are added (Schedule of Tariffs
# 2023, Part III). AMDA (2024) puts the all-in uniform national tariff charged
# on Kenya Power's mini-grids at US$0.20/kWh. Reported for Kenya only.
ALL_IN_NATIONAL = {"kenya": {"national tariff, all charges (US$0.20/kWh)": 0.20}}


def headline_sizing(scenarios, site, n_households, connections,
                    penetration=None):
    s = scenarios[(scenarios.site == site) & scenarios.feasible
                  & (scenarios.tariff == "flat")]
    pen = s.penetration.max() if penetration is None else penetration
    r = s[s.penetration == pen].iloc[0]
    return sizing_from_row(r, connections, n_households), float(pen)


def sizing_from_row(r, connections, n_households):
    """Rebuild a sizing dict from a scenarios CSV row, inverter included."""
    out = {"pv_kw": float(r.pv_kw), "battery_kwh": float(r.battery_kwh),
           "connections": connections, "households": n_households}
    if "inverter_limits_battery" in r and bool(r.inverter_limits_battery):
        out.update(inverter_kw=float(r.inverter_kw), inverter_limits_battery=True)
    if "pv_kw_stage2" in r and pd.notna(r.pv_kw_stage2):      # staged build
        keys = ("pv_kw", "battery_kwh", "inverter_kw", "inverter_limits_battery")
        s1 = {k: out[k] for k in keys if k in out}
        s2 = {"pv_kw": float(r.pv_kw_stage2), "battery_kwh": float(r.battery_kwh_stage2)}
        if "inverter_kw" in s1:
            s2.update(inverter_kw=float(r.inverter_kw_stage2), inverter_limits_battery=True)
        out["stages"] = [{"from_year": 1, **s1},
                         {"from_year": int(r.stage2_from_year), **s2}]
    return out


def viability(scenarios, resources, n_households, connections, seed=42):
    """One row per site: grant fraction needed, cost-reflective tariff, gap."""
    rows = []
    for site, res in resources.items():
        cfg = country_cfg(site)
        sizing, pen = headline_sizing(scenarios, site, n_households, connections)
        builder = make_load_builder(cfg, n_households, pen, 0.0, seed)
        _, m = simulate(cfg, sizing, builder, res, "flat")
        frac, best_irr = required_subsidy(cfg, sizing, builder, res, "flat")
        tar, _ = required_tariff(cfg, sizing, builder, res)
        reg = average_billed_rate(cfg, sizing, builder, res)
        rows.append({"site": site, "penetration": pen,
                     "regulated_tariff": reg,
                     "lcoe": m["lcoe"], "npv": m["npv"],
                     "grant_fraction": frac,
                     "irr_at_max_grant": best_irr if frac is None else None,
                     "cost_reflective_tariff": tar,
                     "gap_per_kwh": (tar - reg) if tar else None,
                     "multiple_of_regulated": (tar / reg) if tar else None})
    return pd.DataFrame(rows)


def discount_sweep(scenarios, resources, n_households, connections, seed=42,
                   rates=DISCOUNT_RATES, hurdle_premium=0.0):
    """No published East African mini-grid cost-of-capital benchmark exists,
    so the discount rate is swept. The target return equals the discount rate
    (`hurdle_premium` 0): the project is viable when its net present value at
    the cost of capital is zero.
    """
    rows = []
    for site, res in resources.items():
        base = country_cfg(site)
        sizing, pen = headline_sizing(scenarios, site, n_households, connections)
        builder = make_load_builder(base, n_households, pen, 0.0, seed)
        for dr in rates:
            c = {k: (v.copy() if isinstance(v, dict) else v) for k, v in base.items()}
            c["finance"] = {**base["finance"], "discount_rate_real": dr,
                            "target_irr": dr + hurdle_premium}
            _, m = simulate(c, sizing, builder, res, "flat")
            tar, _ = required_tariff(c, sizing, builder, res)
            reg = average_billed_rate(c, sizing, builder, res)
            rows.append({"site": site, "discount_rate": dr,
                         "target_irr": dr + hurdle_premium,
                         "lcoe": m["lcoe"], "npv": m["npv"],
                         "cost_reflective_tariff": tar, "regulated_tariff": reg,
                         "multiple_of_regulated": tar / reg if tar else None})
    return pd.DataFrame(rows)


def _flat(cfg, rate):
    c = {k: (v.copy() if isinstance(v, dict) else v) for k, v in cfg.items()}
    c["tariff"] = {**cfg["tariff"], "flat_rate_per_kwh": rate, "bands": None}
    return c


def tariff_scenarios(scenarios, resources, n_households, connections, seed=42,
                     site_tariffs=SITE_TARIFFS):
    """Full adoption under each tariff: operator's result and household bill.

    kwh_* are the simulated average household's first-year use per month; the
    cooking bill is what cooking adds to its monthly bill at that tariff.
    """
    rows = []
    for site, res in resources.items():
        cfg = country_cfg(site)
        sizing, pen = headline_sizing(scenarios, site, n_households, connections)
        b1 = make_load_builder(cfg, n_households, pen, 0.0, seed)
        b0 = make_load_builder(cfg, n_households, 0.0, 0.0, seed)
        kwh0 = float(b0(1).sum() / n_households / 12.0)
        kwh1 = float(b1(1).sum() / n_households / 12.0)
        tar, _ = required_tariff(cfg, sizing, b1, res)
        sizing0, _ = headline_sizing(scenarios, site, n_households, connections, 0.0)
        options = [("national tariff", cfg)]
        options += [(name, _flat(cfg, rate))
                    for name, rate in ALL_IN_NATIONAL.get(site, {}).items()]
        options += [(name, _flat(cfg, rate)) for name, rate in site_tariffs.items()]
        options += [("break-even tariff", _flat(cfg, tar))]
        national_bill = None
        for name, c in options:
            _, m = simulate(c, sizing, b1, res)
            sub, _ = required_operating_subsidy(c, sizing, b1, res)
            # the same village without cooking, at the same tariff
            _, m0 = simulate(c, sizing0, b0, res)
            sub0, _ = required_operating_subsidy(c, sizing0, b0, res)
            t = c["tariff"]
            bill0 = _band_rate(kwh0, t) * kwh0
            bill1 = _band_rate(kwh1, t) * kwh1
            if national_bill is None:
                national_bill = bill1
            rows.append({"site": site, "tariff": name, "penetration": pen,
                         "price_per_kwh": bill1 / kwh1,
                         "npv": m["npv"], "irr": m["irr"],
                         "opsub_usd_per_conn_year": sub,
                         "npv_no_cooking": m0["npv"],
                         "opsub_no_cooking_usd_per_conn_year": sub0,
                         "incremental_usd_per_cooking_hh_year": (
                             (sub - sub0) / pen if sub is not None and sub0 is not None
                             else (m0["npv"] - m["npv"]) / connections / pen
                             / sum((1 + c["finance"]["discount_rate_real"]) ** -y
                                   for y in range(1, c["finance"]["project_life_years"] + 1))),
                         "kwh_month_no_cooking": kwh0, "kwh_month_cooking": kwh1,
                         "bill_month_no_cooking": bill0, "bill_month_cooking": bill1,
                         "cooking_bill_month": bill1 - bill0,
                         "bill_multiple_of_national": bill1 / national_bill})
    return pd.DataFrame(rows)
