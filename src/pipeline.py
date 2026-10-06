"""One entry point for every result in the paper.

    python src/pipeline.py resource            # NASA POWER -> data/processed (network)
    python src/pipeline.py mtf                 # MTF microdata -> data/processed (needs data/raw)
    python src/pipeline.py phase1              # sweep, frontier, bands, viability, tables
    python src/pipeline.py all                 # everything that does not need the network

    --synthetic   use the synthetic resource and write to results/synthetic/.
                  For smoke tests and CI only. Never quote these numbers.
    --resume      skip steps already finished in this results directory
                  (listed in <results>/.steps_done). For long runs on Colab,
                  where the runtime can be reset part-way: rerun the same
                  command and it carries on from the first unfinished step.

Each step writes CSVs into the results directory; manuscript_tables.py turns
those into the manuscript tables, and tests/test_manuscript_numbers.py checks
the .docx against them.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

# Headless: never inherit a notebook's inline backend (Colab sets
# MPLBACKEND=module://matplotlib_inline..., which this environment lacks).
os.environ["MPLBACKEND"] = "Agg"

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
sys.path.insert(0, str(SRC))

STEPS = {}


def step(name, group):
    def deco(f):
        STEPS[name] = (group, f)
        return f
    return deco


class Ctx:
    def __init__(self, args):
        self.params = yaml.safe_load(open(ROOT / args.params))
        self.synthetic = args.synthetic
        self.results = Path(args.results or (ROOT / ("results/synthetic"
                                                     if args.synthetic else "results")))
        self.results.mkdir(parents=True, exist_ok=True)
        run = self.params["run"]
        self.n, self.conn, self.seed = run["n_households"], run["connections"], run["seed"]
        self.sites = list(self.params["countries"])
        self.quick = args.quick

    def rep_year(self, site):
        return self.params["countries"][site]["representative_year"]

    def resource(self, site, year=None):
        from solar_resource import load_site_resource, synthetic_years
        y = year or self.rep_year(site)
        if self.synthetic:
            return synthetic_years(site)[y]
        return load_site_resource(site, y)

    def all_years(self, site):
        from solar_resource import resource_years, synthetic_years
        return synthetic_years(site) if self.synthetic else resource_years(site)

    def cfg(self, site):
        from final_cfg import country_cfg
        cfg = country_cfg(site)
        if self.quick:                        # CI smoke: coarse, small sweep
            cfg["scenarios"] = {**cfg["scenarios"], "penetration_sweep": [0.0, 1.0],
                                "shiftable_fraction_sweep": [0.0, 0.5]}
        return cfg

    def csv(self, name):
        return self.results / name

    def read(self, name):
        return pd.read_csv(self.results / name)


# ----------------------------------------------------------------- data steps
@step("resource", "data")
def s_resource(ctx):
    p = ctx.params["shared"]["resource"]["years"]
    subprocess.run([sys.executable, str(SRC / "fetch_power.py"), "--params",
                    "params.yaml", "--start", str(p[0]), "--end", str(p[1])],
                   cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(SRC / "load_resource.py"), "--params",
                    "params.yaml"], cwd=ROOT, check=True)


@step("mtf", "data")
def s_mtf(ctx):
    subprocess.run([sys.executable, str(SRC / "mtf_checks.py")], cwd=ROOT, check=True)


# --------------------------------------------------------------------- phase 1
@step("sweep", "phase1")
def s_sweep(ctx):
    from run_scenarios import run, substitution_frontier
    S, F = [], []
    for site in ctx.sites:
        t = time.time()
        df = run(ctx.cfg(site), ctx.resource(site), ctx.n, ctx.conn,
                 ctx.csv(f"scenarios_{site}.csv"), seed=ctx.seed, verbose=False)
        df.insert(0, "site", site)
        S.append(df)
        f = substitution_frontier(df)
        F.append(f)
        print(f"  sweep {site}: {len(df)} scenarios in {time.time()-t:.0f}s")
    pd.concat(S).to_csv(ctx.csv("scenarios_both.csv"), index=False, float_format="%.10g")
    pd.concat(F).to_csv(ctx.csv("frontier_both.csv"), index=False, float_format="%.10g")


@step("bands", "phase1")
def s_bands(ctx):
    from bands import blended_rate_table
    blended_rate_table(ctx.sites, ctx.n, ctx.seed).to_csv(
        ctx.csv("tariff_band_recomputed.csv"), index=False, float_format="%.10g")


@step("validation", "phase1")
def s_validation(ctx):
    from validate_cooking import validation_summary
    validation_summary(ctx.n).to_csv(ctx.csv("cooking_validation_summary.csv"),
                                     index=False, float_format="%.10g")


@step("viability", "phase1")
def s_viability(ctx):
    from viability import discount_sweep, viability
    S = ctx.read("scenarios_both.csv")
    res = {s: ctx.resource(s) for s in ctx.sites}
    viability(S, res, ctx.n, ctx.conn, ctx.seed).to_csv(
        ctx.csv("viability.csv"), index=False, float_format="%.10g")
    discount_sweep(S, res, ctx.n, ctx.conn, ctx.seed).to_csv(
        ctx.csv("discount_sweep.csv"), index=False, float_format="%.10g")


@step("tables", "phase1")
def s_tables(ctx):
    from manuscript_tables import build_all, write
    tables, numbers = build_all(ctx.results)
    write(tables, numbers, ctx.results / "tables")
    print(f"  tables -> {ctx.results / 'tables'}")


# --------------------------------------------------------------------- phase 2
def _headline(ctx, site, penetration=None):
    """(cfg, builder, resource, sizing) for the headline scenario."""
    from run_scenarios import make_load_builder
    from viability import headline_sizing
    cfg = ctx.cfg(site)
    sizing, pen = headline_sizing(ctx.read("scenarios_both.csv"), site, ctx.n,
                                  ctx.conn, penetration)
    return cfg, make_load_builder(cfg, ctx.n, pen, 0.0, ctx.seed), ctx.resource(site), sizing


def _skw(ctx, cfg):
    return {"pv_range": tuple(cfg["sizing"]["pv_range"]),
            "batt_range": tuple(cfg["sizing"]["battery_range"])}


@step("expansion", "phase2")
def s_expansion(ctx):
    import expansion
    out = []
    for site in ctx.sites:
        cfg, b, res, _ = _headline(ctx, site)
        df = expansion.run(cfg, b, res, ctx.conn, sizing_kw=_skw(ctx, cfg))
        df.insert(0, "site", site)
        out.append(df)
    pd.concat(out).to_csv(ctx.csv("expansion.csv"), index=False, float_format="%.10g")


@step("sizing_check", "phase2")
def s_sizing_check(ctx):
    import sizing_check
    from run_scenarios import make_load_builder
    specs = [("rwanda", 1.0, 0.0, "flat"), ("kenya", 0.5, 0.5, "tou")]
    rows, grids = [], []
    for site, pen, phi, mode in specs:
        cfg = ctx.cfg(site)
        cfg["_tariff_mode"] = mode
        b = make_load_builder(cfg, ctx.n, pen, phi, ctx.seed)
        step_pv, step_b = (25.0, 100.0) if ctx.quick else (5.0, 20.0)
        pv, bt = sizing_check.default_grid(cfg, step_pv, step_b,
                                           pv=(20, 400), batt=(0, 1400))
        label = f"{site} pen={pen} phi={phi} {mode}"
        summ, grid = sizing_check.check(cfg, b, ctx.resource(site), ctx.conn, pv, bt,
                                        label, _skw(ctx, cfg))
        rows.append(summ)
        grids.append(grid.assign(scenario=label))
        print(f"  {label}: search {summ['search_lcoe']:.4f} vs grid "
              f"{summ['grid_lcoe']:.4f} ({summ['lcoe_gap_pct']:+.2f}%)")
    pd.DataFrame(rows).to_csv(ctx.csv("sizing_check.csv"), index=False, float_format="%.10g")
    pd.concat(grids).to_csv(ctx.csv("sizing_check_grid.csv"), index=False, float_format="%.6g")


@step("interannual", "phase2")
def s_interannual(ctx):
    import interannual
    summ, dist = [], []
    for site in ctx.sites:
        cfg, b, _, sizing = _headline(ctx, site)
        s, d = interannual.run(cfg, sizing, b, ctx.all_years(site), ctx.rep_year(site),
                               ctx.conn, _skw(ctx, cfg))
        summ.append({"site": site, **s})
        dist.append(d.assign(site=site))
    pd.DataFrame(summ).to_csv(ctx.csv("interannual_summary.csv"), index=False,
                              float_format="%.10g")
    pd.concat(dist).to_csv(ctx.csv("interannual_by_year.csv"), index=False,
                           float_format="%.10g")


@step("ensemble", "phase2")
def s_ensemble(ctx):
    import ensemble
    seeds = range(1, 4) if ctx.quick else range(1, 25)
    per, summ = [], []
    for site in ctx.sites:
        cfg = ctx.cfg(site)
        t = time.time()
        df = ensemble.run(cfg, ctx.resource(site), ctx.n, ctx.conn, seeds,
                          sizing_kw=_skw(ctx, cfg))
        per.append(df.assign(site=site))
        summ.append(ensemble.summarise(df).assign(site=site))
        print(f"  ensemble {site}: {len(df)} seeds in {time.time()-t:.0f}s")
    pd.concat(per).to_csv(ctx.csv("ensemble_seeds.csv"), index=False, float_format="%.10g")
    pd.concat(summ).to_csv(ctx.csv("ensemble_summary.csv"), index=False,
                           float_format="%.10g")


@step("tou_sweep", "phase2")
def s_tou_sweep(ctx):
    import tou_sweep
    sweeps, be = [], []
    for site in ctx.sites:
        cfg = ctx.cfg(site)
        for response in ("step", "elastic"):
            df, _ = tou_sweep.sweep(cfg, ctx.resource(site), ctx.n, ctx.conn,
                                    ctx.seed, response=response,
                                    sizing_kw=_skw(ctx, cfg))
            sweeps.append(df.assign(site=site))
            if response == "step":
                be.append(tou_sweep.break_even_discount(df).assign(
                    site=site, step_function=tou_sweep.is_step_function(df)))
    pd.concat(sweeps).to_csv(ctx.csv("tou_sweep.csv"), index=False, float_format="%.10g")
    pd.concat(be).to_csv(ctx.csv("tou_break_even.csv"), index=False, float_format="%.10g")


@step("esmap", "phase2")
def s_esmap(ctx):
    import esmap
    wf, comp = [], []
    for site in ctx.sites:
        cfg, b, res, sizing = _headline(ctx, site)
        wf.append(esmap.waterfall(cfg, b, res, ctx.conn, _skw(ctx, cfg)).assign(site=site))
        comp.append({"site": site, **esmap.lcoe_components(cfg, sizing, b, res)})
    pd.concat(wf).to_csv(ctx.csv("esmap_waterfall.csv"), index=False, float_format="%.10g")
    pd.DataFrame(comp).to_csv(ctx.csv("lcoe_components.csv"), index=False,
                              float_format="%.10g")


# --------------------------------------------------------------------- phase 3
@step("operating_subsidy", "phase3")
def s_opsub(ctx):
    import operating_subsidy
    rows = []
    for site in ctx.sites:
        cfg, b, res, sizing = _headline(ctx, site)
        rows.append({"site": site, **operating_subsidy.cost(cfg, sizing, b, res, ctx.n)})
    pd.DataFrame(rows).to_csv(ctx.csv("operating_subsidy.csv"), index=False,
                              float_format="%.10g")


@step("peaks", "phase3")
def s_peaks(ctx):
    """Curtailment and the peak effect of shifting, from the sweep outputs."""
    F = ctx.read("frontier_both.csv")
    F = F[F.discount == F.discount.max()]
    cols = ["site", "penetration", "phi", "discount", "battery_flat", "battery_kwh",
            "avoided_battery_kwh", "peak_cooking_kw_flat", "peak_cooking_kw_year1",
            "peak_load_kw_year1", "peak_load_kw_final_year", "curtailed_fraction"]
    out = F[cols].rename(columns={"peak_cooking_kw_year1": "peak_cooking_kw_tou",
                                  "curtailed_fraction": "curtailed_fraction_tou"})
    S = ctx.read("scenarios_both.csv")
    flat = S[S.tariff == "flat"].groupby(["site", "penetration"]).agg(
        curtailed_fraction_flat=("curtailed_fraction", "first"),
        peak_load_kw_year1_flat=("peak_load_kw_year1", "first")).reset_index()
    out = out.merge(flat, on=["site", "penetration"], how="left")
    out["cooking_peak_change_pct"] = 100 * (out.peak_cooking_kw_tou
                                            / out.peak_cooking_kw_flat - 1)
    out["system_peak_change_pct"] = 100 * (out.peak_load_kw_year1
                                           / out.peak_load_kw_year1_flat - 1)
    out.to_csv(ctx.csv("peak_and_curtailment.csv"), index=False, float_format="%.10g")
    S.groupby(["site", "penetration", "tariff", "discount", "phi"]).curtailed_fraction.first() \
        .reset_index().to_csv(ctx.csv("curtailment.csv"), index=False, float_format="%.10g")


@step("household_bands", "phase3")
def s_household_bands(ctx):
    import household_bands as H
    rows, pen = [], []
    for site in ctx.sites:
        cfg = ctx.cfg(site)
        for p in (0.0, 1.0):
            rows.append(H.check(cfg, ctx.n, p, 0.0, ctx.seed).assign(site=site))
        for y in (1, 20):
            pen.append({"site": site, **H.adoption_penalty_distribution(cfg, ctx.n, ctx.seed, y)})
    pd.concat(rows).to_csv(ctx.csv("household_bands.csv"), index=False, float_format="%.10g")
    pd.DataFrame(pen).to_csv(ctx.csv("adoption_penalty_households.csv"), index=False,
                             float_format="%.10g")


@step("ringiti", "phase3")
def s_ringiti(ctx):
    import ringiti
    cfg = ctx.cfg("kenya")
    ringiti.run(cfg, ctx.resource("kenya"), ctx.seed, sizing_kw=_skw(ctx, cfg)).to_csv(
        ctx.csv("ringiti_benchmark.csv"), index=False, float_format="%.10g")


@step("household_cost", "phase3")
def s_household_cost(ctx):
    import household_cost
    B = ctx.read("tariff_band_recomputed.csv")
    rows = []
    for site in ctx.sites:
        r = B[(B.site == site) & (B.year == 1)].iloc[0]
        df = household_cost.compare(ctx.cfg(site), r.kwh_no_ecooking,
                                    r.kwh_full_ecooking - r.kwh_no_ecooking)
        rows.append(df.assign(site=site))
    pd.concat(rows).to_csv(ctx.csv("household_cost.csv"), index=False, float_format="%.10g")


# --------------------------------------------------------------------- phase 4
@step("final_tables", "phase4")
def s_final_tables(ctx):
    """Tables again, now that phases 2-3 exist: table 7 (operating subsidy)
    and the ensemble numbers in headline_numbers.csv need their outputs, and
    the phase 1 `tables` step runs before them."""
    s_tables(ctx)


@step("figures", "phase4")
def s_figures(ctx):
    import figures
    print("  figures ->", figures.build(ctx.results))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="a step name, a phase name, or 'all'")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--results", default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="reduced sweep for CI smoke runs")
    ap.add_argument("--resume", action="store_true",
                    help="skip steps already finished (see <results>/.steps_done)")
    args = ap.parse_args()
    ctx = Ctx(args)
    if args.synthetic:
        print("SYNTHETIC RESOURCE - smoke run only, results are not quotable")

    if args.target in STEPS:
        names = [args.target]
    elif args.target == "all":
        names = [n for n, (g, _) in STEPS.items() if g != "data"]
    else:
        names = [n for n, (g, _) in STEPS.items() if g == args.target]
    if not names:
        ap.error(f"unknown target {args.target!r}; steps: {', '.join(STEPS)}")
    done_file = ctx.results / ".steps_done"
    done = set(done_file.read_text().split()) if done_file.exists() else set()
    for n in names:
        if args.resume and n in done:
            print(f"[{n}] already done, skipped (--resume)")
            continue
        t = time.time()
        print(f"[{n}]", flush=True)
        STEPS[n][1](ctx)
        # recorded only after the step has written all its outputs
        with open(done_file, "a") as f:
            f.write(n + "\n")
        print(f"[{n}] done in {time.time()-t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
