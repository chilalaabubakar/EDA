"""Scenario sweep: tariff x eCooking penetration x shiftable fraction x discount.

    python src/run_scenarios.py --params params.yaml --country rwanda \
        --out results/scenarios_rwanda.csv

Writes one tidy row per scenario. Figure 5 is built from the difference in
sized battery capacity between matched flat and ToU rows.
"""
import argparse
import itertools
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from load_builder import build_cooking_load, build_noncooking_load
from sizing import size_system


def make_load_builder(cfg, n_households, penetration, phi, seed):
    base = build_noncooking_load(cfg["appliances"], n_households, None, seed=seed)
    cook = build_cooking_load(n_households, penetration, phi, seed=seed)
    growth = cfg["demand"]["annual_growth_rate"]

    def builder(year):
        return (base + cook) * (1 + growth) ** (year - 1)
    return builder


def run(cfg, resource, n_households, connections, out_path, seed=42):
    sc = cfg["scenarios"]
    combos = list(itertools.product(sc["penetration_sweep"],
                                    sc["shiftable_fraction_sweep"],
                                    sc["tariffs"],
                                    sc["tou_daytime_discount_sweep"]))
    # A discount is meaningless under a flat tariff: keep only discount 0 there.
    combos = [c for c in combos if not (c[2] == "flat" and c[3] != 0.0)]

    rows = []
    t0 = time.time()
    for i, (pen, phi, tariff, disc) in enumerate(combos, 1):
        c = {k: (v.copy() if isinstance(v, dict) else v) for k, v in cfg.items()}
        c["tariff"] = {**cfg["tariff"], "daytime_discount_per_kwh": disc}
        c["_tariff_mode"] = tariff

        # phi is a RESPONSE to the price signal, not an independent input.
        # Under a flat tariff there is no incentive to shift, so households
        # cook on the measured baseline split (phi_effective = 0). Applying
        # phi to both arms would make the tariff purely a revenue change and
        # no substitution could ever appear.
        phi_eff = phi if (tariff == "tou" and disc > 0) else 0.0
        builder = make_load_builder(cfg, n_households, pen, phi_eff, seed)
        s, m, _ = size_system(c, builder, resource, connections,
                              diesel_kw=cfg["diesel_kw"],
                              max_unmet=cfg["reliability"]["max_unmet_demand_fraction"],
                              pv_range=tuple(cfg["sizing"]["pv_range"]),
                              batt_range=tuple(cfg["sizing"]["battery_range"]))
        if s is None:
            rows.append({"penetration": pen, "phi": phi, "phi_effective": phi_eff,
                         "tariff": tariff, "discount": disc, "feasible": False})
            continue
        rows.append({"penetration": pen, "phi": phi, "phi_effective": phi_eff,
                     "tariff": tariff, "discount": disc, "feasible": True,
                     "pv_kw": s["pv_kw"], "battery_kwh": s["battery_kwh"],
                     "lcoe": m["lcoe"], "npv": m["npv"], "irr": m["irr"],
                     "unmet_fraction": m["unmet_fraction"],
                     "capex": m["total_capex"]})
        el = time.time() - t0
        print(f"[{i}/{len(combos)}] pen={pen} phi={phi} {tariff} d={disc} -> "
              f"PV {s['pv_kw']:.0f} kW batt {s['battery_kwh']:.0f} kWh "
              f"LCOE {m['lcoe']:.3f}  ({el/i:.1f}s/scenario)")

    df = pd.DataFrame(rows)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df


def substitution_frontier(df):
    """Avoided battery capacity: flat baseline minus ToU, at matched pen/phi."""
    flat = (df[(df.tariff == "flat") & df.feasible]
            .set_index(["penetration", "phi"]).battery_kwh)
    tou = df[(df.tariff == "tou") & df.feasible].copy()
    tou["battery_flat"] = tou.set_index(["penetration", "phi"]).index.map(flat)
    tou["avoided_battery_kwh"] = tou.battery_flat - tou.battery_kwh
    return tou


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--country", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.params))
    raise SystemExit("Wire cfg/resource loading to your params.yaml layout, "
                     "then call run(). See demo_sweep.py for a worked example.")


if __name__ == "__main__":
    main()
