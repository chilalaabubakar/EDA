"""Cost the operating subsidy, and the part of it that cooking adds.

Three outputs:

  cost()          the subsidy for one design: US$ per connection per year (the
                  same amount every year in real terms), per village, in
                  present value, alone and alongside capital grants.

  by_adoption()   the same at each share of households cooking, plus the
                  INCREMENT per cooking household: (subsidy with cooking minus
                  subsidy without) divided by the number of cooking households.
                  This is the measure of the burden cooking places on whoever
                  funds the operator. The levelised cost is not: it falls with
                  cooking mainly because per-connection costs are divided by
                  more kilowatt-hours, while the loss grows.

  carbon()        the increment per tonne of CO2 avoided, for two estimates of
                  the firewood a cooking household stops burning.

Emission parameters are assumptions with named sources (CARBON). None is fitted.
"""
import numpy as np
import pandas as pd

from model import (average_billed_rate, required_operating_subsidy,
                   required_tariff, simulate)

CARBON = {
    # Wood: IPCC 2006 GL Vol.2 Ch.2 default CO2 EF 112 tCO2/TJ (NCV);
    # NCV 15.6 GJ/t -> 1.747 tCO2/t wood. CO2 only.
    "tco2_per_t_wood": 112 * 15.6 / 1000,
    # Basis A, useful-energy parity: wood displaced per kWh of cooker
    # electricity = kWh x 3.6 MJ x eta_epc / (eta_fire x NCV). Cooker 0.80,
    # three-stone fire 0.15, NCV 15.6 MJ/kg -> ~1.23 kg/kWh. A LOWER bound:
    # it credits the pressure cooker only with the heat it delivers.
    "eta_epc": 0.80, "eta_fire": 0.15, "wood_ncv_mj_per_kg": 15.6,
    # Basis B, the default baseline of the CDM cookstove methodologies
    # (AMS-II.G, AMS-I.E): 0.5 t of wood per person per year, for a household
    # of four. An UPPER bound: it assumes cooking displaces all the wood a
    # household burns, and the default itself is thought to be high.
    "cdm_wood_t_per_person_year": 0.5, "household_size": 4.0,
    # Fraction of non-renewable biomass: uncertain and contested; swept.
    "fnrb_sweep": (0.1, 0.3, 0.5, 0.8),
}


def wood_kg_per_kwh(p=CARBON):
    return 3.6 * p["eta_epc"] / (p["eta_fire"] * p["wood_ncv_mj_per_kg"])


def annuity_factor(r, n):
    return (1 - (1 + r) ** -n) / r


def cost(cfg, sizing, builder, res, villages_households=300,
         grant_fractions=(0.0, 0.5, 0.95)):
    """Operating subsidy for one design, alone and with capital grants."""
    conn = sizing["connections"]
    r = cfg["finance"]["discount_rate_real"]
    life = cfg["finance"]["project_life_years"]
    df, m = simulate(cfg, sizing, builder, res)
    tar, _ = required_tariff(cfg, sizing, builder, res)
    disc = (1 + r) ** df.year.values
    reg = average_billed_rate(cfg, sizing, builder, res)
    out = {"lcoe": m["lcoe"], "npv": m["npv"], "gross_capex": m["gross_capex"],
           "regulated_tariff": reg, "cost_reflective_tariff": tar,
           "gap_per_kwh": (tar - reg) if tar else None,
           "served_kwh_year1": float(df.served_kwh.iloc[0]),
           "served_kwh_mean": float(df.served_kwh.mean())}
    for g in grant_fractions:
        s, irr = required_operating_subsidy(cfg, sizing, builder, res, grant_fraction=g)
        key = f"grant{int(round(100 * g))}"
        out[f"opsub_{key}_usd_per_conn_year"] = s
        if s is not None:
            out[f"opsub_{key}_usd_per_village_year1"] = s * villages_households
            # level stream: present value = annual amount x annuity factor
            out[f"opsub_{key}_npv_usd"] = s * conn * annuity_factor(r, life)
            out[f"opsub_{key}_per_kwh"] = float(
                s * conn * annuity_factor(r, life) / (df.served_kwh.values / disc).sum())
    # the saving per dollar of grant is the capital recovery factor
    g0, g50 = out.get("opsub_grant0_usd_per_conn_year"), out.get("opsub_grant50_usd_per_conn_year")
    if g0 is not None and g50 is not None:
        out["implied_capital_recovery_factor"] = (g0 - g50) * conn / (0.5 * m["gross_capex"])
        out["capital_recovery_factor"] = 1.0 / annuity_factor(r, life)
    return out


def by_adoption(cfg, site, designs, res, connections):
    """One row per adoption level. `designs` maps penetration -> (sizing, builder).

    incremental_usd_per_cooking_hh_year is measured against the no-cooking
    design of the same village.
    """
    rows = []
    for pen in sorted(designs):
        sizing, builder = designs[pen]
        df, m = simulate(cfg, sizing, builder, res)
        s, _ = required_operating_subsidy(cfg, sizing, builder, res)
        cook_kwh = float(builder.cooking_in_year(1).sum())
        disc = (1 + cfg["finance"]["discount_rate_real"]) ** df.year.values
        energy_pv = float((df.served_kwh.values / disc).sum())
        # cooking energy served, present value (unserved cooking is not sold)
        cook_pv = float(sum(builder.cooking_in_year(y).sum() * sv / dm / (1 + cfg["finance"]["discount_rate_real"]) ** y
                            for y, sv, dm in zip(df.year, df.served_kwh, df.demand_kwh)))
        rows.append({"site": site, "penetration": pen,
                     "energy_pv_kwh": energy_pv, "cost_pv": m["lcoe"] * energy_pv,
                     "cooking_pv_kwh": cook_pv,
                     "lcoe": m["lcoe"], "npv": m["npv"],
                     "gross_capex": m["gross_capex"],
                     "avg_price_paid": average_billed_rate(cfg, sizing, builder, res),
                     "served_kwh_year1": float(df.served_kwh.iloc[0]),
                     "cooking_households": int(round(connections * pen)),
                     "cooking_kwh_per_cooking_hh_year": (
                         cook_kwh / (connections * pen) if pen else 0.0),
                     "opsub_usd_per_conn_year": s,
                     "opsub_usd_per_village_year": s * connections})
    out = pd.DataFrame(rows)
    base = out[out.penetration == 0.0].iloc[0]
    n = out.cooking_households.replace(0, np.nan)
    out["incremental_usd_per_village_year"] = (out.opsub_usd_per_village_year
                                               - base.opsub_usd_per_village_year)
    out["incremental_usd_per_cooking_hh_year"] = out.incremental_usd_per_village_year / n
    out["incremental_usd_per_cooking_kwh"] = (out.incremental_usd_per_cooking_hh_year
                                              / out.cooking_kwh_per_cooking_hh_year.replace(0, np.nan))
    # Long-run cost of supplying cooking energy: the extra cost of the larger
    # system divided by the cooking energy it serves. Cooking adds to the
    # subsidy when it is sold below this price and reduces it when sold above.
    out["incremental_cost_per_cooking_kwh"] = ((out.cost_pv - base.cost_pv)
                                               / out.cooking_pv_kwh.replace(0, np.nan))
    out["npv_change_vs_no_cooking"] = out.npv - base.npv
    out["npv_change_per_cooking_hh"] = out.npv_change_vs_no_cooking / n
    out["lcoe_change_pct_vs_no_cooking"] = 100 * (out.lcoe / base.lcoe - 1)
    return out


def carbon(burden_row, carbon=CARBON):
    """US$ per tonne of CO2 avoided, from the INCREMENTAL subsidy per cooking
    household and the wood that household stops burning each year."""
    inc = float(burden_row.incremental_usd_per_cooking_hh_year)
    kwh = float(burden_row.cooking_kwh_per_cooking_hh_year)
    wood = {"useful_energy": kwh * wood_kg_per_kwh(carbon) / 1000.0,
            "cdm_default": carbon["cdm_wood_t_per_person_year"] * carbon["household_size"]}
    rows = []
    for basis, t_wood in wood.items():
        for f in carbon["fnrb_sweep"]:
            tco2 = t_wood * carbon["tco2_per_t_wood"] * f
            rows.append({"site": burden_row.site, "wood_basis": basis,
                         "wood_t_per_cooking_hh_year": t_wood, "fnrb": f,
                         "tco2_per_cooking_hh_year": tco2,
                         "incremental_usd_per_cooking_hh_year": inc,
                         "usd_per_tco2": inc / tco2})
    return pd.DataFrame(rows)
