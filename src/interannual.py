"""Phase 2: propagate interannual resource variability.

s4 reports 7.4% (Nkombo) and 8.0% (Ringiti) interannual GHI spreads over
2005-2024 and the model then uses a single median year. Three checks:

  by_weather_year   the headline design run with each of the 20 weather years
                    repeated across the life: distribution of LCOE and of
                    worst-year unmet (does the 5% constraint survive a bad year?)
  chronological     project year y uses weather year (first + y - 1): one
                    realistic 20-year sequence
  size_to_p10       re-size against the 10th-percentile GHI year and report
                    what reliability insurance costs
"""
import numpy as np
import pandas as pd

from model import required_tariff, simulate
from sizing import size_system


def _ghi(r):
    return float(np.sum(r["ghi"]) / 1000.0)


def by_weather_year(cfg, sizing, builder, years):
    rows = []
    for y, r in sorted(years.items()):
        _, m = simulate(cfg, sizing, builder, r)
        rows.append({"weather_year": y, "ghi_kwh_m2": _ghi(r), "lcoe": m["lcoe"],
                     "worst_year_unmet_fraction": m["worst_year_unmet_fraction"],
                     "unmet_fraction": m["unmet_fraction"],
                     "curtailed_fraction": m["curtailed_fraction"]})
    return pd.DataFrame(rows)


def chronological(cfg, sizing, builder, years):
    ys = sorted(years)
    seq = lambda py: years[ys[(py - 1) % len(ys)]]
    _, m = simulate(cfg, sizing, builder, seq)
    return {"lcoe": m["lcoe"], "worst_year_unmet_fraction": m["worst_year_unmet_fraction"],
            "unmet_fraction": m["unmet_fraction"],
            "years_breaching_constraint": int(sum(
                u > cfg["reliability"]["max_unmet_demand_fraction"]
                for u in m["unmet_fraction_by_year"]))}


def size_to_percentile(cfg, builder, years, connections, q=10, sizing_kw=None):
    ghi = {y: _ghi(r) for y, r in years.items()}
    target = np.percentile(list(ghi.values()), q)
    y = min(ghi, key=lambda k: abs(ghi[k] - target))
    s, m, _ = size_system(cfg, builder, years[y], connections, **(sizing_kw or {}))
    tar, _ = required_tariff(cfg, s, builder, years[y])
    return y, s, m, tar


def run(cfg, sizing, builder, years, rep_year, connections, sizing_kw=None):
    dist = by_weather_year(cfg, sizing, builder, years)
    chrono = chronological(cfg, sizing, builder, years)
    p10y, s10, m10, tar10 = size_to_percentile(cfg, builder, years, connections,
                                               sizing_kw=sizing_kw)
    reg = cfg["tariff"]["flat_rate_per_kwh"]
    _, base = simulate(cfg, sizing, builder, years[rep_year])
    tar0, _ = required_tariff(cfg, sizing, builder, years[rep_year])
    summary = {
        "rep_year": rep_year,
        "ghi_spread_pct": 100 * (dist.ghi_kwh_m2.max() - dist.ghi_kwh_m2.min())
                          / dist.ghi_kwh_m2.median(),
        "lcoe_rep_year": base["lcoe"],
        "lcoe_p05": dist.lcoe.quantile(0.05), "lcoe_median": dist.lcoe.median(),
        "lcoe_p95": dist.lcoe.quantile(0.95),
        "worst_year_unmet_max_over_weather": dist.worst_year_unmet_fraction.max(),
        "weather_years_breaching": int((dist.worst_year_unmet_fraction
                                        > cfg["reliability"]["max_unmet_demand_fraction"]).sum()),
        "chrono_lcoe": chrono["lcoe"],
        "chrono_worst_year_unmet": chrono["worst_year_unmet_fraction"],
        "chrono_years_breaching": chrono["years_breaching_constraint"],
        "p10_year": p10y, "p10_pv_kw": s10["pv_kw"], "p10_battery_kwh": s10["battery_kwh"],
        "p10_lcoe": m10["lcoe"],
        "multiple_rep_year": tar0 / reg if tar0 else None,
        "multiple_p10_sizing": tar10 / reg if tar10 else None,
    }
    return summary, dist
