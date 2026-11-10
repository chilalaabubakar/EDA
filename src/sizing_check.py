"""Does the sizing search find the least-cost design?

The base case is built in two stages, so the check has two parts, each
comparing the production search with an exhaustive grid:

  stage 1   the plant for years 1-10: sizing.size_system on a ten-year
            project against sizing.full_grid_search on the same project
  stage 2   the enlarged plant for years 11-20, given stage 1:
            expansion.size_staged against every (solar, battery) pair on the
            grid, each run through the full 20-year simulation

For the chosen design both reliability figures are reported. The limit binds
in the WORST year; unserved demand averaged over the project is far below it.
"""
import copy

import numpy as np
import pandas as pd

from expansion import size_staged
from model import simulate
from sizing import _sizing, full_grid_search, size_system


def check(cfg, builder, res, connections, pv_values, batt_values, label="",
          sizing_kw=None):
    """Single-stage search against the full grid (kept for the single-stage
    robustness case and the tests)."""
    s, m, trace = size_system(cfg, builder, res, connections, **(sizing_kw or {}))
    g, gm, rows = full_grid_search(cfg, builder, res, connections, pv_values,
                                   batt_values)
    summary = {
        "scenario": label, "stage": "single",
        "search_pv_kw": s["pv_kw"], "search_battery_kwh": s["battery_kwh"],
        "search_lcoe": m["lcoe"], "search_evaluations": len(trace),
        "grid_pv_kw": g["pv_kw"], "grid_battery_kwh": g["battery_kwh"],
        "grid_lcoe": gm["lcoe"], "grid_evaluations": len(rows),
        "lcoe_gap_pct": 100 * (m["lcoe"] - gm["lcoe"]) / gm["lcoe"],
        "worst_year_unmet": m["worst_year_unmet_fraction"],
        "lifetime_unmet": m["unmet_fraction"],
    }
    return summary, pd.DataFrame(rows)


def check_staged(cfg, builder, res, connections, pv_values, batt_values, label="",
                 sizing_kw=None, stage2_pv_span=100.0):
    """Both stages of the two-stage build against exhaustive grids.
    Returns (list of two summary rows, grid DataFrame)."""
    split = cfg["battery"]["replacement_year"]
    life = cfg["finance"]["project_life_years"]
    limit = cfg["reliability"]["max_unmet_demand_fraction"]

    # ---- stage 1: a ten-year project with no replacement
    c1 = copy.deepcopy(cfg)
    c1["finance"]["project_life_years"] = split
    c1["battery"]["replacement_year"] = None
    s1, m1, trace = size_system(c1, builder, res, connections, design_year=split,
                                **(sizing_kw or {}))
    g1, gm1, rows1 = full_grid_search(c1, builder, res, connections, pv_values,
                                      batt_values, design_year=split)
    out = [{
        "scenario": label, "stage": "1 (years 1-10)",
        "search_pv_kw": s1["pv_kw"], "search_battery_kwh": s1["battery_kwh"],
        "search_lcoe": m1["lcoe"], "search_evaluations": len(trace),
        "grid_pv_kw": g1["pv_kw"], "grid_battery_kwh": g1["battery_kwh"],
        "grid_lcoe": gm1["lcoe"], "grid_evaluations": len(rows1),
        "lcoe_gap_pct": 100 * (m1["lcoe"] - gm1["lcoe"]) / gm1["lcoe"],
        "worst_year_unmet": m1["worst_year_unmet_fraction"],
        "lifetime_unmet": m1["unmet_fraction"],
    }]
    grid = pd.DataFrame(rows1).assign(stage=1)

    # ---- stage 2: every enlarged plant on the grid, given the search's stage 1
    st = size_staged(cfg, builder, res, connections, sizing_kw=sizing_kw)
    _, m = simulate(cfg, st, builder, res)
    first, second = st["stages"]
    rows2, best = [], None
    pv2s = [p for p in pv_values if first["pv_kw"] <= p <= first["pv_kw"] + stage2_pv_span]
    for pv2 in pv2s:
        for bt2 in batt_values:
            sz = {**st, "stages": [first, {"from_year": second["from_year"],
                                           **_sizing(cfg, pv2, bt2, connections, builder, life)}]}
            _, g = simulate(cfg, sz, builder, res)
            ok = g["worst_year_unmet_fraction"] <= limit
            rows2.append({"pv_kw": pv2, "battery_kwh": bt2, "lcoe": g["lcoe"], "feasible": ok,
                          "worst_year_unmet_fraction": g["worst_year_unmet_fraction"],
                          "unmet_fraction": g["unmet_fraction"]})
            if ok and (best is None or g["lcoe"] < best[0]):
                best = (g["lcoe"], pv2, bt2)
    out.append({
        "scenario": label, "stage": "2 (years 11-20)",
        "search_pv_kw": second["pv_kw"], "search_battery_kwh": second["battery_kwh"],
        "search_lcoe": m["lcoe"], "search_evaluations": np.nan,
        "grid_pv_kw": best[1], "grid_battery_kwh": best[2],
        "grid_lcoe": best[0], "grid_evaluations": len(rows2),
        "lcoe_gap_pct": 100 * (m["lcoe"] - best[0]) / best[0],
        "worst_year_unmet": m["worst_year_unmet_fraction"],
        "lifetime_unmet": m["unmet_fraction"],
    })
    grid = pd.concat([grid, pd.DataFrame(rows2).assign(stage=2)])
    return out, grid


def default_grid(cfg, step_pv=5.0, step_batt=20.0, pv=(50, 400), batt=(100, 1400)):
    return (np.arange(pv[0], pv[1] + 1e-9, step_pv),
            np.arange(batt[0], batt[1] + 1e-9, step_batt))
