"""Phase 3: benchmark the model against the operating Ringiti mini-grid.

Ringiti Island has had a solar-battery mini-grid since August 2018 (s3.2).
This module runs the model at the installed system's customer count and
compares solar capacity and solar energy per customer with the plant.

Published figures (RINGITI_ACTUAL): 20 kW of solar commissioned in August
2018 (TaiyangNews, 27 Sep 2018, "Renewvia Energy Commissions Microgrid
Facilities"; African Energy, 28 Sep 2018) and 140 customers (Renewvia
Energy, "Minigrid Sites", https://www.renewvia.com/minigrid-sites, accessed
13 Oct 2026). Battery size, inverter size, tariff and energy sold are not
published, so the comparison is on solar capacity and on the most energy the
installed solar could deliver per customer, which bounds what the plant can
serve whatever its battery.
"""
import numpy as np
import pandas as pd

from model import _pv_dc
from run_scenarios import make_load_builder
from sizing import size_system

RINGITI_ACTUAL = {
    "source": "TaiyangNews 2018; Renewvia Energy minigrid sites",
    "commissioned": 2018,
    "connections": 140,             # customers (Renewvia, minigrid sites page)
    "pv_kw": 20.0,                  # TaiyangNews / African Energy, Sep 2018
    "battery_kwh": None,            # not published
    "inverter_kw": None,            # not published
    "tariff_usd_per_kwh": None,     # not published
    "annual_kwh_sold": None,        # not published
}


def ac_yield_per_kw(cfg, res, year_index=1):
    """AC energy a 1 kW solar array delivers in a year, before any is spilled
    or stored: the upper bound on what each installed kW can serve."""
    dc = _pv_dc(cfg, {"pv_kw": 1.0}, np.asarray(res["ghi"]), np.asarray(res["tair"]),
                year_index)
    return float(dc.sum() * cfg["bos"]["inverter_eff"])


def run(cfg, res, seed=42, actual=RINGITI_ACTUAL, penetrations=(0.0, 0.5, 1.0),
        sizing_kw=None):
    n = actual["connections"] or 300
    life = cfg["finance"]["project_life_years"]
    yld = ac_yield_per_kw(cfg, res)
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
                     "kwh_per_connection_year1": b(1).sum() / n,
                     "kwh_per_connection_final_year": b(life).sum() / n})
    if actual["connections"] and actual["pv_kw"]:
        bt = actual["battery_kwh"]
        rows.append({"basis": "installed (" + str(actual["source"]) + ")",
                     "connections": actual["connections"], "pv_kw": actual["pv_kw"],
                     "battery_kwh": bt, "inverter_kw": actual["inverter_kw"],
                     "w_per_connection": 1000 * actual["pv_kw"] / actual["connections"],
                     "kwh_storage_per_kwp": bt / actual["pv_kw"] if bt else None,
                     "lcoe": None,
                     "kwh_per_connection_year1": (actual["annual_kwh_sold"] / actual["connections"]
                                                  if actual["annual_kwh_sold"] else None),
                     "kwh_per_connection_final_year": None,
                     "max_solar_kwh_per_connection_year":
                         actual["pv_kw"] * yld / actual["connections"]})
    else:
        rows.append({"basis": "installed: SOURCE NEEDED - fill RINGITI_ACTUAL"})
    df = pd.DataFrame(rows)
    df["ac_kwh_per_kw_year1"] = yld
    if actual["pv_kw"]:
        df["pv_multiple_of_installed"] = df.w_per_connection / (
            1000 * actual["pv_kw"] / actual["connections"])
    df["regulated_tariff_model"] = cfg["tariff"]["flat_rate_per_kwh"]
    df["tariff_installed"] = actual["tariff_usd_per_kwh"]
    return df
