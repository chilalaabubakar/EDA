"""Phase 2: propagate interannual resource variability.

s4 reports 7.4% (Nkombo) and 8.0% (Ringiti) interannual GHI spreads over
2005-2024. Systems are sized on a design weather year (params.yaml
design_year): the year that is hardest for the full-cooking system. Checks:

  by_weather_year   the headline design run with each of the 20 weather years
                    repeated across the life: distribution of LCOE and of
                    worst-year unmet (does the 5% constraint survive every year?)
  chronological     project year y uses weather year (first + y - 1): one
                    realistic 20-year sequence
  median sizing     the same system sized on the median-GHI year instead, and
                    how often that cheaper design breaches the constraint
  binding_year      the weather year that is hardest for a design (how the
                    design year in params.yaml was chosen)
"""
import numpy as np
import pandas as pd

from model import average_billed_rate, required_tariff, simulate
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


def binding_year(dist):
    """Weather year whose recurrence leaves most demand unserved in the worst year."""
    return int(dist.loc[dist.worst_year_unmet_fraction.idxmax(), "weather_year"])


def run(cfg, sizing, builder, years, design_year, median_year, connections,
        sizing_kw=None):
    limit = cfg["reliability"]["max_unmet_demand_fraction"]
    dist = by_weather_year(cfg, sizing, builder, years)
    chrono = chronological(cfg, sizing, builder, years)
    reg = average_billed_rate(cfg, sizing, builder, years[design_year])
    _, base = simulate(cfg, sizing, builder, years[design_year])
    tar0, _ = required_tariff(cfg, sizing, builder, years[design_year])

    # the cheaper alternative: size on the median-GHI year
    sm, mm, _ = size_system(cfg, builder, years[median_year], connections,
                            **(sizing_kw or {}))
    dm = by_weather_year(cfg, sm, builder, years)
    regm = average_billed_rate(cfg, sm, builder, years[median_year])
    tarm, _ = required_tariff(cfg, sm, builder, years[median_year])

    summary = {
        "design_year": design_year,
        "ghi_spread_pct": 100 * (dist.ghi_kwh_m2.max() - dist.ghi_kwh_m2.min())
                          / dist.ghi_kwh_m2.median(),
        "pv_kw": sizing["pv_kw"], "battery_kwh": sizing["battery_kwh"],
        "lcoe_design_year": base["lcoe"],
        "lcoe_p05": dist.lcoe.quantile(0.05), "lcoe_median": dist.lcoe.median(),
        "lcoe_p95": dist.lcoe.quantile(0.95),
        "worst_year_unmet_max_over_weather": dist.worst_year_unmet_fraction.max(),
        "weather_years_breaching": int((dist.worst_year_unmet_fraction > limit).sum()),
        "chrono_lcoe": chrono["lcoe"],
        "chrono_worst_year_unmet": chrono["worst_year_unmet_fraction"],
        "chrono_years_breaching": chrono["years_breaching_constraint"],
        "median_year": median_year,
        "median_pv_kw": sm["pv_kw"], "median_battery_kwh": sm["battery_kwh"],
        "median_lcoe": mm["lcoe"],
        "median_lcoe_saving_pct": 100 * (1 - mm["lcoe"] / base["lcoe"]),
        "median_weather_years_breaching": int((dm.worst_year_unmet_fraction > limit).sum()),
        "median_worst_year_unmet_max": dm.worst_year_unmet_fraction.max(),
        "median_binding_year": binding_year(dm),
        "multiple_design_year": tar0 / reg if tar0 else None,
        "multiple_median_sizing": tarm / regm if tarm else None,
    }
    return summary, dist
