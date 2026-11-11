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

from final_cfg import KES_USD, RWF_USD
from model import _band_rate, average_billed_rate, simulate
from run_scenarios import make_load_builder
from viability import headline_sizing

FX = {"rwanda": ("RWF", RWF_USD), "kenya": ("KES", KES_USD)}


def lcoe_components(cfg, sizing, builder, res):
    """Levelised cost split by cost line ($/kWh, same discounting as LCOE).

    per_connection_fixed  the connection, its share of soft costs and the
                          customer part of operating cost: these do not change
                          with how much a household uses.
    supply                everything that grows with demand: solar, battery
                          and inverter with their soft costs, the second-stage
                          expansion, battery replacement, the plant part of
                          operating cost and any generator fuel.
    """
    df, m = simulate(cfg, sizing, builder, res)
    r = cfg["finance"]["discount_rate_real"]
    disc = (1 + r) ** df.year.values
    energy = (df.served_kwh.values / disc).sum()
    items = m["capex_items"]
    hard = [k for k in ("pv", "battery", "inverter", "connections", "generator") if k in items]
    sub = sum(items[k] for k in hard)
    out = {k: items[k] / energy for k in hard}
    for k in hard:                                           # allocate soft cost
        out[k + "_soft"] = items["soft"] * items[k] / sub / energy
    out["expansion"] = (df.capex_addition.values / disc).sum() / energy
    out["battery_replacement"] = (df.replacement.values / disc).sum() / energy
    customer = cfg["opex"].get("per_customer_year", 0.0) * sizing["connections"] \
        if cfg["opex"]["basis"] in ("split", "per_customer") else 0.0
    esc = (1 + cfg["opex"]["escalation_rate"]) ** (df.year.values - 1)
    out["opex_customer"] = (customer * esc / disc).sum() / energy
    out["opex_plant"] = (df.opex.values / disc).sum() / energy - out["opex_customer"]
    out["total"] = sum(out.values())
    out["lcoe_check"] = m["lcoe"]
    out["per_connection_fixed"] = (out["connections"] + out["connections_soft"]
                                   + out["opex_customer"])
    out["supply"] = out["total"] - out["per_connection_fixed"]
    return out


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
            "pv_kw_final": sizing["stages"][-1]["pv_kw"] if sizing.get("stages") else sizing["pv_kw"],
            "battery_kwh_bought": sizing["battery_kwh"] + (
                sizing["stages"][-1]["battery_kwh"] if sizing.get("stages") else sizing["battery_kwh"]),
            "capital_pv": float(m["capex_items"]["_gross_capex"]
                                + ((df.capex_addition + df.replacement).values / disc).sum()),
            "curtailed_fraction": m["curtailed_fraction"],
            "opex_per_connection_year1": float(df.opex.iloc[0]) / connections,
            "opex_per_connection_final": float(df.opex.iloc[-1]) / connections,
            "revenue_per_connection_year1": float(df.revenue.iloc[0]) / connections,
            "gross_capex": m["capex_items"]["_gross_capex"],
            "kwh_per_connection_year1": float(df.served_kwh.iloc[0]) / connections,
            "served_kwh_pv": float((df.served_kwh.values / disc).sum()),
            "lcoe": m["lcoe"], "per_connection_fixed": comp["per_connection_fixed"],
            "supply": comp["supply"],
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
