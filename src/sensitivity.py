"""How far do the results depend on the assumptions?

Seed ensembles (ensemble.py) measure only the noise from random household
behaviour. The larger uncertainties are the inputs themselves. This module
re-sizes and re-costs each village, with no cooking and with full cooking,
under:

  one_at_a_time()  a low and a high value of each uncertain input
                   (capital cost, operating cost, discount rate, appliance
                   demand growth, energy per meal, collection rate, battery
                   cost, the unserved-demand limit), and both ends together

  structural()     different designs of the system or the village: a single-
                   stage build, a commercial anchor load, a backup generator

  bridge()         the steps from the previous base case to this one, so the
                   change in every headline number can be traced

Reported for each case: levelised cost with no and with full cooking, the
operator's net present value, the operating subsidy per connection, and the
INCREMENTAL subsidy per cooking household (the burden measure of s4.4).
"""
import copy

import numpy as np
import pandas as pd

from expansion import size_design
from load_builder import CookingParams
from model import (average_billed_rate, required_operating_subsidy, simulate)
from run_scenarios import make_load_builder
from sizing import _sizing

ANCHOR_KWH_DAY = 120.0      # illustrative: an ice machine, a mill and shops


def _skw(cfg):
    return dict(max_unmet=cfg["reliability"]["max_unmet_demand_fraction"],
                pv_range=tuple(cfg["sizing"]["pv_range"]),
                batt_range=tuple(cfg["sizing"]["battery_range"]))


def size_hybrid(cfg, builder, res, connections, pv_max=400.0, batt_max=1200.0,
                coarse=(25.0, 100.0), fine=(5.0, 20.0)):
    """Least-cost solar, battery and backup generator, single stage.

    The generator is rated to the largest hourly load of the project and runs
    last, so no demand goes unserved and the reliability limit never binds:
    the search simply minimises the levelised cost, fuel included, on a coarse
    grid and then on a fine one around the best coarse design.
    """
    life = cfg["finance"]["project_life_years"]
    peak = max(float(builder(y).max()) for y in (1, life))
    gen_kw = 5.0 * np.ceil(peak / 5.0)
    cache = {}

    def ev(pv, bt):
        key = (round(pv, 6), round(bt, 6))
        if key not in cache:
            s = _sizing(cfg, pv, bt, connections, builder, life)
            s["generator_kw"] = float(gen_kw)
            cache[key] = (s, simulate(cfg, s, builder, res)[1])
        return cache[key]

    def best_of(pvs, bts):
        return min(((ev(pv, bt)[1]["lcoe"], pv, bt) for pv in pvs for bt in bts))

    _, pv0, bt0 = best_of(np.arange(0.0, pv_max + 1e-9, coarse[0]),
                          np.arange(0.0, batt_max + 1e-9, coarse[1]))
    for _ in range(6):                      # re-centre until the best is inside
        _, pv1, bt1 = best_of(
            np.arange(max(0.0, pv0 - coarse[0]), pv0 + coarse[0] + 1e-9, fine[0]),
            np.arange(max(0.0, bt0 - coarse[1]), bt0 + coarse[1] + 1e-9, fine[1]))
        if (pv1, bt1) == (pv0, bt0):
            break
        pv0, bt0 = pv1, bt1
    return ev(pv0, bt0)


def evaluate(cfg, res, n, conn, seed, pen, anchor_kwh_day=0.0, generator=False,
             cooking_params=None):
    b = make_load_builder(cfg, n, pen, 0.0, seed, cooking_params, anchor_kwh_day)
    if generator:
        s, _ = size_hybrid(cfg, b, res, conn)
    else:
        s, _ = size_design(cfg, b, res, conn, **_skw(cfg))
    s = {**s, "households": n}
    df, m = simulate(cfg, s, b, res)
    sub, _ = required_operating_subsidy(cfg, s, b, res)
    st2 = s["stages"][1] if s.get("stages") else s
    return {"lcoe": m["lcoe"], "npv": m["npv"], "gross_capex": m["gross_capex"],
            "opsub": sub, "price": average_billed_rate(cfg, s, b, res),
            "pv_kw": s["pv_kw"], "battery_kwh": s["battery_kwh"],
            "pv_kw_final": st2["pv_kw"], "battery_kwh_final": st2["battery_kwh"],
            "kwh_per_conn_year1": float(df.served_kwh.iloc[0]) / conn,
            "curtailed_fraction": m["curtailed_fraction"],
            "generator_share": m["generator_share"],
            "worst_year_unmet": m["worst_year_unmet_fraction"]}


def pair(cfg, res, n, conn, seed, **kw):
    """No cooking against full cooking, both re-sized under `cfg`."""
    a = evaluate(cfg, res, n, conn, seed, 0.0, **kw)
    b = evaluate(cfg, res, n, conn, seed, 1.0, **kw)
    coll = cfg["tariff"]["collection_rate"]
    out = {}
    for k, v in a.items():
        out[k + "_zero"] = v
    for k, v in b.items():
        out[k + "_full"] = v
    out["lcoe_fall_pct"] = 100 * (1 - b["lcoe"] / a["lcoe"])
    out["npv_change"] = b["npv"] - a["npv"]
    out["incremental_usd_per_cooking_hh_year"] = b["opsub"] - a["opsub"]
    out["cost_multiple_full"] = b["lcoe"] / coll / b["price"]
    return out


# ------------------------------------------------------------ input changes
def _scaled(cfg, section, keys, factor):
    c = copy.deepcopy(cfg)
    for k in keys:
        c[section][k] = cfg[section][k] * factor
    return c


def _capital(cfg, f):
    return _scaled(cfg, "capex", ("pv_per_kw", "battery_per_kwh", "inverter_per_kw",
                                  "connection_per_customer"), f)


def _opex(cfg, f):
    return _scaled(cfg, "opex", ("per_customer_year", "plant_fraction_per_year"), f)


def _set(cfg, section, **values):
    c = copy.deepcopy(cfg)
    c[section].update(values)
    return c


def _rate(cfg, r):
    return _set(cfg, "finance", discount_rate_real=r, target_irr=r)


# name -> (low label, low (cfg, kwargs), high label, high (cfg, kwargs))
def cases(cfg):
    meal = lambda kwh: {"cooking_params": CookingParams(kwh_per_meal_mean=kwh)}
    return [
        ("Capital cost", "30% lower", (_capital(cfg, 0.7), {}),
         "30% higher", (_capital(cfg, 1.3), {})),
        ("Operating cost", "50% lower", (_opex(cfg, 0.5), {}),
         "50% higher", (_opex(cfg, 1.5), {})),
        ("Discount rate", "8%", (_rate(cfg, 0.08), {}), "20%", (_rate(cfg, 0.20), {})),
        ("Battery cost", "US$150/kWh", (_set(cfg, "capex", battery_per_kwh=150.0), {}),
         "US$450/kWh", (_set(cfg, "capex", battery_per_kwh=450.0), {})),
        ("Appliance demand growth", "none", (_set(cfg, "demand", annual_growth_rate=0.0), {}),
         "5% a year", (_set(cfg, "demand", annual_growth_rate=0.05), {})),
        ("Energy per meal", "0.25 kWh", (cfg, meal(0.25)), "0.45 kWh", (cfg, meal(0.45))),
        ("Bills collected", "100%", (_set(cfg, "tariff", collection_rate=1.0), {}),
         "80%", (_set(cfg, "tariff", collection_rate=0.8), {})),
        ("Unserved demand allowed", "10%",
         (_set(cfg, "reliability", max_unmet_demand_fraction=0.10), {}),
         "2%", (_set(cfg, "reliability", max_unmet_demand_fraction=0.02), {})),
    ]


def _favourable(cfg, sign):
    """All cost inputs at their low (sign=-1) or high (+1) end together."""
    c = _capital(cfg, 1 + 0.3 * sign)
    c = _opex(c, 1 + 0.5 * sign)
    c = _rate(c, 0.08 if sign < 0 else 0.20)
    return _set(c, "tariff", collection_rate=1.0 if sign < 0 else 0.8)


def one_at_a_time(cfg, res, n, conn, seed=42):
    base = pair(cfg, res, n, conn, seed)
    rows = [{"parameter": "Base case", "side": "base", "label": "", **base}]
    for name, lo_label, (lo_cfg, lo_kw), hi_label, (hi_cfg, hi_kw) in cases(cfg):
        rows.append({"parameter": name, "side": "low", "label": lo_label,
                     **pair(lo_cfg, res, n, conn, seed, **lo_kw)})
        rows.append({"parameter": name, "side": "high", "label": hi_label,
                     **pair(hi_cfg, res, n, conn, seed, **hi_kw)})
    rows.append({"parameter": "All cost inputs together", "side": "low",
                 "label": "all favourable", **pair(_favourable(cfg, -1), res, n, conn, seed)})
    rows.append({"parameter": "All cost inputs together", "side": "high",
                 "label": "all adverse", **pair(_favourable(cfg, +1), res, n, conn, seed)})
    df = pd.DataFrame(rows)
    for q in ("lcoe_full", "incremental_usd_per_cooking_hh_year", "opsub_full", "npv_full"):
        df[q + "_change_pct"] = 100 * (df[q] / base[q] - 1)
    return df


def structural(cfg, res, n, conn, seed=42, anchor_kwh_day=ANCHOR_KWH_DAY,
               fuel_prices=(1.0, 1.5, 2.0)):
    rows = [{"case": "Base case (two-stage solar and battery)", **pair(cfg, res, n, conn, seed)}]
    rows.append({"case": "Single-stage build, sized for the worst of 20 years",
                 **pair(_set(cfg, "sizing", build="single"), res, n, conn, seed)})
    rows.append({"case": f"Commercial anchor load, {anchor_kwh_day:g} kWh a day",
                 **pair(cfg, res, n, conn, seed, anchor_kwh_day=anchor_kwh_day)})
    for p in fuel_prices:
        rows.append({"case": f"Backup generator, diesel at US${p:.2f} a litre",
                     **pair(_set(cfg, "generator", fuel_price_per_l=p), res, n, conn, seed,
                            generator=True)})
    rows.append({"case": f"Anchor load and backup generator (diesel US${fuel_prices[1]:.2f})",
                 **pair(_set(cfg, "generator", fuel_price_per_l=fuel_prices[1]), res, n, conn,
                        seed, anchor_kwh_day=anchor_kwh_day, generator=True)})
    return pd.DataFrame(rows)


def previous_base(cfg):
    """The base case of the first submission."""
    c = copy.deepcopy(cfg)
    c["opex"].update(basis="per_customer", per_customer_year=80.0, escalation_rate=0.05)
    c["demand"].update(annual_growth_rate=0.05, cooking_growth_rate=0.05)
    c["sizing"]["build"] = "single"
    c["finance"]["target_irr"] = c["finance"]["discount_rate_real"] + 0.03
    return c


def bridge(cfg, res, n, conn, seed=42):
    """From the first submission's base case to this one, one change at a
    time (cumulative, in this order)."""
    c = previous_base(cfg)
    rows = [{"step": "0 first submission", **pair(c, res, n, conn, seed)}]
    c = _set(c, "opex", escalation_rate=cfg["opex"]["escalation_rate"])
    rows.append({"step": "1 operating cost constant in real terms", **pair(c, res, n, conn, seed)})
    c = _set(c, "opex", basis=cfg["opex"]["basis"],
             per_customer_year=cfg["opex"]["per_customer_year"],
             plant_fraction_per_year=cfg["opex"]["plant_fraction_per_year"])
    rows.append({"step": "2 operating cost split into customer and plant parts",
                 **pair(c, res, n, conn, seed)})
    c = _set(c, "demand", **cfg["demand"])
    rows.append({"step": "3 cooking energy does not grow; appliance demand grows 2% a year",
                 **pair(c, res, n, conn, seed)})
    c = _set(c, "sizing", build=cfg["sizing"]["build"])
    rows.append({"step": "4 two-stage build", **pair(c, res, n, conn, seed)})
    c = _set(c, "finance", target_irr=cfg["finance"]["target_irr"])
    rows.append({"step": "5 target return equal to the discount rate (this paper)",
                 **pair(c, res, n, conn, seed)})
    return pd.DataFrame(rows)
