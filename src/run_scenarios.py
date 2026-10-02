"""Scenario sweep: tariff x eCooking penetration x shiftable fraction x discount.

    python src/run_scenarios.py --country rwanda --out results/scenarios_rwanda.csv
    python src/run_scenarios.py --country kenya --synthetic --out /tmp/x.csv

Writes one tidy row per scenario. The substitution frontier (Figure 4) is built
from the difference in sized battery capacity between matched flat and ToU rows.

Every row records the seed, the resource year and the git-independent inputs
needed to reproduce it, and the sweep is bit-for-bit repeatable:
tests/test_reproducibility.py runs it twice and compares the CSVs.
"""
import argparse
import itertools
import time
from pathlib import Path

import numpy as np
import pandas as pd

from load_builder import build_cooking_load, build_noncooking_load
from model import simulate
from sizing import size_system

_COOK_CACHE = {}


def cooking_load(n_households, penetration, phi, seed, params=None):
    key = (n_households, penetration, phi, seed, repr(params))
    if key not in _COOK_CACHE:
        _COOK_CACHE[key] = build_cooking_load(n_households, penetration, phi,
                                              params=params, seed=seed)
    return _COOK_CACHE[key]


def make_load_builder(cfg, n_households, penetration, phi, seed,
                      cooking_params=None):
    """year -> 8760 kW array. Appliance (RAMP) and cooking loads are both
    seeded by `seed`; demand grows at cfg['demand']['annual_growth_rate']."""
    base = build_noncooking_load(cfg["appliances"], n_households, None, seed=seed)
    cook = cooking_load(n_households, penetration, phi, seed, cooking_params)
    growth = cfg["demand"]["annual_growth_rate"]
    total = base + cook

    def builder(year):
        return total * (1 + growth) ** (year - 1)
    builder.noncooking = base
    builder.cooking = cook
    return builder


def effective_phi(phi, tariff, discount):
    """phi is a RESPONSE to the price signal, not an independent input.

    Under a flat tariff there is no incentive to shift, so households cook on
    the measured baseline split (phi_effective = 0). Applying phi to both arms
    would make the tariff purely a revenue change and no substitution could
    ever appear.

    NOTE (Phase 2, s3.3): this is an ASSUMED step response. Any positive
    discount triggers the full nominal phi, so avoided storage cannot depend
    on the size of the discount. See tou_sweep.py.
    """
    return phi if (tariff == "tou" and discount > 0) else 0.0


def scenario_row(cfg, resource, n_households, connections, pen, phi, tariff,
                 disc, seed, sizing_kw=None, cooking_params=None,
                 sizing_cache=None):
    """Size and evaluate one scenario.

    Sizing depends on the load (penetration, effective phi, seed) but not on
    the tariff: dispatch ignores price and LCOE is a cost metric. Passing a
    dict as `sizing_cache` reuses the least-cost sizing across tariff arms with
    the same load; only NPV/IRR are recomputed under the arm's tariff.
    """
    c = {k: (v.copy() if isinstance(v, dict) else v) for k, v in cfg.items()}
    c["tariff"] = {**cfg["tariff"], "daytime_discount_per_kwh": disc}
    c["_tariff_mode"] = tariff
    phi_eff = effective_phi(phi, tariff, disc)
    builder = make_load_builder(cfg, n_households, pen, phi_eff, seed,
                                cooking_params)
    kw = dict(max_unmet=cfg["reliability"]["max_unmet_demand_fraction"],
              pv_range=tuple(cfg["sizing"]["pv_range"]),
              batt_range=tuple(cfg["sizing"]["battery_range"]))
    kw.update(sizing_kw or {})
    key = (pen, phi_eff, seed, repr(sorted(kw.items())))
    if sizing_cache is not None and key in sizing_cache:
        s = sizing_cache[key]
        m = simulate(c, s, builder, resource, tariff_mode=tariff)[1] if s else None
    else:
        s, m, _ = size_system(c, builder, resource, connections, **kw)
        if sizing_cache is not None:
            sizing_cache[key] = s
    row = {"penetration": pen, "phi": phi, "phi_effective": phi_eff,
           "tariff": tariff, "discount": disc, "seed": seed,
           "feasible": s is not None}
    if s is None:
        return row
    cook = builder.cooking
    row.update({
        "pv_kw": s["pv_kw"], "battery_kwh": s["battery_kwh"],
        "inverter_kw": m["capex_items"]["inverter"] / cfg["capex"]["inverter_per_kw"],
        "inverter_limits_battery": bool(s.get("inverter_limits_battery", False)),
        "lcoe": m["lcoe"], "npv": m["npv"], "irr": m["irr"],
        "unmet_fraction": m["unmet_fraction"],
        "worst_year_unmet_fraction": m["worst_year_unmet_fraction"],
        "curtailed_fraction": m["curtailed_fraction"],
        "peak_load_kw_final_year": m["peak_load_kw"],
        "peak_load_kw_year1": float(builder(1).max()),
        "peak_cooking_kw_year1": float(cook.max()),
        "capex": m["total_capex"], "gross_capex": m["gross_capex"],
    })
    return row


def run(cfg, resource, n_households, connections, out_path=None, seed=42,
        verbose=True, cooking_params=None):
    sc = cfg["scenarios"]
    combos = list(itertools.product(sc["penetration_sweep"],
                                    sc["shiftable_fraction_sweep"],
                                    sc["tariffs"],
                                    sc["tou_daytime_discount_sweep"]))
    # A discount is meaningless under a flat tariff: keep only discount 0 there.
    combos = [c for c in combos if not (c[2] == "flat" and c[3] != 0.0)]

    rows, cache = [], {}
    t0 = time.time()
    for i, (pen, phi, tariff, disc) in enumerate(combos, 1):
        r = scenario_row(cfg, resource, n_households, connections, pen, phi,
                         tariff, disc, seed, cooking_params=cooking_params,
                         sizing_cache=cache)
        rows.append(r)
        if verbose and r["feasible"]:
            print(f"[{i}/{len(combos)}] pen={pen} phi={phi} {tariff} d={disc} -> "
                  f"PV {r['pv_kw']:.0f} kW batt {r['battery_kwh']:.0f} kWh "
                  f"LCOE {r['lcoe']:.4f}  ({(time.time()-t0)/i:.1f}s/scenario)")

    df = pd.DataFrame(rows)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False, float_format="%.10g")
    return df


def substitution_frontier(df):
    """Avoided battery capacity: flat baseline minus ToU, at matched pen/phi."""
    flat = (df[(df.tariff == "flat") & df.feasible]
            .set_index(["penetration", "phi"]))
    tou = df[(df.tariff == "tou") & df.feasible].copy()
    idx = tou.set_index(["penetration", "phi"]).index
    tou["battery_flat"] = idx.map(flat.battery_kwh)
    tou["lcoe_flat"] = idx.map(flat.lcoe)
    tou["peak_cooking_kw_flat"] = idx.map(flat.peak_cooking_kw_year1)
    tou["avoided_battery_kwh"] = tou.battery_flat - tou.battery_kwh
    tou["avoided_battery_pct"] = 100 * tou.avoided_battery_kwh / tou.battery_flat
    tou["lcoe_change_pct"] = 100 * (tou.lcoe - tou.lcoe_flat) / tou.lcoe_flat
    return tou


def main():
    import yaml
    from final_cfg import country_cfg
    from resource import load_site_resource, synthetic_years

    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--country", required=True, choices=["rwanda", "kenya"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--synthetic", action="store_true",
                    help="synthetic resource - smoke test only, never quote")
    args = ap.parse_args()
    p = yaml.safe_load(open(args.params))
    site = p["countries"][args.country]
    year = site["representative_year"]
    res = (synthetic_years(args.country)[year] if args.synthetic
           else load_site_resource(args.country, year))
    run(country_cfg(args.country), res, p["run"]["n_households"],
        p["run"]["connections"], args.out, seed=p["run"]["seed"])


if __name__ == "__main__":
    main()
