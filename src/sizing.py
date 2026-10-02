"""Least-cost sizing search under a reliability constraint.

    size_system(cfg, load_builder, resource, connections) -> (sizing, metrics, trace)

WHAT CHANGED (Phases 1-2) AND WHY
---------------------------------
1. The constraint the paper states is now the constraint the code enforces.
   s3.5: "least-cost configuration meeting an unmet-demand constraint of 5%
   ... screened on the final project year". v4 screened year 20 against a
   FRESH battery, then accepted candidates on LIFETIME-AVERAGE unmet. With a
   10-year-old battery in year 20 the final-year unmet ran at 7-12%, while
   the reported (lifetime) figure was 1-2% - the "1-2% against a 5%
   constraint" a reviewer would read as an early stop. Default now:
   reliability_metric="worst_year" on the full multi-year simulation.

2. The screen is conservative: design-year dispatch with the battery at its
   end-of-life capacity (screen_battery_fade=1.0), so it never discards a
   candidate the full simulation would accept... and the full simulation has
   the final word.

3. Candidates are ranked by their real LCOE from simulate(), not by a
   PV+battery CAPEX proxy that ignored inverter, connections and soft cost.
   `full_grid_search` exists to check that this finds the grid optimum
   (Phase 2; see sizing_check.py).

4. Inverter sizing is explicit (Phase 2). cfg["bos"]["inverter_sizing"]:
     "pv"    v4 convention: pv_kw / dc_ac_ratio, battery output not limited.
     "load"  hybrid inverter rated to the design-year peak load x headroom,
             capping total AC output (PV + battery). DEFAULT.
"""
import numpy as np

from model import Battery, dispatch_year, simulate

DEFAULTS = dict(max_unmet=0.05, pv_range=(10, 250), batt_range=(0, 800),
                coarse_pv=25.0, coarse_batt=100.0, fine_pv=5.0, fine_batt=20.0,
                design_year=None, reliability_metric="worst_year",
                screen_battery_fade=1.0, extra_batt_steps=2)


def _res(resource, year):
    return resource(year) if callable(resource) else resource


def inverter_for(cfg, pv_kw, load_builder, design_year):
    """sizing fields for the inverter, per cfg['bos']['inverter_sizing']."""
    mode = cfg["bos"].get("inverter_sizing", "pv")
    if mode == "pv":
        return {}
    if mode == "load":
        peak = float(load_builder(design_year).max())
        step = cfg["bos"].get("inverter_step_kw", 5.0)
        kw = step * np.ceil(peak * cfg["bos"].get("inverter_headroom", 1.25) / step)
        return {"inverter_kw": float(kw), "inverter_limits_battery": True}
    raise ValueError(f"unknown inverter_sizing {mode!r}")


def design_year_unmet(cfg, sizing, load_builder, resource, design_year,
                      battery_fade=1.0):
    """Unmet fraction in the design year with a battery aged to `battery_fade`
    (0 = new, 1 = end of life)."""
    load = load_builder(design_year)
    b = Battery.from_cfg(cfg, sizing["battery_kwh"])
    b.cumulative_discharge = battery_fade * b.throughput_limit
    b.soc = min(b.soc, b.effective_capacity())
    res = _res(resource, design_year)
    r = dispatch_year(load, res["ghi"], res["tair"], cfg, sizing, b, design_year)
    return r["unmet"].sum() / load.sum()


def _reliability(m, metric, design_year=None):
    """worst_year: worst year up to and including the design year (all years
    when the design year is the last). lifetime: the v4 metric."""
    if metric == "worst_year":
        by = m["unmet_fraction_by_year"]
        return max(by[:design_year] if design_year else by)
    return m["unmet_fraction"]


def _sizing(cfg, pv, bt, connections, load_builder, design_year):
    s = {"pv_kw": float(pv), "battery_kwh": float(bt), "connections": connections}
    s.update(inverter_for(cfg, pv, load_builder, design_year))
    return s


def size_system(cfg, load_builder, resource, connections, verbose=False, **kw):
    """Returns (best_sizing, best_metrics, trace)."""
    o = {**DEFAULTS, **kw}
    dy = o["design_year"] or cfg["finance"]["project_life_years"]
    mode = cfg.get("_tariff_mode", "flat")
    pv_lo, pv_hi = o["pv_range"]
    b_lo, b_hi = o["batt_range"]
    batt_grid = np.arange(b_lo, b_hi + 1e-9, o["coarse_batt"])

    def screen_ok(pv, bt):
        s = _sizing(cfg, pv, bt, connections, load_builder, dy)
        return design_year_unmet(cfg, s, load_builder, resource, dy,
                                 o["screen_battery_fade"]) <= o["max_unmet"]

    # ---- stage 1: coarse screen - smallest feasible battery at each PV ------
    frontier = []
    for pv in np.arange(pv_lo, pv_hi + 1e-9, o["coarse_pv"]):
        if not screen_ok(pv, batt_grid[-1]):
            continue
        lo, hi = 0, len(batt_grid) - 1           # binary search on the grid
        while lo < hi:
            mid = (lo + hi) // 2
            if screen_ok(pv, batt_grid[mid]):
                hi = mid
            else:
                lo = mid + 1
        frontier.append((float(pv), float(batt_grid[lo])))
    if not frontier:
        return None, None, []

    cache = {}

    def evaluate(pv, bt):
        key = (round(pv, 6), round(bt, 6))
        if key not in cache:
            s = _sizing(cfg, pv, bt, connections, load_builder, dy)
            _, m = simulate(cfg, s, load_builder, resource, tariff_mode=mode)
            cache[key] = (s, m)
        return cache[key]

    # rank the coarse frontier by true LCOE, then refine around the best
    scored = []
    for pv, bt in frontier:
        s, m = evaluate(pv, bt)
        scored.append((m["lcoe"], pv, bt))
    scored.sort()
    _, pv0, bt0 = scored[0]

    # ---- stage 2: fine search around the coarse optimum, true LCOE ----------
    trace, best, best_m = [], None, None
    for pv in np.arange(max(pv_lo, pv0 - o["coarse_pv"]),
                        pv0 + o["coarse_pv"] + 1e-9, o["fine_pv"]):
        fine = np.arange(max(b_lo, bt0 - o["coarse_batt"]),
                         min(b_hi, bt0 + 2 * o["coarse_batt"]) + 1e-9, o["fine_batt"])
        found = 0
        for bt in fine:
            s, m = evaluate(pv, bt)
            ok = _reliability(m, o["reliability_metric"], dy) <= o["max_unmet"]
            trace.append({**s, "lcoe": m["lcoe"], "npv": m["npv"], "feasible": ok,
                          "unmet_fraction": m["unmet_fraction"],
                          "worst_year_unmet_fraction": m["worst_year_unmet_fraction"]})
            if not ok:
                continue
            if best_m is None or m["lcoe"] < best_m["lcoe"]:
                best, best_m = s, m
            found += 1
            if found > o["extra_batt_steps"]:
                break                 # more battery at this PV only adds cost
    if verbose:
        print(f"  coarse opt pv={pv0} batt={bt0}; {len(trace)} fine evaluations")
    return best, best_m, trace


def full_grid_search(cfg, load_builder, resource, connections, pv_values,
                     batt_values, max_unmet=0.05, reliability_metric="worst_year",
                     design_year=None):
    """Exhaustive search: every (pv, battery) pair through the full simulation.
    Slow by design - it is the check on size_system, not a replacement."""
    dy = design_year or cfg["finance"]["project_life_years"]
    mode = cfg.get("_tariff_mode", "flat")
    rows, best, best_m = [], None, None
    for pv in pv_values:
        for bt in batt_values:
            s = _sizing(cfg, pv, bt, connections, load_builder, dy)
            _, m = simulate(cfg, s, load_builder, resource, tariff_mode=mode)
            ok = _reliability(m, reliability_metric, dy) <= max_unmet
            rows.append({**s, "lcoe": m["lcoe"], "feasible": ok,
                         "worst_year_unmet_fraction": m["worst_year_unmet_fraction"],
                         "unmet_fraction": m["unmet_fraction"]})
            if ok and (best_m is None or m["lcoe"] < best_m["lcoe"]):
                best, best_m = s, m
    return best, best_m, rows
