"""Phase 2: does the two-stage search find the LCOE optimum?

Runs the production search (sizing.size_system) and an exhaustive full grid on
the same scenario and compares. Also reports, for the chosen design, both
reliability figures, which is the actual explanation of the "1-2% achieved
against a 5% constraint" pattern: the constraint binds in the WORST year, and
lifetime-average unmet is necessarily far below it when demand grows 5%/yr.
"""
import numpy as np
import pandas as pd

from sizing import full_grid_search, size_system


def check(cfg, builder, res, connections, pv_values, batt_values, label="",
          sizing_kw=None):
    s, m, trace = size_system(cfg, builder, res, connections, **(sizing_kw or {}))
    g, gm, rows = full_grid_search(cfg, builder, res, connections, pv_values,
                                   batt_values)
    summary = {
        "scenario": label,
        "search_pv_kw": s["pv_kw"], "search_battery_kwh": s["battery_kwh"],
        "search_lcoe": m["lcoe"], "search_evaluations": len(trace),
        "grid_pv_kw": g["pv_kw"], "grid_battery_kwh": g["battery_kwh"],
        "grid_lcoe": gm["lcoe"], "grid_evaluations": len(rows),
        "lcoe_gap_pct": 100 * (m["lcoe"] - gm["lcoe"]) / gm["lcoe"],
        "worst_year_unmet": m["worst_year_unmet_fraction"],
        "lifetime_unmet": m["unmet_fraction"],
    }
    return summary, pd.DataFrame(rows)


def default_grid(cfg, step_pv=5.0, step_batt=20.0, pv=(50, 400), batt=(100, 1400)):
    return (np.arange(pv[0], pv[1] + 1e-9, step_pv),
            np.arange(batt[0], batt[1] + 1e-9, step_batt))
