"""One entry point for every result in the paper.

    python src/pipeline.py resource            # NASA POWER -> data/processed (network)
    python src/pipeline.py mtf                 # MTF microdata -> data/processed (needs data/raw)
    python src/pipeline.py phase1              # sweep, frontier, bands, viability, tables
    python src/pipeline.py all                 # everything that does not need the network

    --synthetic   use the synthetic resource and write to results/synthetic/.
                  For smoke tests and CI only. Never quote these numbers.

Each step writes CSVs into the results directory; manuscript_tables.py turns
those into the manuscript tables, and tests/test_manuscript_numbers.py checks
the .docx against them.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

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
        from resource import load_site_resource, synthetic_years
        y = year or self.rep_year(site)
        if self.synthetic:
            return synthetic_years(site)[y]
        return load_site_resource(site, y)

    def all_years(self, site):
        from resource import resource_years, synthetic_years
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="a step name, a phase name, or 'all'")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--results", default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="reduced sweep for CI smoke runs")
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
    for n in names:
        t = time.time()
        print(f"[{n}]")
        STEPS[n][1](ctx)
        print(f"[{n}] done in {time.time()-t:.0f}s")


if __name__ == "__main__":
    main()
