"""Phase 2: reconcile the modelled LCOE with ESMAP's benchmark.

ESMAP (2022) [ref 3] reports a reference LCOE near $0.55/kWh at a 22% load
factor for household-only systems, falling towards $0.20/kWh above 40%. The
modelled LCOEs are several times higher, and a reviewer will ask why before
reading s5. This module answers with a cumulative waterfall, moving one
convention at a time from the paper's to a benchmark-like one:

  0  headline             12% real, sized for the worst year of 20 with 5%/yr
                          demand growth, 300 households, per-customer OPEX
  1  discount rate        -> ESMAP_DISCOUNT_RATE
  2  sizing convention    no demand growth: the plant is sized for, and sells,
                          year-1 demand throughout (no 2.5x growth reserve)
  3  demand level         consumption per connection scaled by
                          DEMAND_MULTIPLIER (same hourly shape): the per-
                          connection fixed costs (connection, its soft cost,
                          per-customer OPEX) are spread over more kWh

plus `lcoe_components`: the headline LCOE split by cost line, in $/kWh. The
load factor is reported at every step. It is NOT the driver: the headline
system already runs at ~30%, above ESMAP's 22% household-only anchor, so the
reconciliation paragraph should say the gap is demand level per connection,
the growth reserve and the discount rate - not load shape.

The order matters (steps interact); it is reported as run. The drivers named
in the reconciliation paragraph are the steps with the largest moves.

ASSUMPTIONS TO CONFIRM against ESMAP (2022) before quoting: the discount rate
and load-factor anchors below are taken from the manuscript's own reading of
the report, not re-verified here.
"""
import copy

import numpy as np
import pandas as pd

from model import simulate
from sizing import size_system

ESMAP_ANCHORS = {"lcoe_at_22pct_lf": 0.55, "lcoe_above_40pct_lf": 0.20}
ESMAP_DISCOUNT_RATE = 0.10          # TO CONFIRM against ESMAP (2022)
DEMAND_MULTIPLIER = 2.0             # ILLUSTRATIVE - kWh/connection scaling


def load_factor(load):
    return float(load.mean() / load.max()) if load.max() > 0 else np.nan


def waterfall(cfg, builder, res, connections, sizing_kw=None,
              esmap_rate=ESMAP_DISCOUNT_RATE, demand_multiplier=DEMAND_MULTIPLIER):
    steps = []

    def record(label, c, b):
        s, m, _ = size_system(c, b, res, connections, **(sizing_kw or {}))
        y1 = b(1)
        steps.append({"step": label, "lcoe": m["lcoe"], "pv_kw": s["pv_kw"],
                      "battery_kwh": s["battery_kwh"],
                      "discount_rate": c["finance"]["discount_rate_real"],
                      "demand_growth": c["demand"]["annual_growth_rate"],
                      "load_factor_year1": load_factor(y1),
                      "kwh_per_connection_year1": y1.sum() / connections,
                      "curtailed_fraction": m["curtailed_fraction"]})

    c = copy.deepcopy(cfg)
    record("0 headline", c, builder)

    c["finance"]["discount_rate_real"] = esmap_rate
    record(f"1 discount rate {esmap_rate:.0%}", c, builder)

    c["demand"]["annual_growth_rate"] = 0.0
    flat_b = lambda y: builder(1)
    record("2 no growth reserve (size to year-1 demand)", c, flat_b)

    base = builder(1)
    record(f"3 demand per connection x{demand_multiplier:g}", c,
           lambda y: base * demand_multiplier)

    df = pd.DataFrame(steps)
    df["change_vs_previous"] = df.lcoe.diff()
    df["share_of_total_change"] = df.change_vs_previous / (df.lcoe.iloc[-1] - df.lcoe.iloc[0])
    return df


def lcoe_components(cfg, sizing, builder, res):
    """Headline LCOE split by cost line ($/kWh, same discounting as LCOE)."""
    df, m = simulate(cfg, sizing, builder, res)
    r = cfg["finance"]["discount_rate_real"]
    disc = (1 + r) ** df.year.values
    energy = (df.served_kwh.values / disc).sum()
    items = m["capex_items"]
    sub = sum(v for k, v in items.items() if k in ("pv", "battery", "inverter", "connections"))
    soft = items["soft"]
    out = {k: items[k] / energy for k in ("pv", "battery", "inverter", "connections")}
    for k in ("pv", "battery", "inverter", "connections"):     # allocate soft cost
        out[k + "_soft"] = soft * items[k] / sub / energy
    out["battery_replacement"] = (df.replacement.values / disc).sum() / energy
    out["opex"] = (df.opex.values / disc).sum() / energy
    out["total"] = sum(out.values())
    out["lcoe_check"] = m["lcoe"]
    out["per_connection_fixed"] = (out["connections"] + out["connections_soft"]
                                   + out["opex"])
    return out
