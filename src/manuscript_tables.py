"""Generate every manuscript table, and every headline in-text number, from
the results CSVs - in the manuscript's own formatting.

    python src/manuscript_tables.py --results results --out results/tables

The point is that no number reaches the paper by hand. tests/
test_manuscript_numbers.py compares these against the .docx cell by cell,
and against the claims listed in manuscript/claims.yaml.

Docx table order (s3.6 .. s5.4):
    1 tariff schedules   2 cooking validation   3 LCOE by penetration
    4 storage displacement   5 blended tariff   6 cost-reflective tariff
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from final_cfg import KES_USD, RWF_USD, country_cfg

SITES = ("rwanda", "kenya")
TITLE = {"rwanda": "Rwanda", "kenya": "Kenya"}


def usd(x, dp=2):
    return "-" if x is None or x != x else f"${x:.{dp}f}"


def mult(x, dp=1):
    return "-" if x is None or x != x else f"{x:.{dp}f}×"


def pct(x, dp=0):
    return f"{x:.{dp}f}%"


# ---------------------------------------------------------------- tables
def table1():
    rw, ke = country_cfg("rwanda")["tariff"], country_cfg("kenya")["tariff"]
    r = [round(b[1] * RWF_USD, 2) for b in rw["bands"]]
    k = [round(b[1] * KES_USD, 2) for b in ke["bands"]]
    rb, kb = [b[0] for b in rw["bands"]], [b[0] for b in ke["bands"]]
    fmt = lambda v: f"{v:g}"
    return pd.DataFrame([
        ["Lifeline", f"{fmt(r[0])} (0–{rb[0]} kWh)", f"{fmt(k[0])} (<{kb[0]} kWh)"],
        ["Middle", f"{fmt(r[1])} ({rb[0]}–{rb[1]} kWh)", f"{fmt(k[1])} ({kb[0]+1}–{kb[1]} kWh)"],
        ["Upper", f"{fmt(r[2])} (>{rb[1]} kWh)", f"{fmt(k[2])} (>{kb[1]} kWh)"],
        ["Structure", "Telescopic" if rw["telescopic"] else "Non-telescopic",
         "Telescopic" if ke["telescopic"] else "Non-telescopic"],
    ], columns=["Band", "Rwanda (RWF/kWh)", "Kenya (KES/kWh)"])


def table2(validation):
    v = validation.mean(numeric_only=True)
    return pd.DataFrame([
        ["Diversity factor (average profile)", f"{v.df_mecs:.2f}",
         "Kenya 9.75, Tanzania 13.52, Ghana 13.00"],
        ["Peak hour", f"{int(round(v.peak_hour)):02d}:00", "Supper peak 19:00–21:00"],
        ["Peak load per household", f"{v.peak_w_per_hh:.0f} W (1 kW EPC)",
         "205 W equivalent (2 kW induction)"],
        ["Daily cooking energy", f"{v.daily_kwh_per_hh:.2f} kWh",
         "1.30 kWh (electricity-only households)"],
    ], columns=["Metric", "Model", "MECS measured"])


def table3(S):
    flat = S[(S.tariff == "flat") & S.feasible]
    rows = []
    for pen in sorted(flat.penetration.unique()):
        row = [pct(100 * pen)]
        for site in SITES:
            r = flat[(flat.site == site) & (flat.penetration == pen)].iloc[0]
            row += [f"{r.pv_kw:.0f} kW / {r.battery_kwh:.0f} kWh", usd(r.lcoe, 2)]
        rows.append(row)
    return pd.DataFrame(rows, columns=["Penetration", "Rwanda PV / storage",
                                       "Rwanda LCOE", "Kenya PV / storage",
                                       "Kenya LCOE"])


def _frontier_rows(F, discount=None):
    top = F.penetration.max()
    d = F.discount.max() if discount is None else discount
    return F[(F.penetration == top) & (F.discount == d)]


def table4(F, discount=None):
    f = _frontier_rows(F, discount)
    rows = []
    for phi in sorted(f.phi.unique()):
        row = [f"{phi:.1f}"]
        for site in SITES:
            r = f[(f.site == site) & (f.phi == phi)].iloc[0]
            av = r.avoided_battery_kwh
            row += [f"{r.battery_kwh:.0f} kWh",
                    "0" if av == 0 else f"{av:.0f} kWh ({r.avoided_battery_pct:.0f}%)",
                    usd(r.lcoe, 3)]
        rows.append(row)
    return pd.DataFrame(rows, columns=["φ", "Rwanda storage", "Avoided",
                                       "Rwanda LCOE", "Kenya storage", "Avoided ",
                                       "Kenya LCOE"])


def table5(B):
    """Restructured by project year (Phase 1). Each row: pre -> post blended
    rate and the factor, for each country."""
    rows = []
    for key, g in B.groupby(B.year.fillna(0), sort=True):
        label = ("Illustrative, 15 → 60 kWh" if key == 0
                 else f"Year {int(key)}, simulated")
        row = [label]
        for site in SITES:
            r = g[g.site == site].iloc[0]
            row += [f"{r.kwh_no_ecooking:.0f} → {r.kwh_full_ecooking:.0f} kWh",
                    f"{usd(r.rate_no_ecooking, 3)} → {usd(r.rate_full_ecooking, 3)}",
                    mult(r.factor)]
        rows.append(row)
    return pd.DataFrame(rows, columns=["Basis", "Rwanda kWh/month",
                                       "Rwanda blended rate", "Rwanda factor",
                                       "Kenya kWh/month", "Kenya blended rate",
                                       "Kenya factor"])


def table6(D):
    rows = []
    for dr in sorted(D.discount_rate.unique()):
        row = [pct(100 * dr)]
        for site in SITES:
            r = D[(D.site == site) & (D.discount_rate == dr)].iloc[0]
            row += [usd(r.cost_reflective_tariff, 3), mult(r.multiple_of_regulated)]
        rows.append(row)
    return pd.DataFrame(rows, columns=["Discount rate", "Rwanda cost-reflective",
                                       "Multiple", "Kenya cost-reflective",
                                       "Multiple "])


# ------------------------------------------------------------- in-text numbers
def headline_numbers(S, F, B, D, base_rate=0.12, discount=None):
    """Named quantities quoted in the abstract, s1 and s5-s7."""
    out = {}
    flat = S[(S.tariff == "flat") & S.feasible]
    f = _frontier_rows(F, discount)
    for site in SITES:
        g = flat[flat.site == site].sort_values("penetration")
        lo, hi = g.iloc[0], g.iloc[-1]
        out[f"lcoe_zero_{site}"] = lo.lcoe
        out[f"lcoe_full_{site}"] = hi.lcoe
        out[f"lcoe_reduction_pct_{site}"] = 100 * (1 - hi.lcoe / lo.lcoe)
        top = f[f.site == site].sort_values("phi").iloc[-1]
        out[f"avoided_storage_pct_{site}"] = top.avoided_battery_pct
        out[f"avoided_storage_kwh_{site}"] = top.avoided_battery_kwh
        out[f"tou_lcoe_reduction_pct_{site}"] = -top.lcoe_change_pct
        d = D[D.site == site].set_index("discount_rate")
        out[f"multiple_base_{site}"] = d.loc[base_rate, "multiple_of_regulated"]
        out[f"multiple_max_rate_{site}"] = d.iloc[-1]["multiple_of_regulated"]
        b = B[(B.site == site) & (B.basis == "simulated")].sort_values("year")
        out[f"band_factor_year1_{site}"] = b.iloc[0].factor
        out[f"band_factor_final_{site}"] = b.iloc[-1].factor
        out[f"blended_pre_year1_{site}"] = b.iloc[0].rate_no_ecooking
        out[f"blended_post_year1_{site}"] = b.iloc[0].rate_full_ecooking
    for k in ("tou_lcoe_reduction_pct", "multiple_max_rate", "lcoe_reduction_pct",
              "avoided_storage_pct", "multiple_base"):
        vals = [out[f"{k}_{s}"] for s in SITES]
        out[f"{k}_min"], out[f"{k}_max"] = min(vals), max(vals)
    return out


def build_all(results="results", validation=None):
    R = Path(results)
    S = pd.read_csv(R / "scenarios_both.csv")
    F = pd.read_csv(R / "frontier_both.csv")
    B = pd.read_csv(R / "tariff_band_recomputed.csv")
    D = pd.read_csv(R / "discount_sweep.csv")
    if validation is None:
        validation = pd.read_csv(R / "cooking_validation_summary.csv")
    tables = {1: table1(), 2: table2(validation), 3: table3(S), 4: table4(F),
              5: table5(B), 6: table6(D)}
    return tables, headline_numbers(S, F, B, D)


def to_markdown(df):
    cols = [str(c).strip() for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.values]
    return "\n".join(lines)


def write(tables, numbers, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    md = []
    for n, t in tables.items():
        t.to_csv(out / f"table{n}.csv", index=False)
        md += [f"### Table {n}", "", to_markdown(t), ""]
    (out / "tables.md").write_text("\n".join(md))
    pd.Series(numbers).to_csv(out / "headline_numbers.csv", header=["value"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    tables, numbers = build_all(a.results)
    write(tables, numbers, a.out or Path(a.results) / "tables")
    for n, t in tables.items():
        print(f"\nTable {n}\n{t.to_string(index=False)}")
    print("\nHeadline numbers")
    for k, v in numbers.items():
        print(f"  {k:<32} {v:.4f}")


if __name__ == "__main__":
    main()
