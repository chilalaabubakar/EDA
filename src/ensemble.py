"""Phase 2: seed ensemble - confidence intervals on the stochastic claims.

The abstract's "8-9% lower LCOE" and "27-28% of battery capacity displaced"
come from ONE seed. Here every claim is re-derived on N independent seeds
(default 24): each seed draws its own RAMP appliance profile and its own
cooking events, and flat and ToU arms share the seed (paired design).

Reported per site, for each quantity: mean, sd, a t-based 95% CI on the mean,
and the 2.5-97.5 percentile range across seeds (what one seed could show).
"""
import numpy as np
import pandas as pd
from scipy import stats

from run_scenarios import scenario_row

QUANTITIES = ("avoided_battery_kwh", "avoided_battery_pct", "tou_lcoe_change_pct",
              "lcoe_reduction_pct_0_to_full", "lcoe_flat_full", "battery_flat_full",
              "peak_cooking_increase_pct")


def one_seed(cfg, res, n, conn, seed, phi=0.5, discount=0.02, sizing_kw=None):
    cache = {}
    kw = dict(sizing_kw=sizing_kw, sizing_cache=cache)
    zero = scenario_row(cfg, res, n, conn, 0.0, 0.0, "flat", 0.0, seed, **kw)
    flat = scenario_row(cfg, res, n, conn, 1.0, phi, "flat", 0.0, seed, **kw)
    tou = scenario_row(cfg, res, n, conn, 1.0, phi, "tou", discount, seed, **kw)
    return {
        "seed": seed,
        "lcoe_zero": zero["lcoe"], "lcoe_flat_full": flat["lcoe"],
        "lcoe_tou_full": tou["lcoe"],
        "battery_flat_full": flat["battery_kwh"], "battery_tou_full": tou["battery_kwh"],
        "avoided_battery_kwh": flat["battery_kwh"] - tou["battery_kwh"],
        "avoided_battery_pct": 100 * (flat["battery_kwh"] - tou["battery_kwh"])
                               / flat["battery_kwh"],
        "tou_lcoe_change_pct": 100 * (tou["lcoe"] - flat["lcoe"]) / flat["lcoe"],
        "lcoe_reduction_pct_0_to_full": 100 * (1 - flat["lcoe"] / zero["lcoe"]),
        "peak_cooking_increase_pct": 100 * (tou["peak_cooking_kw_year1"]
                                            / flat["peak_cooking_kw_year1"] - 1),
    }


def run(cfg, res, n, conn, seeds=range(1, 25), **kw):
    return pd.DataFrame([one_seed(cfg, res, n, conn, s, **kw) for s in seeds])


def summarise(df, quantities=QUANTITIES):
    rows = []
    k = len(df)
    for q in quantities:
        x = df[q].astype(float)
        se = x.std(ddof=1) / np.sqrt(k)
        h = stats.t.ppf(0.975, k - 1) * se if k > 1 else np.nan
        rows.append({"quantity": q, "n_seeds": k, "mean": x.mean(), "sd": x.std(ddof=1),
                     "ci95_lo": x.mean() - h, "ci95_hi": x.mean() + h,
                     "p2_5": x.quantile(0.025), "p97_5": x.quantile(0.975),
                     "min": x.min(), "max": x.max()})
    return pd.DataFrame(rows)
