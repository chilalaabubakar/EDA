"""Phase 2: the sizing horizon. How much of the viability gap is a sizing
convention?

The headline sizes a single system for the WORST year of a 20-year life with
5%/yr demand growth: year-20 demand is 2.5x year-1 demand, so for a decade the
plant is heavily over-built. Two alternatives:

  design_year_sensitivity  single-stage systems sized to year 5, 10 or 20.
      Smaller design years are cheaper but breach reliability later in life;
      both the cost and the realised unmet demand are reported.

  staged                   stage 1 sized for years 1-10; at the year-10 battery
      replacement the bank is replaced at a NEW size and PV/inverter are added,
      sized for years 11-20. Every year meets the 5% constraint. Expansion
      capital is spent at the end of year 10, discounted like any other cost.

For each: LCOE, worst-year unmet, gross CAPEX, and the cost-reflective
multiple of the regulated tariff - the viability figure the paper headlines.
"""
import copy

import numpy as np
import pandas as pd

from model import required_tariff, simulate
from sizing import _sizing, design_year_unmet, size_system


def _multiple(cfg, sizing, builder, res):
    tar, _ = required_tariff(cfg, sizing, builder, res)
    return (tar, tar / cfg["tariff"]["flat_rate_per_kwh"]) if tar else (None, None)


def _row(label, cfg, sizing, builder, res, extra=None):
    _, m = simulate(cfg, sizing, builder, res)
    tar, mult = _multiple(cfg, sizing, builder, res)
    return {"design": label, "lcoe": m["lcoe"], "gross_capex": m["gross_capex"],
            "unmet_fraction": m["unmet_fraction"],
            "worst_year_unmet_fraction": m["worst_year_unmet_fraction"],
            "curtailed_fraction": m["curtailed_fraction"],
            "cost_reflective_tariff": tar, "multiple_of_regulated": mult,
            **(extra or {})}


def design_year_sensitivity(cfg, builder, res, connections, years=(5, 10, 20),
                            sizing_kw=None):
    rows = []
    for dy in years:
        s, m, _ = size_system(cfg, builder, res, connections, design_year=dy,
                              **(sizing_kw or {}))
        if s is None:
            rows.append({"design": f"single, year {dy}", "feasible": False})
            continue
        rows.append(_row(f"single, year {dy}", cfg, s, builder, res,
                         {"pv_kw": s["pv_kw"], "battery_kwh": s["battery_kwh"],
                          "inverter_kw": s.get("inverter_kw")}))
    return rows


def size_staged(cfg, builder, res, connections, split_year=None, pv_step=5.0,
                batt_step=20.0, pv_span=400.0, batt_max=4000.0, sizing_kw=None):
    """Two-stage least-cost design. Stage boundary = battery replacement."""
    split = split_year or cfg["battery"]["replacement_year"]
    # Stage 1: an ordinary least-cost search on a project that ends at `split`.
    c1 = copy.deepcopy(cfg)
    c1["finance"]["project_life_years"] = split
    c1["battery"]["replacement_year"] = None
    s1, _, _ = size_system(c1, builder, res, connections, design_year=split,
                           **(sizing_kw or {}))
    if s1 is None:
        return None
    max_unmet = cfg["reliability"]["max_unmet_demand_fraction"]
    dy = cfg["finance"]["project_life_years"]

    def staged(pv2, bt2):
        st2 = _sizing(cfg, pv2, bt2, connections, builder, dy)
        return {**s1, "stages": [{"from_year": 1, **s1},
                                 {"from_year": split + 1, **st2}]}

    # Stage 2: for each PV >= stage-1 PV, the smallest replacement bank that
    # keeps every year within the constraint (bisection on the screen, then
    # confirmed by the full simulation), ranked by full-life LCOE.
    batt_grid = np.arange(0, batt_max + 1e-9, batt_step)
    best, best_m = None, None
    for pv2 in np.arange(s1["pv_kw"], s1["pv_kw"] + pv_span + 1e-9, pv_step):
        probe = _sizing(cfg, pv2, batt_grid[-1], connections, builder, dy)
        if design_year_unmet(cfg, probe, builder, res, dy, 0.5) > max_unmet:
            continue
        lo, hi = 0, len(batt_grid) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            sz = staged(pv2, batt_grid[mid])
            if simulate(cfg, sz, builder, res)[1]["worst_year_unmet_fraction"] <= max_unmet:
                hi = mid
            else:
                lo = mid + 1
        sz = staged(pv2, batt_grid[lo])
        _, m = simulate(cfg, sz, builder, res)
        if m["worst_year_unmet_fraction"] > max_unmet:
            continue
        if best_m is None or m["lcoe"] < best_m["lcoe"]:
            best, best_m = sz, m
        elif m["lcoe"] > best_m["lcoe"] * 1.02:
            break                       # past the optimum along PV
    return best


def run(cfg, builder, res, connections, sizing_kw=None):
    rows = design_year_sensitivity(cfg, builder, res, connections,
                                   sizing_kw=sizing_kw)
    st = size_staged(cfg, builder, res, connections, sizing_kw=sizing_kw)
    if st is not None:
        a, b = st["stages"]
        rows.append(_row("staged, years 1-10 / 11-20", cfg, st, builder, res,
                         {"pv_kw": a["pv_kw"], "battery_kwh": a["battery_kwh"],
                          "inverter_kw": a.get("inverter_kw"),
                          "pv_kw_stage2": b["pv_kw"],
                          "battery_kwh_stage2": b["battery_kwh"],
                          "inverter_kw_stage2": b.get("inverter_kw")}))
    df = pd.DataFrame(rows)
    ref = df[df.design == "single, year 20"]
    if not ref.empty and "multiple_of_regulated" in df:
        df["multiple_change_vs_headline"] = (df.multiple_of_regulated
                                             - ref.multiple_of_regulated.iloc[0])
    return df
