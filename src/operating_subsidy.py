"""Phase 3: cost the operating subsidy the paper says the arithmetic points to.

Converts "the gap is $X/kWh" into figures a funder can budget:
  * $/connection/yr and $/village/yr from the third inverse solver
    (model.required_operating_subsidy), alone and alongside capital grants
  * the same from the simple gap arithmetic (gap x kWh served), as a check
  * NPV of the subsidy stream over the project life
  * $/tCO2 against collected firewood, across a range of fNRB values,
    compared with clean-cooking carbon credit prices and RBF grant levels

ALL emission and price parameters below are ASSUMPTIONS with a named source
to confirm. None is fitted. Values marked None are placeholders the author
must fill from a dated source before the comparison is reported; the code
reports "source needed" rather than inventing a figure.
"""
import numpy as np
import pandas as pd

from model import required_operating_subsidy, required_tariff, simulate

CARBON = {
    # Wood: IPCC 2006 GL Vol.2 Ch.2 default CO2 EF 112 tCO2/TJ (NCV);
    # NCV 15.6 GJ/t -> 1.747 tCO2/t wood. CO2 only. TO CONFIRM.
    "tco2_per_t_wood": 112 * 15.6 / 1000,
    # Wood displaced per kWh of EPC electricity: useful-energy parity,
    # kWh_e x 3.6 MJ x eta_epc / (eta_fire x NCV). eta_epc 0.80, three-stone
    # fire 0.15, NCV 15.6 MJ/kg -> ~1.23 kg/kWh. Conservative relative to
    # per-meal comparisons in the MECS diaries. TO CONFIRM.
    "eta_epc": 0.80, "eta_fire": 0.15, "wood_ncv_mj_per_kg": 15.6,
    # Fraction of non-renewable biomass: highly uncertain and contested;
    # swept rather than assumed.
    "fnrb_sweep": (0.1, 0.3, 0.5, 0.8),
    # Clean-cooking credit prices, USD/tCO2e. INDICATIVE RANGE ONLY - replace
    # with a dated market source (e.g. Ecosystem Marketplace, MSCI/Trove)
    # before quoting.
    "credit_price_range": (3.0, 15.0),
    # Rwanda results-based financing grant per connection (USD). PLACEHOLDER:
    # fill from the Rwanda Energy Access and Quality Improvement Project /
    # BRD RBF window documentation.
    "rwanda_rbf_per_connection_usd": None,
}


def wood_kg_per_kwh(p=CARBON):
    return 3.6 * p["eta_epc"] / (p["eta_fire"] * p["wood_ncv_mj_per_kg"])


def cooking_kwh_per_year(cfg, builder, years):
    """Electric cooking energy in each project year, with demand growth."""
    g = cfg["demand"]["annual_growth_rate"]
    return float(builder.cooking.sum()) * (1 + g) ** (np.asarray(years) - 1)


def cost(cfg, sizing, builder, res, villages_households=300,
         grant_fractions=(0.0, 0.5, 0.95), carbon=CARBON):
    conn = sizing["connections"]
    r = cfg["finance"]["discount_rate_real"]
    life = cfg["finance"]["project_life_years"]
    df, m = simulate(cfg, sizing, builder, res)
    reg = cfg["tariff"]["flat_rate_per_kwh"]
    tar, _ = required_tariff(cfg, sizing, builder, res)
    disc = (1 + r) ** df.year.values
    out = {"lcoe": m["lcoe"], "regulated_tariff": reg, "cost_reflective_tariff": tar,
           "gap_per_kwh": (tar - reg) if tar else None,
           "served_kwh_year1": float(df.served_kwh.iloc[0]),
           "served_kwh_mean": float(df.served_kwh.mean())}
    if tar:
        out["gap_usd_per_connection_year_simple"] = (tar - reg) * df.served_kwh.mean() / conn

    for g in grant_fractions:
        s, irr = required_operating_subsidy(cfg, sizing, builder, res, grant_fraction=g)
        key = f"grant{int(round(100 * g))}"
        out[f"opsub_{key}_usd_per_conn_year"] = s
        if s is not None:
            esc = cfg["opex"]["escalation_rate"]
            stream = s * conn * (1 + esc) ** (df.year.values - 1)
            out[f"opsub_{key}_usd_per_village_year1"] = s * villages_households
            out[f"opsub_{key}_npv_usd"] = float((stream / disc).sum())
            out[f"opsub_{key}_per_kwh"] = float((stream / disc).sum()
                                                / (df.served_kwh.values / disc).sum())

    # carbon: cooking electricity -> wood displaced -> CO2 avoided
    cook_kwh = cooking_kwh_per_year(cfg, builder, df.year.values)
    served_share = (df.served_kwh / df.demand_kwh).values      # unmet cooking stays on wood
    wood_t = cook_kwh * served_share * wood_kg_per_kwh(carbon) / 1000.0
    out["wood_displaced_t_year1"] = float(wood_t[0])
    s0 = out.get("opsub_grant0_usd_per_conn_year")
    for f in carbon["fnrb_sweep"]:
        t = wood_t * carbon["tco2_per_t_wood"] * f
        out[f"tco2_avoided_life_fnrb{f}"] = float(t.sum())
        if s0 is not None:
            esc = cfg["opex"]["escalation_rate"]
            stream = s0 * conn * (1 + esc) ** (df.year.values - 1)
            # undiscounted $ per undiscounted tonne, the convention credit prices use
            out[f"usd_per_tco2_fnrb{f}"] = float(stream.sum() / t.sum()) if t.sum() else None
    lo, hi = carbon["credit_price_range"]
    out["credit_price_lo"], out["credit_price_hi"] = lo, hi
    out["rwanda_rbf_per_connection_usd"] = carbon["rwanda_rbf_per_connection_usd"] or "source needed"
    return out
