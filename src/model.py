"""Microgrid technical + financial model, refactored for scenario sweeps.

Derived from achilala_ESM_Assignment9. Structural changes:
  * No global state. Everything takes a cfg dict -> scenarios can be swept.
  * Battery: round-trip efficiency, depth-of-discharge floor, applied fade.
  * Wind removed (the original returned rated power regardless of wind speed).
  * Resource data comes from NASA POWER hourly, not daily interpolation.
  * LCOE added.
  * Time-of-use tariffs added.
  * Seeded RNG -> reproducible.
"""
from dataclasses import dataclass, field

import numpy as np
import numpy_financial as npf
import pandas as pd

HOURS = 8760


# ----------------------------------------------------------------- components
class PVGenerator:
    def __init__(self, capacity_kw, temp_coeff=-0.004, noct=45.0, degradation=0.008):
        self.capacity_kw = capacity_kw
        self.temp_coeff = temp_coeff
        self.noct = noct
        self.degradation = degradation

    def output(self, ghi, tair, year_index):
        """Vectorised DC output (kW) for an array of hours."""
        tcell = tair + (ghi / 800.0) * (self.noct - 20.0)
        p = self.capacity_kw * (ghi / 1000.0) * (1 + self.temp_coeff * (tcell - 25.0))
        p = np.maximum(p, 0.0)
        return p * (1 - self.degradation) ** (year_index - 1)


class Battery:
    """Bucket model with round-trip efficiency, DoD floor and applied fade.

    Renamed from KiBaM: this is not a kinetic two-tank model and should not
    claim to be one.
    """

    def __init__(self, capacity_kwh, rte=0.90, dod=0.80, cycle_life=3000,
                 start_soc_fraction=0.5, max_c_rate=0.5, eol_capacity_loss=0.2):
        self.nominal = capacity_kwh
        self.usable = capacity_kwh * dod
        self.eta_1way = np.sqrt(rte)          # split RTE across charge+discharge
        self.dod = dod
        self.throughput_limit = capacity_kwh * dod * cycle_life
        self.max_power_kw = capacity_kwh * max_c_rate
        self.eol_capacity_loss = eol_capacity_loss
        self.soc = self.usable * start_soc_fraction
        self.cumulative_discharge = 0.0
        self.energy_in = 0.0                  # DC into the cell, for audit
        self.energy_out = 0.0                 # DC out of the cell, for audit

    @property
    def fade(self):
        if self.throughput_limit <= 0:
            return 0.0
        return min(self.cumulative_discharge / self.throughput_limit, 1.0)

    def effective_capacity(self):
        return self.usable * (1 - self.eol_capacity_loss * self.fade)

    def _clamp(self):
        """Fade shrinks capacity; stored energy above the new ceiling is lost."""
        cap = self.effective_capacity()
        if self.soc > cap:
            self.soc = cap

    def discharge(self, energy_needed_dc):
        if energy_needed_dc <= 0 or self.soc <= 0:
            return 0.0
        self._clamp()
        deliverable = min(self.soc * self.eta_1way, self.max_power_kw)
        delivered = min(energy_needed_dc, deliverable)
        self.soc -= delivered / self.eta_1way
        self.energy_out += delivered          # output side, comparable to energy_in
        self.cumulative_discharge += delivered
        return delivered

    def charge(self, energy_avail_dc):
        if energy_avail_dc <= 0:
            return 0.0
        self._clamp()
        space = self.effective_capacity() - self.soc
        if space <= 0:
            return 0.0
        stored = min(energy_avail_dc * self.eta_1way, space, self.max_power_kw)
        self.soc += stored
        self.energy_in += stored / self.eta_1way
        return stored / self.eta_1way


class DieselGenerator:
    def __init__(self, capacity_kw, min_load_ratio=0.3,
                 fuel_intercept=0.08415, fuel_slope=0.246):
        self.capacity_kw = capacity_kw
        self.min_load_kw = capacity_kw * min_load_ratio
        self.fuel_intercept = fuel_intercept
        self.fuel_slope = fuel_slope
        self.fuel = 0.0
        self.runtime = 0.0

    def step(self, power_kw):
        if power_kw > 0 and self.capacity_kw > 0:
            op = max(power_kw, self.min_load_kw)
            self.fuel += self.fuel_intercept * self.capacity_kw + self.fuel_slope * op
            self.runtime += 1.0
        return power_kw


# ------------------------------------------------------------------- dispatch
def dispatch_year(load_kw, ghi, tair, cfg, sizing, battery, year_index):
    """One year of hourly merit-order dispatch. Returns per-hour arrays."""
    pv = PVGenerator(sizing["pv_kw"],
                     cfg["pv"]["temp_coeff_per_c"],
                     cfg["pv"]["noct_c"],
                     cfg["pv"].get("degradation_rate", 0.008))
    gen = DieselGenerator(sizing.get("diesel_kw", 0.0))

    inv_eff = cfg["bos"]["inverter_eff"]
    inv_kw = sizing["pv_kw"] / cfg["bos"]["dc_ac_ratio"]
    derate = cfg["pv"]["derate_factor"]

    pv_dc = pv.output(ghi, tair, year_index) * derate

    served = np.zeros(HOURS)
    unmet = np.zeros(HOURS)
    pv_to_load = np.zeros(HOURS)
    batt_to_load = np.zeros(HOURS)
    diesel_to_load = np.zeros(HOURS)
    curtailed = np.zeros(HOURS)

    for h in range(HOURS):
        remaining = load_kw[h]

        # 1. PV direct
        pv_ac = min(pv_dc[h] * inv_eff, inv_kw)
        used = min(pv_ac, remaining)
        remaining -= used
        pv_to_load[h] = used

        # 2. surplus PV to battery
        surplus_dc = pv_dc[h] - (used / inv_eff if inv_eff else 0.0)
        if surplus_dc > 0:
            absorbed = battery.charge(surplus_dc)
            curtailed[h] = surplus_dc - absorbed

        # 3. battery to load
        if remaining > 0:
            dc_needed = remaining / inv_eff
            dc_out = battery.discharge(dc_needed)
            delivered = dc_out * inv_eff
            remaining -= delivered
            batt_to_load[h] = delivered

        # 4. diesel
        if remaining > 0 and gen.capacity_kw > 0:
            d = min(remaining, gen.capacity_kw)
            gen.step(d)
            remaining -= d
            diesel_to_load[h] = d

        unmet[h] = max(remaining, 0.0)
        served[h] = load_kw[h] - unmet[h]

    supply = pv_to_load + batt_to_load + diesel_to_load
    residual = float(np.abs(supply + unmet - load_kw).max())

    return {"served": served, "unmet": unmet, "pv_to_load": pv_to_load,
            "batt_to_load": batt_to_load, "diesel_to_load": diesel_to_load,
            "curtailed": curtailed, "fuel_l": gen.fuel, "runtime_h": gen.runtime,
            "battery_fade": battery.fade, "balance_residual_kw": residual}


# ------------------------------------------------------------------- finances
def _band_rate(monthly_kwh_per_hh, t):
    """Rate for a household consuming this much in a month.

    Two regimes, because Rwanda and Kenya differ:
      telescopic=False (Kenya, since April 2023): total consumption selects ONE
        band and that single rate applies to every unit.
      telescopic=True (Rwanda): each block is charged at its own rate.
    Returns (effective_rate_per_kwh).
    """
    bands = t.get("bands")
    if not bands:
        return t["flat_rate_per_kwh"]

    if not t.get("telescopic", False):
        for upper, rate in bands:
            if monthly_kwh_per_hh <= upper:
                return rate
        return bands[-1][1]

    # telescopic: charge each block at its own rate, return the blended rate
    remaining, cost, lower = monthly_kwh_per_hh, 0.0, 0.0
    for upper, rate in bands:
        block = min(remaining, upper - lower)
        if block <= 0:
            break
        cost += block * rate
        remaining -= block
        lower = upper
    if remaining > 0:
        cost += remaining * bands[-1][1]
    return cost / monthly_kwh_per_hh if monthly_kwh_per_hh > 0 else bands[0][1]


def tariff_revenue(served_kw, cfg, tariff_mode, n_households=None):
    """Revenue for one year.

    Band rates depend on each household's MONTHLY consumption, so the year is
    processed month by month. This matters for eCooking: in Rwanda, crossing
    20 kWh/month moves a household from Rwf 89 to Rwf 310 per kWh, so adoption
    itself changes the price paid. A flat rate cannot represent that.
    """
    t = cfg["tariff"]
    hours = np.arange(HOURS) % 24
    discount = np.zeros(HOURS)
    if tariff_mode == "tou":
        lo, hi = t["daytime_window_hours"]
        discount[(hours >= lo) & (hours < hi)] = t["daytime_discount_per_kwh"]

    n_hh = n_households or t.get("n_households")
    if not t.get("bands") or not n_hh:
        rate = np.full(HOURS, t["flat_rate_per_kwh"], dtype=float) - discount
        return float((served_kw * rate).sum() * t["collection_rate"])

    # month boundaries on a 365-day year
    edges = np.cumsum([0] + [d * 24 for d in
                             (31,28,31,30,31,30,31,31,30,31,30,31)])
    revenue = 0.0
    for a, b in zip(edges[:-1], edges[1:]):
        seg = served_kw[a:b]
        monthly_per_hh = seg.sum() / n_hh
        base = _band_rate(monthly_per_hh, t)
        rate = np.maximum(base - discount[a:b], 0.0)
        revenue += float((seg * rate).sum())
    return revenue * t["collection_rate"]


def required_subsidy(cfg, sizing, load_builder, resource, tariff_mode,
                     target_irr=None, max_fraction=0.95, tol=1e-3):
    """Smallest CAPEX grant fraction that lifts IRR to the target.

    Answers the policy question directly: what share of capital must a donor or
    results-based-financing facility cover for this project to clear a
    commercial hurdle rate at the regulated tariff?
    Returns (fraction, irr_at_that_fraction) or (None, best_irr) if unreachable.
    """
    target = target_irr if target_irr is not None else cfg["finance"]["target_irr"]

    def irr_at(frac):
        c = {k: (v.copy() if isinstance(v, dict) else v) for k, v in cfg.items()}
        c["capex"] = {**cfg["capex"], "_grant_fraction": frac}
        _, m = simulate(c, sizing, load_builder, resource, tariff_mode)
        return m["irr"]

    hi = irr_at(max_fraction)
    if not (hi == hi) or hi < target:
        return None, hi
    lo_f, hi_f = 0.0, max_fraction
    while hi_f - lo_f > tol:
        mid = (lo_f + hi_f) / 2
        r = irr_at(mid)
        if (r == r) and r >= target:
            hi_f = mid
        else:
            lo_f = mid
    return hi_f, irr_at(hi_f)


def capex(cfg, sizing):
    c = cfg["capex"]
    inv_kw = sizing["pv_kw"] / cfg["bos"]["dc_ac_ratio"]
    items = {
        "pv": sizing["pv_kw"] * c["pv_per_kw"],
        "battery": sizing["battery_kwh"] * c["battery_per_kwh"],
        "diesel": sizing.get("diesel_kw", 0.0) * c["diesel_per_kw"],
        "inverter": inv_kw * c["inverter_per_kw"],
        "connections": sizing["connections"] * c["connection_per_customer"],
    }
    subtotal = sum(items.values())
    items["soft"] = subtotal * c["soft_cost_fraction"]
    total = sum(items.values())
    # Gross (pre-grant) cost of the physical asset. Operating cost must be
    # derived from this, never from the post-grant figure: a donor paying for
    # the plant does not make the plant cheaper to run.
    items["_gross_capex"] = total
    grant = c.get("_grant_fraction", 0.0)
    if grant:
        items["grant"] = -total * grant
        total *= (1 - grant)
    return total, items


def fixed_opex_year_one(cfg, sizing, gross_capex):
    """Year-1 fixed operating cost, on the basis named in cfg['opex']['basis'].

    Two bases are supported and the choice must be explicit, because they are
    not interchangeable. At 300 connections:

      per_customer   $80/customer/yr            -> $24,000/yr at any system size
      capex_fraction 4% of gross CAPEX + staff  -> $17.3k at 0% eCooking
                                                   $48.0k at 100% eCooking

    The capex_fraction basis makes operating cost scale with plant size, which
    works against the utilisation finding and in favour of the viability gap.
    AMDA and SEforALL both report OPEX per customer per year, which is the
    basis the manuscript claims in s3.7, so that is the default here.

    gross_capex is the PRE-grant figure. Deriving OPEX from post-grant CAPEX
    (the previous behaviour) meant a 95% grant cut operating cost by 95% too,
    which flattered the capital-subsidy solver.
    """
    o = cfg["opex"]
    basis = o.get("basis")
    if basis is None:
        raise KeyError(
            "cfg['opex']['basis'] must be set explicitly to 'per_customer' or "
            "'capex_fraction'. It was previously implicit, and the value the "
            "code used ('capex_fraction') was not the one the manuscript "
            "described ('per_customer').")
    if basis == "per_customer":
        return o["per_customer_year"] * sizing["connections"]
    if basis == "capex_fraction":
        return (gross_capex * o["om_fraction_of_capex_per_year"]
                + o["staff_annual"])
    raise ValueError(f"unknown opex basis {basis!r}")


def financials(annual, cfg, sizing, total_capex, gross_capex=None):
    """annual: list of dicts, one per project year.

    total_capex is net of any grant (it is what the investor puts in).
    gross_capex is the full cost of the asset and drives operating cost.
    """
    f = cfg["finance"]
    df = pd.DataFrame(annual)
    esc_opex = (1 + cfg["opex"]["escalation_rate"]) ** (df.year - 1)
    esc_fuel = (1 + cfg["opex"]["fuel_escalation_rate"]) ** (df.year - 1)

    if gross_capex is None:
        gross_capex = total_capex
    fixed = fixed_opex_year_one(cfg, sizing, gross_capex)
    df["fixed_opex"] = fixed * esc_opex
    df["fuel_cost"] = df.fuel_l * cfg["opex"]["fuel_cost_per_litre"] * esc_fuel
    df["opex"] = df.fixed_opex + df.fuel_cost

    # battery replacement
    df["replacement"] = 0.0
    ry = cfg["battery"].get("replacement_year")
    if ry and ry <= f["project_life_years"]:
        df.loc[df.year == ry, "replacement"] = (
            sizing["battery_kwh"] * cfg["capex"]["battery_per_kwh"])

    df["ebitda"] = df.revenue - df.opex
    dep = total_capex / f["project_life_years"]
    df["ebt"] = df.ebitda - dep
    df["tax"] = np.where(df.ebt > 0, df.ebt * f["tax_rate"], 0.0)
    df["cash_flow"] = df.ebitda - df["tax"] - df.replacement

    flows = np.concatenate([[-total_capex], df.cash_flow.values])
    r = f["discount_rate_real"]
    npv = npf.npv(r, flows)
    try:
        irr = npf.irr(flows)
    except Exception:
        irr = np.nan

    yrs = np.arange(len(df)) + 1
    disc = (1 + r) ** yrs
    cost_pv = total_capex + ((df.opex + df.replacement).values / disc).sum()
    energy_pv = (df.served_kwh.values / disc).sum()
    lcoe = cost_pv / energy_pv if energy_pv > 0 else np.nan

    return df, {"npv": float(npv), "irr": float(irr) if irr == irr else np.nan,
                "lcoe": float(lcoe), "total_capex": float(total_capex)}


# ---------------------------------------------------------------- entry point
def simulate(cfg, sizing, load_builder, resource, tariff_mode="flat"):
    """One full scenario. Pure function of its arguments - no globals.

    load_builder(year_index) -> 8760 array of kW
    resource: dict with 'ghi' and 'tair', each 8760 arrays
    """
    def _new_battery():
        b = cfg["battery"]
        return Battery(sizing["battery_kwh"], b["round_trip_efficiency"],
                       b["depth_of_discharge"], b["cycle_life"],
                       b.get("start_soc_fraction", 0.5),
                       b.get("max_c_rate", 0.5),
                       b.get("eol_capacity_loss", 0.2))

    battery = _new_battery()
    annual = []
    replace_year = cfg["battery"].get("replacement_year")
    for y in range(1, cfg["finance"]["project_life_years"] + 1):
        # Physical replacement, not just a cash line: a new battery resets
        # state of charge and accumulated fade.
        if replace_year and y == replace_year + 1:
            battery = _new_battery()
        load = load_builder(y)
        r = dispatch_year(load, resource["ghi"], resource["tair"],
                          cfg, sizing, battery, y)
        annual.append({
            "year": y,
            "served_kwh": r["served"].sum(),
            "unmet_kwh": r["unmet"].sum(),
            "demand_kwh": load.sum(),
            "fuel_l": r["fuel_l"],
            "runtime_h": r["runtime_h"],
            "curtailed_kwh": r["curtailed"].sum(),
            "battery_fade": r["battery_fade"],
            "balance_residual_kw": r["balance_residual_kw"],
            "revenue": tariff_revenue(r["served"], cfg, tariff_mode,
                                      sizing.get("households",
                                                 sizing.get("connections"))),
        })
    total_capex, capex_items = capex(cfg, sizing)
    df, metrics = financials(annual, cfg, sizing, total_capex,
                             gross_capex=capex_items["_gross_capex"])
    metrics["gross_capex"] = float(capex_items["_gross_capex"])
    # Curtailment was computed every hour and then discarded. It is the
    # physical justification for a daytime discount, so surface it.
    metrics["curtailed_fraction"] = float(
        df.curtailed_kwh.sum() / (df.curtailed_kwh.sum() + df.served_kwh.sum()))
    metrics["unmet_fraction"] = float(df.unmet_kwh.sum() / df.demand_kwh.sum())
    metrics["max_balance_residual_kw"] = float(df.balance_residual_kw.max())
    metrics["capex_items"] = capex_items
    return df, metrics


def required_tariff(cfg, sizing, load_builder, resource, target_irr=None,
                    lo=0.01, hi=3.0, tol=1e-4):
    """Flat cost-reflective tariff ($/kWh) that just meets the target IRR.

    The complement to required_subsidy. Where a capital grant cannot rescue a
    project — because revenue fails to cover OPEX at the regulated tariff — this
    gives the tariff that would. The gap between it and the regulated tariff is
    the per-kWh subsidy the regulator is implicitly asking someone to absorb.
    """
    target = target_irr if target_irr is not None else cfg["finance"]["target_irr"]

    def irr_at(rate):
        c = {k: (v.copy() if isinstance(v, dict) else v) for k, v in cfg.items()}
        c["tariff"] = {**cfg["tariff"], "flat_rate_per_kwh": rate, "bands": None}
        _, m = simulate(c, sizing, load_builder, resource, "flat")
        return m["irr"]

    top = irr_at(hi)
    if not (top == top) or top < target:
        return None, top
    while hi - lo > tol:
        mid = (lo + hi) / 2
        r = irr_at(mid)
        if (r == r) and r >= target:
            hi = mid
        else:
            lo = mid
    return hi, irr_at(hi)
