"""Why cost per kWh falls while the price paid per kWh rises (s4.1, s4.3, s5.1).

Two effects of the same extra kilowatt-hours:

* Cost of supply. The LCOE is split into per-connection costs (the connection,
  its share of soft costs, and operation), which do not change with use, and
  the cost of solar, battery and inverter (with their soft costs and battery
  replacement), which grows with demand. Cooking spreads the first over much
  more energy.
* Price paid. Under banded tariffs more of the energy is billed in the upper
  bands, so the average price per kWh rises. `bill_example` works through the
  monthly bill of the simulated average household with and without cooking.

Writes results/cost_vs_price.csv (one row per site and adoption level) and
results/bill_example.csv (one row per site, year one).
"""
import pandas as pd

from esmap import lcoe_components
from final_cfg import KES_USD, RWF_USD
from model import _band_rate, average_billed_rate, simulate
from run_scenarios import make_load_builder
from viability import headline_sizing

SUPPLY = ["pv", "pv_soft", "battery", "battery_soft", "battery_replacement",
          "inverter", "inverter_soft"]
FX = {"rwanda": ("RWF", RWF_USD), "kenya": ("KES", KES_USD)}


def run(cfg, site, scenarios, resource, n_households, connections, seed=42,
        penetrations=(0.0, 0.5, 1.0)):
    """Cost of supply and average price paid at each adoption level, on the
    least-cost flat-tariff sizing the sweep found for that level."""
    rows = []
    for pen in penetrations:
        sizing, _ = headline_sizing(scenarios, site, n_households, connections, pen)
        b = make_load_builder(cfg, n_households, pen, 0.0, seed)
        comp = lcoe_components(cfg, sizing, b, resource)
        df, m = simulate(cfg, sizing, b, resource, "flat")
        price = average_billed_rate(cfg, sizing, b, resource)
        disc = (1 + cfg["finance"]["discount_rate_real"]) ** df.year.values
        rows.append({
            "site": site, "penetration": pen, "pv_kw": sizing["pv_kw"], "battery_kwh": sizing["battery_kwh"],
            "gross_capex": m["capex_items"]["_gross_capex"],
            "kwh_per_connection_year1": float(df.served_kwh.iloc[0]) / connections,
            "served_kwh_pv": float((df.served_kwh.values / disc).sum()),
            "lcoe": m["lcoe"], "per_connection_fixed": comp["per_connection_fixed"],
            "supply": sum(comp[k] for k in SUPPLY),
            "avg_price_paid": price, "lcoe_over_price": m["lcoe"] / price,
            "gap_per_kwh": m["lcoe"] - price, "npv": m["npv"]})
    return pd.DataFrame(rows)


def bill_example(cfg, site, kwh_no_cooking, kwh_cooking):
    """Monthly bill of the average household without and with cooking."""
    t = cfg["tariff"]
    cur, fx = FX[site]
    out = {"site": site, "currency": cur,
           "kwh_no_cooking": kwh_no_cooking, "kwh_cooking": kwh_cooking}
    for tag, kwh in (("no_cooking", kwh_no_cooking), ("cooking", kwh_cooking)):
        rate = _band_rate(kwh, t)
        out[f"rate_{tag}_usd"] = rate
        out[f"bill_{tag}_usd"] = rate * kwh
        out[f"bill_{tag}_local"] = rate * kwh * fx
    # price of one more kWh at the cooking household's use (marginal rate)
    out["marginal_rate_cooking_usd"] = (_band_rate(kwh_cooking + 1, t) * (kwh_cooking + 1)
                                        - _band_rate(kwh_cooking, t) * kwh_cooking)
    out["lifeline_rate_usd"] = t["bands"][0][1] if t.get("bands") else t["flat_rate_per_kwh"]
    out["energy_ratio"] = kwh_cooking / kwh_no_cooking
    out["bill_ratio"] = out["bill_cooking_usd"] / out["bill_no_cooking_usd"]
    out["price_ratio"] = out["rate_cooking_usd"] / out["rate_no_cooking_usd"]
    return out
