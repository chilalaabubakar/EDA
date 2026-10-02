"""Phase 2: sweep the ToU discount properly - and what it shows.

s5.2 reports "approximately 90 kWh of avoided storage per US cent of daytime
discount" and s6.5 offers it to regulators as a design parameter. It is a
slope through two points (0 and 2 cents), and the model cannot produce a
slope at all: households shift the full nominal phi for ANY positive discount
and nothing for zero (run_scenarios.effective_phi). Avoided storage is a STEP
function of the discount. A 0.5-cent discount displaces exactly what a
2-cent one does; only the revenue cost differs.

This module makes that visible and replaces the slope with a quantity the
model does support:

  step response (as modelled)  avoided storage vs discount, and the operator's
      NPV change (storage capital saved minus discount revenue forgone). The
      break-even discount - where the operator stops gaining - is a defensible
      regulatory parameter; "kWh per cent" is not.

  elastic response (ILLUSTRATIVE, flagged)  phi_eff = phi_max * min(1, d/d_sat),
      showing what a response curve would have to look like for a per-cent
      slope to mean anything. d_sat is not estimated; it is an assumption.
"""
import numpy as np
import pandas as pd

from run_scenarios import scenario_row

# Up to just under the regulated rates ($0.128-0.147/kWh): the daytime rate
# is floored at zero, so larger discounts are meaningless.
DISCOUNTS = (0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10, 0.125)


def sweep(cfg, res, n, conn, seed=42, phis=(0.3, 0.5), discounts=DISCOUNTS,
          penetration=1.0, response="step", d_sat=0.02, sizing_kw=None):
    cache = {}
    flat = scenario_row(cfg, res, n, conn, penetration, 0.0, "flat", 0.0, seed,
                        sizing_kw=sizing_kw, sizing_cache=cache)
    rows = []
    for phi in phis:
        for d in discounts:
            if response == "step":
                phi_in = phi
            elif response == "elastic":
                phi_in = phi * min(1.0, d / d_sat) if d_sat > 0 else phi
            else:
                raise ValueError(response)
            r = scenario_row(cfg, res, n, conn, penetration, phi_in, "tou", d, seed,
                             sizing_kw=sizing_kw, sizing_cache=cache)
            rows.append({"response": response, "phi_nominal": phi,
                         "phi_effective": r["phi_effective"], "discount": d,
                         "battery_kwh": r["battery_kwh"],
                         "avoided_battery_kwh": flat["battery_kwh"] - r["battery_kwh"],
                         "lcoe": r["lcoe"],
                         "lcoe_change_pct": 100 * (r["lcoe"] / flat["lcoe"] - 1),
                         "npv": r["npv"],
                         "operator_npv_gain": r["npv"] - flat["npv"]})
    return pd.DataFrame(rows), flat


def break_even_discount(df):
    """Per phi: the largest discount at which the operator's NPV gain is still
    >= 0, by linear interpolation on the swept grid (step response only)."""
    out = []
    for phi, g in df[df.discount > 0].groupby("phi_nominal"):
        g = g.sort_values("discount")
        x, y = g.discount.values, g.operator_npv_gain.values
        if (y >= 0).all():
            be, note = np.nan, f"operator still gains at {x[-1]:.3f} $/kWh; widen the sweep"
        elif (y < 0).all():
            be, note = 0.0, "operator loses at every positive discount"
        else:
            i = np.where(y < 0)[0][0]
            be = x[i - 1] + y[i - 1] * (x[i] - x[i - 1]) / (y[i - 1] - y[i])
            note = "interpolated"
        out.append({"phi_nominal": phi, "break_even_discount": be, "note": note,
                    "avoided_battery_kwh": g.avoided_battery_kwh.iloc[0]})
    return pd.DataFrame(out)


def is_step_function(df, tol=1e-9):
    """True if avoided storage is identical at every positive discount."""
    pos = df[df.discount > 0]
    return bool((pos.groupby("phi_nominal").avoided_battery_kwh.nunique() == 1).all())
