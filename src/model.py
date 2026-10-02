"""Microgrid technical + financial model, refactored for scenario sweeps.

Derived from achilala_ESM_Assignment9. Structural changes:
  * No global state. Everything takes a cfg dict -> scenarios can be swept.
  * Battery: round-trip efficiency, depth-of-discharge floor, applied fade.
  * Wind removed (the original returned rated power regardless of wind speed).
  * Resource data comes from NASA POWER hourly, not daily interpolation.
  * LCOE added.
  * Time-of-use tariffs added.
  * Seeded RNG -> reproducible.

Phase 1 (integrity):
  * DIESEL CUT. Every published scenario ran diesel_kw = 0, so the generator,
    its fuel cost and the fuel-price references described an option the
    results never used. It is removed from dispatch, CAPEX and OPEX rather than
    left as dead code a reviewer could reasonably assume was active.
  * LCOE is computed on GROSS capital cost. It is a cost metric; a capital
    grant changes who pays, not what the plant costs.
  * Hourly dispatch runs in a compiled kernel (numba when available, plain
    Python otherwise). The original class-based loop is kept verbatim as
    `dispatch_year_reference`, and tests/test_dispatch_kernel.py asserts the
    two agree to 1e-9 on every hourly series and on battery state. This is
    what makes 20-seed ensembles and full-grid sizing checks affordable.
"""
import numpy as np
import numpy_financial as npf
import pandas as pd

try:                                         # numba is optional
    from numba import njit
    HAVE_NUMBA = True
except ImportError:                          # pragma: no cover
    HAVE_NUMBA = False

    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

HOURS = 8760
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
MONTH_EDGES = np.cumsum([0] + [d * 24 for d in MONTH_DAYS])


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

    @classmethod
    def from_cfg(cls, cfg, capacity_kwh):
        b = cfg["battery"]
        return cls(capacity_kwh, b["round_trip_efficiency"],
                   b["depth_of_discharge"], b["cycle_life"],
                   b.get("start_soc_fraction", 0.5), b.get("max_c_rate", 0.5),
                   b.get("eol_capacity_loss", 0.2))

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


def inverter_kw(cfg, sizing):
    """AC inverter rating.

    Explicit sizing["inverter_kw"] wins. Otherwise the v4 convention: a PV
    inverter at pv_kw / dc_ac_ratio, which does NOT limit battery discharge.
    Phase 2 adds load-based sizing in sizing.py, which sets inverter_kw and
    the `inverter_limits_battery` flag.
    """
    if sizing.get("inverter_kw") is not None:
        return float(sizing["inverter_kw"])
    return sizing["pv_kw"] / cfg["bos"]["dc_ac_ratio"]


# ------------------------------------------------------------------- dispatch
@njit(cache=True)
def _dispatch_kernel(load, pv_dc, inv_eff, inv_kw, limit_batt,
                     soc, cum, e_in, e_out,
                     usable, eta, thr, maxp, eol):
    """Hour-by-hour merit order: PV direct -> surplus PV to battery (DC
    coupled) -> battery to load -> unmet. Mirrors Battery.charge/discharge
    operation for operation; see dispatch_year_reference.

    limit_batt: if True the inverter is a single hybrid unit and total AC
    output (PV + battery) is capped at inv_kw. If False (v4 convention) only
    PV is capped and battery discharge is not inverter-limited.
    """
    n = load.shape[0]
    pv_to_load = np.zeros(n)
    batt_to_load = np.zeros(n)
    unmet = np.zeros(n)
    curtailed = np.zeros(n)
    for h in range(n):
        remaining = load[h]
        pv_ac = min(pv_dc[h] * inv_eff, inv_kw)
        used = min(pv_ac, remaining)
        remaining -= used
        pv_to_load[h] = used

        surplus = pv_dc[h] - (used / inv_eff if inv_eff else 0.0)
        if surplus > 0:
            # --- charge (Battery.charge)
            fade = min(cum / thr, 1.0) if thr > 0 else 0.0
            cap = usable * (1 - eol * fade)
            if soc > cap:
                soc = cap
            space = cap - soc
            absorbed = 0.0
            if space > 0:
                stored = min(surplus * eta, space, maxp)
                soc += stored
                e_in += stored / eta
                absorbed = stored / eta
            curtailed[h] = surplus - absorbed

        if remaining > 0:
            ac_room = remaining
            if limit_batt:
                ac_room = min(remaining, max(inv_kw - used, 0.0))
            need = ac_room / inv_eff
            delivered = 0.0
            if need > 0 and soc > 0:
                # --- discharge (Battery.discharge)
                fade = min(cum / thr, 1.0) if thr > 0 else 0.0
                cap = usable * (1 - eol * fade)
                if soc > cap:
                    soc = cap
                deliverable = min(soc * eta, maxp)
                delivered = min(need, deliverable)
                soc -= delivered / eta
                e_out += delivered
                cum += delivered
            ac = delivered * inv_eff
            remaining -= ac
            batt_to_load[h] = ac

        unmet[h] = max(remaining, 0.0)
    return pv_to_load, batt_to_load, unmet, curtailed, soc, cum, e_in, e_out


def _pv_dc(cfg, sizing, ghi, tair, year_index):
    pv = PVGenerator(sizing["pv_kw"], cfg["pv"]["temp_coeff_per_c"],
                     cfg["pv"]["noct_c"], cfg["pv"].get("degradation_rate", 0.008))
    return pv.output(ghi, tair, year_index) * cfg["pv"]["derate_factor"]


def dispatch_year(load_kw, ghi, tair, cfg, sizing, battery, year_index):
    """One year of hourly merit-order dispatch. Returns per-hour arrays.
    `battery` carries state across years and is updated in place."""
    load = np.ascontiguousarray(load_kw, dtype=np.float64)
    pv_dc = np.ascontiguousarray(_pv_dc(cfg, sizing, ghi, tair, year_index),
                                 dtype=np.float64)
    inv_eff = float(cfg["bos"]["inverter_eff"])
    (pv_to_load, batt_to_load, unmet, curtailed, battery.soc,
     battery.cumulative_discharge, battery.energy_in, battery.energy_out) = \
        _dispatch_kernel(load, pv_dc, inv_eff, float(inverter_kw(cfg, sizing)),
                         bool(sizing.get("inverter_limits_battery", False)),
                         float(battery.soc), float(battery.cumulative_discharge),
                         float(battery.energy_in), float(battery.energy_out),
                         float(battery.usable), float(battery.eta_1way),
                         float(battery.throughput_limit),
                         float(battery.max_power_kw),
                         float(battery.eol_capacity_loss))
    served = load - unmet
    supply = pv_to_load + batt_to_load
    residual = float(np.abs(supply + unmet - load).max())
    return {"served": served, "unmet": unmet, "pv_to_load": pv_to_load,
            "batt_to_load": batt_to_load, "curtailed": curtailed,
            "battery_fade": battery.fade, "balance_residual_kw": residual}


def dispatch_year_reference(load_kw, ghi, tair, cfg, sizing, battery, year_index):
    """The v4 class-based loop (diesel removed), kept as the test oracle for
    _dispatch_kernel. Do not use in production paths: ~200x slower."""
    inv_eff = cfg["bos"]["inverter_eff"]
    inv = inverter_kw(cfg, sizing)
    limit_batt = bool(sizing.get("inverter_limits_battery", False))
    pv_dc = _pv_dc(cfg, sizing, ghi, tair, year_index)
    n = len(load_kw)
    out = {k: np.zeros(n) for k in ("unmet", "pv_to_load", "batt_to_load",
                                    "curtailed")}
    for h in range(n):
        remaining = load_kw[h]
        pv_ac = min(pv_dc[h] * inv_eff, inv)
        used = min(pv_ac, remaining)
        remaining -= used
        out["pv_to_load"][h] = used
        surplus_dc = pv_dc[h] - (used / inv_eff if inv_eff else 0.0)
        if surplus_dc > 0:
            out["curtailed"][h] = surplus_dc - battery.charge(surplus_dc)
        if remaining > 0:
            room = min(remaining, max(inv - used, 0.0)) if limit_batt else remaining
            delivered = battery.discharge(room / inv_eff) * inv_eff
            remaining -= delivered
            out["batt_to_load"][h] = delivered
        out["unmet"][h] = max(remaining, 0.0)
    out["served"] = np.asarray(load_kw) - out["unmet"]
    return out


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


def _tou_discount(t, tariff_mode):
    discount = np.zeros(HOURS)
    if tariff_mode == "tou":
        hours = np.arange(HOURS) % 24
        lo, hi = t["daytime_window_hours"]
        discount[(hours >= lo) & (hours < hi)] = t["daytime_discount_per_kwh"]
    return discount


def tariff_revenue(served_kw, cfg, tariff_mode, n_households=None):
    """Revenue for one year.

    Band rates depend on each household's MONTHLY consumption, so the year is
    processed month by month. This matters for eCooking: in Rwanda, crossing
    20 kWh/month moves a household from Rwf 89 to Rwf 310 per kWh, so adoption
    itself changes the price paid. A flat rate cannot represent that.

    Band assignment uses the MEAN household. Phase 3's household_bands module
    measures the error this introduces under a non-linear schedule.
    """
    t = cfg["tariff"]
    discount = _tou_discount(t, tariff_mode)

    n_hh = n_households or t.get("n_households")
    if not t.get("bands") or not n_hh:
        rate = np.full(HOURS, t["flat_rate_per_kwh"], dtype=float) - discount
        return float((served_kw * rate).sum() * t["collection_rate"])

    revenue = 0.0
    for a, b in zip(MONTH_EDGES[:-1], MONTH_EDGES[1:]):
        seg = served_kw[a:b]
        monthly_per_hh = seg.sum() / n_hh
        base = _band_rate(monthly_per_hh, t)
        rate = np.maximum(base - discount[a:b], 0.0)
        revenue += float((seg * rate).sum())
    return revenue * t["collection_rate"]


def capex(cfg, sizing):
    c = cfg["capex"]
    items = {
        "pv": sizing["pv_kw"] * c["pv_per_kw"],
        "battery": sizing["battery_kwh"] * c["battery_per_kwh"],
        "inverter": inverter_kw(cfg, sizing) * c["inverter_per_kw"],
        "connections": sizing["connections"] * c["connection_per_customer"],
    }
    subtotal = sum(items.values())
    items["soft"] = subtotal * c["soft_cost_fraction"]
    total = sum(items.values())
    # Gross (pre-grant) cost of the physical asset. Operating cost and LCOE
    # are derived from this, never from the post-grant figure: a donor paying
    # for the plant does not make the plant cheaper to build or run.
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
    gross_capex is the full cost of the asset; it drives operating cost and
    LCOE.

    Optional per-year columns on `annual`:
      capex_addition      extra capital spent in that year (staged expansion)
      operating_subsidy   cash received from an operating-subsidy instrument
    """
    f = cfg["finance"]
    df = pd.DataFrame(annual)
    esc_opex = (1 + cfg["opex"]["escalation_rate"]) ** (df.year - 1)

    if gross_capex is None:
        gross_capex = total_capex
    fixed = fixed_opex_year_one(cfg, sizing, gross_capex)
    df["fixed_opex"] = fixed * esc_opex
    df["opex"] = df.fixed_opex

    # battery replacement (sized to the battery in service at that time)
    df["replacement"] = 0.0
    ry = cfg["battery"].get("replacement_year")
    if ry and ry <= f["project_life_years"]:
        repl_kwh = sizing.get("replacement_battery_kwh", sizing["battery_kwh"])
        df.loc[df.year == ry, "replacement"] = (
            repl_kwh * cfg["capex"]["battery_per_kwh"])
    if "capex_addition" not in df:
        df["capex_addition"] = 0.0
    if "operating_subsidy" not in df:
        df["operating_subsidy"] = 0.0

    df["ebitda"] = df.revenue + df.operating_subsidy - df.opex
    dep = total_capex / f["project_life_years"]
    df["ebt"] = df.ebitda - dep
    df["tax"] = np.where(df.ebt > 0, df.ebt * f["tax_rate"], 0.0)
    df["cash_flow"] = (df.ebitda - df["tax"] - df.replacement
                       - df.capex_addition)

    flows = np.concatenate([[-total_capex], df.cash_flow.values])
    r = f["discount_rate_real"]
    npv = npf.npv(r, flows)
    try:
        irr = npf.irr(flows)
    except Exception:
        irr = np.nan

    yrs = np.arange(len(df)) + 1
    disc = (1 + r) ** yrs
    cost_pv = gross_capex + ((df.opex + df.replacement + df.capex_addition)
                             .values / disc).sum()
    energy_pv = (df.served_kwh.values / disc).sum()
    lcoe = cost_pv / energy_pv if energy_pv > 0 else np.nan

    return df, {"npv": float(npv), "irr": float(irr) if irr == irr else np.nan,
                "lcoe": float(lcoe), "total_capex": float(total_capex)}


# ---------------------------------------------------------------- entry point
def _resource_for(resource, year):
    """resource is either one {'ghi','tair'} dict used every year, or a
    callable year -> dict (Phase 2: interannual variability)."""
    return resource(year) if callable(resource) else resource


def simulate(cfg, sizing, load_builder, resource, tariff_mode="flat",
             operating_subsidy=None):
    """One full scenario. Pure function of its arguments - no globals.

    load_builder(year_index) -> 8760 array of kW
    resource: dict with 'ghi' and 'tair' (8760 arrays), or year -> such dict
    sizing may carry a 'stages' list for staged expansion (see sizing.py):
        [{"from_year": 1, "pv_kw": .., "battery_kwh": .., "inverter_kw": ..},
         {"from_year": 11, ...}]
    operating_subsidy: optional callable year -> USD received that year.
    """
    stages = sizing.get("stages") or [{"from_year": 1, **sizing}]
    stages = sorted(stages, key=lambda s: s["from_year"])
    replace_year = cfg["battery"].get("replacement_year")
    for s in stages[1:]:
        if replace_year is None or s["from_year"] != replace_year + 1:
            raise ValueError("expansion stages must start the year after the "
                             "battery replacement, so the enlarged bank is the "
                             "replacement bank")

    def stage_for(y):
        cur = stages[0]
        for s in stages:
            if y >= s["from_year"]:
                cur = s
        return {**sizing, **cur}

    battery = Battery.from_cfg(cfg, stages[0]["battery_kwh"])
    annual = []
    peak_load = 0.0
    for y in range(1, cfg["finance"]["project_life_years"] + 1):
        sz = stage_for(y)
        # Physical replacement, not just a cash line: a new battery resets
        # state of charge and accumulated fade.
        if replace_year and y == replace_year + 1:
            battery = Battery.from_cfg(cfg, sz["battery_kwh"])
        load = load_builder(y)
        peak_load = max(peak_load, float(load.max()))
        res = _resource_for(resource, y)
        r = dispatch_year(load, res["ghi"], res["tair"], cfg, sz, battery, y)
        annual.append({
            "year": y,
            "served_kwh": r["served"].sum(),
            "unmet_kwh": r["unmet"].sum(),
            "demand_kwh": load.sum(),
            "curtailed_kwh": r["curtailed"].sum(),
            "pv_to_load_kwh": r["pv_to_load"].sum(),
            "batt_to_load_kwh": r["batt_to_load"].sum(),
            "peak_load_kw": float(load.max()),
            "battery_fade": r["battery_fade"],
            "balance_residual_kw": r["balance_residual_kw"],
            "revenue": tariff_revenue(r["served"], cfg, tariff_mode,
                                      sizing.get("households",
                                                 sizing.get("connections"))),
            "operating_subsidy": (float(operating_subsidy(y))
                                  if operating_subsidy else 0.0),
            "capex_addition": 0.0,
        })
    # Expansion capital (added PV and inverter, plus soft costs) is spent at
    # the end of the year before the stage starts. The enlarged battery is
    # charged through the replacement line, which is sized to the new bank.
    c = cfg["capex"]
    for prev, nxt in zip(stages[:-1], stages[1:]):
        p_sz, n_sz = {**sizing, **prev}, {**sizing, **nxt}
        d_pv = max(n_sz["pv_kw"] - p_sz["pv_kw"], 0.0)
        d_inv = max(inverter_kw(cfg, n_sz) - inverter_kw(cfg, p_sz), 0.0)
        annual[nxt["from_year"] - 2]["capex_addition"] += (
            d_pv * c["pv_per_kw"] + d_inv * c["inverter_per_kw"]) * (
            1 + c["soft_cost_fraction"])

    first = {**sizing, **stages[0]}
    if len(stages) > 1:
        first["replacement_battery_kwh"] = stage_for(replace_year + 1)["battery_kwh"]
    total_capex, capex_items = capex(cfg, first)
    df, metrics = financials(annual, cfg, first, total_capex,
                             gross_capex=capex_items["_gross_capex"])
    metrics["gross_capex"] = float(capex_items["_gross_capex"])
    # Curtailment was computed every hour and then discarded. It is the
    # physical justification for a daytime discount, so surface it.
    produced = df.curtailed_kwh.sum() + df.served_kwh.sum()
    metrics["curtailed_fraction"] = float(
        df.curtailed_kwh.sum() / produced) if produced > 0 else 0.0
    metrics["unmet_fraction"] = float(df.unmet_kwh.sum() / df.demand_kwh.sum())
    by_year = (df.unmet_kwh / df.demand_kwh).tolist()
    metrics["unmet_fraction_by_year"] = by_year
    metrics["worst_year_unmet_fraction"] = float(max(by_year))
    metrics["peak_load_kw"] = peak_load
    metrics["max_balance_residual_kw"] = float(df.balance_residual_kw.max())
    metrics["capex_items"] = capex_items
    return df, metrics


def _copy_cfg(cfg):
    return {k: (v.copy() if isinstance(v, dict) else v) for k, v in cfg.items()}


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
        c = _copy_cfg(cfg)
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
        c = _copy_cfg(cfg)
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


def required_operating_subsidy(cfg, sizing, load_builder, resource,
                               tariff_mode="flat", target_irr=None,
                               grant_fraction=0.0, hi=5000.0, tol=0.01):
    """Annual operating subsidy per connection ($/connection/yr, constant in
    real terms, escalating with OPEX) that lifts IRR to the target at the
    REGULATED tariff - the third inverse solver (Phase 3).

    s6.3 concludes that "the arithmetic points to operating subsidy" without
    pricing it. This prices it. Optionally combined with a capital grant, to
    show how far a grant reduces the recurring commitment.
    Returns (usd_per_connection_year, irr) or (None, irr_at_hi).
    """
    target = target_irr if target_irr is not None else cfg["finance"]["target_irr"]
    esc = cfg["opex"]["escalation_rate"]
    conn = sizing["connections"]
    c = _copy_cfg(cfg)
    c["capex"] = {**cfg["capex"], "_grant_fraction": grant_fraction}

    def irr_at(s):
        sub = lambda y: s * conn * (1 + esc) ** (y - 1)
        _, m = simulate(c, sizing, load_builder, resource, tariff_mode,
                        operating_subsidy=sub)
        return m["irr"]

    top = irr_at(hi)
    if not (top == top) or top < target:
        return None, top
    lo = 0.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        r = irr_at(mid)
        if (r == r) and r >= target:
            hi = mid
        else:
            lo = mid
    return hi, irr_at(hi)
