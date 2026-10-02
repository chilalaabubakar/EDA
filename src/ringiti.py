"""Phase 3: benchmark the model against the operating Ringiti mini-grid.

Ringiti Island has a solar-battery mini-grid commissioned in 2018 (s4). A
reviewer will ask why the paper models a 300-household archetype there and
never compares it with the real plant. This module runs the model at the real
installation's connection count and compares capacity per connection, storage
per kWp and tariff with the installed system.

The installed-system figures are NOT filled in: they must come from a
citable source (developer disclosure, EPRA tariff determination, REREC/KOSAP
records, or a published case study). Until they are, run() returns the
modelled side and marks the comparison "source needed" rather than
inventing a benchmark.
"""
import copy

import pandas as pd

from run_scenarios import make_load_builder
from sizing import size_system

RINGITI_ACTUAL = {
    "source": None,                 # citation for every number below
    "commissioned": 2018,
    "connections": None,            # customers connected
    "pv_kw": None,
    "battery_kwh": None,
    "inverter_kw": None,
    "tariff_usd_per_kwh": None,     # EPRA-approved, converted at KES_USD
    "tariff_kes_per_kwh": None,
    "annual_kwh_sold": None,
}


def run(cfg, res, seed=42, actual=RINGITI_ACTUAL, penetrations=(0.0, 0.5, 1.0),
        sizing_kw=None):
    n = actual["connections"] or 300
    rows = []
    for pen in penetrations:
        b = make_load_builder(cfg, n, pen, 0.0, seed)
        s, m, _ = size_system(cfg, b, res, n, **(sizing_kw or {}))
        rows.append({"basis": f"model, eCooking {pen:.0%}", "connections": n,
                     "pv_kw": s["pv_kw"], "battery_kwh": s["battery_kwh"],
                     "inverter_kw": s.get("inverter_kw"),
                     "w_per_connection": 1000 * s["pv_kw"] / n,
                     "kwh_storage_per_kwp": s["battery_kwh"] / s["pv_kw"],
                     "lcoe": m["lcoe"],
                     "kwh_per_connection_year1": b(1).sum() / n})
    have = all(actual[k] is not None for k in ("connections", "pv_kw", "battery_kwh"))
    if have:
        rows.append({"basis": "installed (" + str(actual["source"]) + ")",
                     "connections": actual["connections"], "pv_kw": actual["pv_kw"],
                     "battery_kwh": actual["battery_kwh"],
                     "inverter_kw": actual["inverter_kw"],
                     "w_per_connection": 1000 * actual["pv_kw"] / actual["connections"],
                     "kwh_storage_per_kwp": actual["battery_kwh"] / actual["pv_kw"],
                     "lcoe": None,
                     "kwh_per_connection_year1": (actual["annual_kwh_sold"] / actual["connections"]
                                                  if actual["annual_kwh_sold"] else None)})
    else:
        rows.append({"basis": "installed: SOURCE NEEDED - fill RINGITI_ACTUAL"})
    df = pd.DataFrame(rows)
    df["regulated_tariff_model"] = cfg["tariff"]["flat_rate_per_kwh"]
    df["tariff_installed"] = actual["tariff_usd_per_kwh"]
    return df
