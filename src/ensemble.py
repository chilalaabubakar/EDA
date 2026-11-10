"""Seed ensemble: intervals on the results that depend on random behaviour.

Every claim is re-derived on N independent seeds (default 24): each seed draws
its own appliance profile and its own cooking events, and the flat and
time-of-use arms share the seed (paired design).

These intervals measure SAMPLING NOISE ONLY: how much the result moves when
300 different random households are drawn. They say nothing about the inputs
(capital cost, growth, collection, energy per meal); sensitivity.py covers
those, and they move the results far more.

Reported per site, for each quantity: mean, sd, a t-based 95% interval on the
mean, and the 2.5-97.5 percentile range across seeds (what one seed could
show). The daytime-discount quantities are computed for each share of supper
cooking moved (phi), so Fig. 4 is drawn from the ensemble, not from one seed.

Battery quantities count the batteries BOUGHT over the project: the first bank
and its replacement, which a two-stage build sizes separately.
"""
import numpy as np
import pandas as pd
from scipy import stats

from model import required_operating_subsidy
from run_scenarios import make_load_builder, scenario_row
from viability import sizing_from_row

PHIS = (0.1, 0.2, 0.3, 0.4, 0.5)
D1, D2 = 0.01, 0.02            # two discounts: revenue is linear in the discount


def _tag(phi):
    return f"phi{int(round(100 * phi)):02d}"


def one_seed(cfg, res, n, conn, seed, phis=PHIS, sizing_kw=None):
    cache = {}
    kw = dict(sizing_kw=sizing_kw, sizing_cache=cache)
    zero = scenario_row(cfg, res, n, conn, 0.0, 0.0, "flat", 0.0, seed, **kw)
    flat = scenario_row(cfg, res, n, conn, 1.0, 0.0, "flat", 0.0, seed, **kw)
    sub = {}
    for tag, row, pen in (("zero", zero, 0.0), ("full", flat, 1.0)):
        b = make_load_builder(cfg, n, pen, 0.0, seed)
        sub[tag], _ = required_operating_subsidy(
            cfg, sizing_from_row(pd.Series(row), conn, n), b, res)
    out = {
        "seed": seed,
        "lcoe_zero": zero["lcoe"], "lcoe_flat_full": flat["lcoe"],
        "npv_zero": zero["npv"], "npv_full": flat["npv"],
        "battery_bought_flat_full": flat["battery_kwh_bought"],
        "lcoe_reduction_pct_0_to_full": 100 * (1 - flat["lcoe"] / zero["lcoe"]),
        "opsub_zero": sub["zero"], "opsub_full": sub["full"],
        "incremental_usd_per_cooking_hh_year": sub["full"] - sub["zero"],
    }
    for phi in phis:
        t2 = scenario_row(cfg, res, n, conn, 1.0, phi, "tou", D2, seed, **kw)
        t1 = scenario_row(cfg, res, n, conn, 1.0, phi, "tou", D1, seed, **kw)
        g1, g2 = t1["npv"] - flat["npv"], t2["npv"] - flat["npv"]
        slope = (g2 - g1) / (D2 - D1)                 # US$ of NPV per US$/kWh, < 0
        k = _tag(phi)
        out[f"avoided_battery_kwh_{k}"] = flat["battery_kwh_bought"] - t2["battery_kwh_bought"]
        out[f"avoided_battery_pct_{k}"] = 100 * (1 - t2["battery_kwh_bought"]
                                                  / flat["battery_kwh_bought"])
        out[f"tou_lcoe_change_pct_{k}"] = 100 * (t2["lcoe"] / flat["lcoe"] - 1)
        out[f"peak_cooking_increase_pct_{k}"] = 100 * (t2["peak_cooking_kw_year1"]
                                                       / flat["peak_cooking_kw_year1"] - 1)
        # NPV gain from the smaller system alone (no discount given), and the
        # largest discount the operator can give before the gain is used up
        out[f"npv_gain_no_discount_{k}"] = g1 - slope * D1
        out[f"break_even_discount_{k}"] = D1 - g1 / slope
    return out


def _job(args):
    cfg, res, n, conn, seed, kw = args
    return one_seed(cfg, res, n, conn, seed, **kw)


def run(cfg, res, n, conn, seeds=range(1, 25), workers=1, **kw):
    """One row per seed. Seeds are independent, so `workers` > 1 runs them in
    separate processes; the result does not depend on the number of workers."""
    jobs = [(cfg, res, n, conn, s, kw) for s in seeds]
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(_job, jobs))
    else:
        rows = [_job(j) for j in jobs]
    return pd.DataFrame(rows).sort_values("seed").reset_index(drop=True)


def summarise(df):
    rows = []
    k = len(df)
    for q in [c for c in df.columns if c != "seed"]:
        x = df[q].astype(float)
        se = x.std(ddof=1) / np.sqrt(k)
        h = stats.t.ppf(0.975, k - 1) * se if k > 1 else np.nan
        rows.append({"quantity": q, "n_seeds": k, "mean": x.mean(), "sd": x.std(ddof=1),
                     "ci95_lo": x.mean() - h, "ci95_hi": x.mean() + h,
                     "p2_5": x.quantile(0.025), "p97_5": x.quantile(0.975),
                     "min": x.min(), "max": x.max()})
    return pd.DataFrame(rows)
