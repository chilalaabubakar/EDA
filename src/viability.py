"""Viability at regulated tariffs: capital-grant and cost-reflective-tariff
solvers (Table 6, s5.4), and the discount-rate sweep.

Ported from notebook cells 39 and 43. Operates on the least-cost sizing the
sweep found for each country at full eCooking penetration, flat tariff.
"""
import pandas as pd

from final_cfg import DISCOUNT_RATES, country_cfg
from model import required_subsidy, required_tariff, simulate
from run_scenarios import make_load_builder


def headline_sizing(scenarios, site, n_households, connections,
                    penetration=None):
    s = scenarios[(scenarios.site == site) & scenarios.feasible
                  & (scenarios.tariff == "flat")]
    pen = s.penetration.max() if penetration is None else penetration
    r = s[s.penetration == pen].iloc[0]
    return {"pv_kw": float(r.pv_kw), "battery_kwh": float(r.battery_kwh),
            "connections": connections, "households": n_households}, float(pen)


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
        reg = cfg["tariff"]["flat_rate_per_kwh"]
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
                   rates=DISCOUNT_RATES, hurdle_premium=0.03):
    """No published East African mini-grid cost-of-capital benchmark exists,
    so the discount rate is swept. The target IRR is the discount rate plus a
    `hurdle_premium` (3 points, as in the v4 notebook).

    NOTE for the manuscript: Figure 6's caption says "tariff required for a
    15% return", but each row here targets discount rate + 3%. Make the caption
    match, or set hurdle_premium so the target is a fixed 15%.
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
            reg = c["tariff"]["flat_rate_per_kwh"]
            rows.append({"site": site, "discount_rate": dr,
                         "target_irr": dr + hurdle_premium,
                         "lcoe": m["lcoe"], "npv": m["npv"],
                         "cost_reflective_tariff": tar,
                         "multiple_of_regulated": tar / reg if tar else None})
    return pd.DataFrame(rows)
