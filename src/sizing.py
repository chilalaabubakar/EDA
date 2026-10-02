"""Least-cost sizing search under a reliability constraint.

Two stages, because a naive full grid costs ~1.4 min per scenario and there are
90 scenarios:

  1. Coarse feasibility screen on year-1 dispatch only (cheap, no financials).
  2. Fine search around the coarse optimum, scoring the survivors with the full
     multi-year simulate() so the reported LCOE is the real one.
"""
import numpy as np

from model import Battery, dispatch_year, simulate


def _unmet_fraction(cfg, sizing, load_builder, resource, design_year):
    """Screen on the DESIGN year, not year 1.

    Demand grows and PV degrades, so year 1 is the easiest year of the project.
    Sizing against it produces systems that breach the reliability constraint
    later in life - every candidate then fails the full multi-year check. The
    binding year is the last one.
    """
    load = load_builder(design_year)
    b = Battery(sizing["battery_kwh"],
                cfg["battery"]["round_trip_efficiency"],
                cfg["battery"]["depth_of_discharge"],
                cfg["battery"]["cycle_life"],
                cfg["battery"].get("start_soc_fraction", 0.5),
                cfg["battery"].get("max_c_rate", 0.5),
                cfg["battery"].get("eol_capacity_loss", 0.2))
    r = dispatch_year(load, resource["ghi"], resource["tair"], cfg, sizing, b,
                      design_year)
    return r["unmet"].sum() / load.sum()


def _capex_proxy(cfg, pv_kw, batt_kwh):
    c = cfg["capex"]
    return pv_kw * c["pv_per_kw"] + batt_kwh * c["battery_per_kwh"]


def size_system(cfg, load_builder, resource, connections, diesel_kw=0.0,
                max_unmet=0.05, pv_range=(10, 250), batt_range=(0, 800),
                coarse_pv=25.0, coarse_batt=100.0,
                fine_pv=5.0, fine_batt=20.0, top_k=6, design_year=None,
                verbose=False):
    """Returns (best_sizing, best_metrics, trace)."""
    if design_year is None:
        design_year = cfg["finance"]["project_life_years"]
    pv_lo, pv_hi = pv_range
    b_lo, b_hi = batt_range

    # ---- stage 1: coarse feasibility on year 1 -----------------------------
    feasible = []
    for pv in np.arange(pv_lo, pv_hi + 1e-9, coarse_pv):
        for bt in np.arange(b_lo, b_hi + 1e-9, coarse_batt):
            s = {"pv_kw": float(pv), "battery_kwh": float(bt),
                 "diesel_kw": diesel_kw, "connections": connections}
            u = _unmet_fraction(cfg, s, load_builder, resource, design_year)
            if u <= max_unmet:
                feasible.append((_capex_proxy(cfg, pv, bt), pv, bt, u))
                break          # smallest feasible battery at this PV; go wider
    if not feasible:
        return None, None, []

    feasible.sort()
    _, pv0, bt0, _ = feasible[0]

    # ---- stage 2: fine search around the coarse optimum --------------------
    cands = []
    for pv in np.arange(max(pv_lo, pv0 - coarse_pv), pv0 + coarse_pv + 1e-9, fine_pv):
        for bt in np.arange(max(b_lo, bt0 - coarse_batt), bt0 + coarse_batt + 1e-9, fine_batt):
            s = {"pv_kw": float(pv), "battery_kwh": float(bt),
                 "diesel_kw": diesel_kw, "connections": connections}
            u = _unmet_fraction(cfg, s, load_builder, resource, design_year)
            if u <= max_unmet:
                cands.append((_capex_proxy(cfg, pv, bt), s))
    if not cands:
        return None, None, []

    cands.sort(key=lambda x: x[0])
    trace = []
    best, best_m = None, None
    for _, s in cands[:top_k]:
        df, m = simulate(cfg, s, load_builder, resource,
                         tariff_mode=cfg.get("_tariff_mode", "flat"))
        if m["unmet_fraction"] > max_unmet:
            continue                       # failed once degradation applied
        trace.append({**s, **{k: m[k] for k in ("lcoe", "npv", "unmet_fraction")}})
        if best_m is None or m["lcoe"] < best_m["lcoe"]:
            best, best_m = s, m
    if verbose:
        print(f"  coarse opt pv={pv0} batt={bt0}; {len(cands)} fine candidates")
    return best, best_m, trace
