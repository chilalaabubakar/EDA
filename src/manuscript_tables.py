"""Generate every manuscript table, and every headline in-text number, from
the results CSVs - in the manuscript's own formatting.

    python src/manuscript_tables.py --results results --out results/tables

The point is that no number reaches the paper by hand. tests/
test_manuscript_numbers.py compares these against the .docx cell by cell,
and against the claims listed in manuscript/claims.yaml.

Main-text tables (a draft may use a subset, in its own order: see `tables:`
in claims.yaml):
    1 tariff schedules            2 calibration targets and independent checks
    3 design and levelised cost   4 price paid with and without cooking
    5 loss and subsidy by share cooking (needs burden.csv)
    6 tariff scenarios (needs tariff_scenarios.csv)
Supplementary tables (`supplementary()`), written as tableS*.csv:
    S2 bridge from the first submission   S3 input sensitivity
    S4 structural alternatives            S5 subsidy with grants; break-even
    tariff by discount rate               S6 daytime discount by share moved
    S7 subsidy per tonne of CO2
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
        ["Lifeline", f"{fmt(r[0])} (0–{rb[0]} kWh)", f"{k[0]:.2f} (≤{kb[0]} kWh)"],
        ["Middle", f"{fmt(r[1])} ({rb[0]}–{rb[1]} kWh)", f"{k[1]:.2f} ({kb[0]+1}–{kb[1]} kWh)"],
        ["Upper", f"{fmt(r[2])} (>{rb[1]} kWh)", f"{k[2]:.2f} (>{kb[1]} kWh)"],
        ["Structure", "Telescopic" if rw["telescopic"] else "Non-telescopic",
         "Telescopic" if ke["telescopic"] else "Non-telescopic"],
    ], columns=["Band", "Rwanda (RWF/kWh)", "Kenya (KES/kWh)"])


def table2(validation, ringiti=None, bands=None):
    """Calibration targets, inputs and independent checks, labelled as such.

    The diversity factor is a calibration target (the spread of meal start
    times was tuned to it) and the peak hour is an input (supper is centred
    on 20:00), so neither validates the model. The independent checks are the
    daily cooking energy, Kenyan appliance use against utility billing data
    and the solar capacity of the plant installed on Ringiti.
    """
    v = validation.mean(numeric_only=True)
    rows = [
        ["Diversity factor of cooking", f"{v.df_mecs:.2f}", "9.75 (Kenya)",
         "Calibration target"],
        ["Hour of the cooking peak", f"{int(round(v.peak_hour)):02d}:00", "19:00–21:00",
         "Input"],
        ["Peak cooking load per household", f"{v.peak_w_per_hh:.0f} W (1 kW cooker)",
         "205 W (2 kW stove)", "Follows from the diversity factor"],
        ["Daily cooking energy per household", f"{v.daily_kwh_per_hh:.2f} kWh",
         "1.30 kWh", "Independent check"],
    ]
    if bands is not None:
        b = bands[(bands.site == "kenya") & (bands.basis == "simulated")].sort_values("year")
        rows.append(["Appliance use per household, Kenya",
                     f"{b.iloc[0].kwh_no_ecooking:.0f} kWh/month", "18 kWh/month",
                     "Independent check"])
    if ringiti is not None:
        m = ringiti[ringiti.basis.str.startswith("model")].iloc[0]
        i = ringiti[ringiti.basis.str.startswith("installed")].iloc[0]
        rows.append(["Solar capacity per customer without cooking, Ringiti",
                     f"{m.w_per_connection:.0f} W", f"{i.w_per_connection:.0f} W installed",
                     "Independent check"])
    return pd.DataFrame(rows, columns=["Quantity", "Model", "Measured", "Status"])


def _design(r):
    """'135 → 150 kW / 340 → 380 kWh': first stage → after the year-10 expansion."""
    if "pv_kw_stage2" in r and pd.notna(r.pv_kw_stage2):
        return (f"{r.pv_kw:.0f} → {r.pv_kw_stage2:.0f} kW / "
                f"{r.battery_kwh:.0f} → {r.battery_kwh_stage2:.0f} kWh")
    return f"{r.pv_kw:.0f} kW / {r.battery_kwh:.0f} kWh"


def table3(S):
    flat = S[(S.tariff == "flat") & S.feasible]
    rows = []
    for pen in sorted(flat.penetration.unique()):
        row = [pct(100 * pen)]
        for site in SITES:
            r = flat[(flat.site == site) & (flat.penetration == pen)].iloc[0]
            row += [_design(r), usd(r.lcoe, 2)]
        rows.append(row)
    return pd.DataFrame(rows, columns=["Households cooking", "Rwanda solar / battery",
                                       "Rwanda LCOE", "Kenya solar / battery",
                                       "Kenya LCOE"])


def _frontier_rows(F, discount=None):
    top = F.penetration.max()
    d = F.discount.max() if discount is None else discount
    return F[(F.penetration == top) & (F.discount == d)]


def table4(B):
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


def musd(x, dp=2):
    return f"−{abs(x) / 1e6:.{dp}f}" if x < 0 else f"{x / 1e6:.{dp}f}"


def table5(burden):
    """Operator's result and operating subsidy by share of households cooking."""
    rows = []
    for pen in sorted(burden.penetration.unique()):
        row = [pct(100 * pen)]
        for site in SITES:
            r = burden[(burden.site == site) & (burden.penetration == pen)].iloc[0]
            inc = r.incremental_usd_per_cooking_hh_year
            row += [musd(r.npv), f"{r.opsub_usd_per_conn_year:,.0f}",
                    "–" if inc != inc else f"{inc:,.0f}"]
        rows.append(row)
    cols = ["Households cooking"]
    for site in SITES:
        cols += [f"{TITLE[site]} NPV, US$ million", f"{TITLE[site]} subsidy, US$/connection/yr",
                 f"{TITLE[site]} extra per cooking household, US$/yr"]
    return pd.DataFrame(rows, columns=cols)


TARIFF_LABEL = {"national tariff": "National tariff, base charges (base scenario)",
                "national tariff, all charges (US$0.20/kWh)":
                    "National tariff, all charges (US$0.20/kWh)",
                "site tariff, Oloika (KES 40/kWh)": "Site tariff, KES 40/kWh (Oloika)",
                "site tariff, AMDA private model": "Site tariff, US$0.56/kWh (AMDA model)",
                "break-even tariff": "Break-even tariff"}
TARIFF_ORDER = list(TARIFF_LABEL)


def table6(T):
    """Full adoption under each tariff: price, the cooking household's monthly
    bill, the subsidy still needed and what each cooking household adds to it
    (negative: cooking lowers the subsidy)."""
    rows = []
    for name in [n for n in TARIFF_ORDER if n in set(T.tariff)]:
        row = [TARIFF_LABEL.get(name, name)]
        for site in SITES:
            r = T[(T.site == site) & (T.tariff == name)]
            if r.empty:
                row += ["–"] * 4
                continue
            r = r.iloc[0]
            inc = r.incremental_usd_per_cooking_hh_year
            row += [usd(r.price_per_kwh, 2), usd(r.bill_month_cooking, 2),
                    f"{r.opsub_usd_per_conn_year:,.0f}",
                    f"−{abs(inc):,.0f}" if round(inc) < 0 else f"{inc:,.0f}"]
        rows.append(row)
    cols = ["Tariff"]
    for site in SITES:
        cols += [f"{TITLE[site]} price, US$/kWh", f"{TITLE[site]} bill, US$/month",
                 f"{TITLE[site]} subsidy, US$/connection/yr",
                 f"{TITLE[site]} extra per cooking household, US$/yr"]
    return pd.DataFrame(rows, columns=cols)


# ------------------------------------------------------ supplementary tables
def table_grants(O, D, grants=((0, "None"), (50, "50%"), (95, "95%"))):
    """S5: operating subsidy with a capital grant, and the break-even tariff
    by discount rate."""
    O = O.set_index("site")
    a = []
    for g, label in grants:
        row = [label]
        for site in SITES:
            r = O.loc[site]
            row += [f"{r[f'opsub_grant{g}_usd_per_conn_year']:,.0f}",
                    f"{round(r[f'opsub_grant{g}_usd_per_village_year1'], -3):,.0f}"]
        a.append(row)
    a = pd.DataFrame(a, columns=["Capital grant", "Rwanda, US$/connection/yr",
                                 "Rwanda, US$/village/yr", "Kenya, US$/connection/yr",
                                 "Kenya, US$/village/yr"])
    b = []
    for dr in sorted(D.discount_rate.unique()):
        row = [pct(100 * dr)]
        for site in SITES:
            r = D[(D.site == site) & (D.discount_rate == dr)].iloc[0]
            row += [usd(r.lcoe, 2), usd(r.cost_reflective_tariff, 2), mult(r.multiple_of_regulated)]
        b.append(row)
    b = pd.DataFrame(b, columns=["Discount rate", "Rwanda LCOE", "Rwanda break-even tariff",
                                 "Rwanda multiple", "Kenya LCOE", "Kenya break-even tariff",
                                 "Kenya multiple"])
    return a, b


def _pair_cols(df, label_col, labels=None):
    rows = []
    for key in df[label_col].drop_duplicates():
        g = df[df[label_col] == key]
        for _, lab in g[["label"]].drop_duplicates().iterrows() if "label" in g else [(0, None)]:
            h = g if lab is None else g[g.label.fillna("") == (lab.label if isinstance(lab.label, str) else "")]
            row = [key if lab is None or not isinstance(lab.label, str) or not lab.label
                   else f"{key}: {lab.label}"]
            for site in SITES:
                r = h[h.site == site].iloc[0]
                row += [usd(r.lcoe_zero, 2), usd(r.lcoe_full, 2), musd(r.npv_full),
                        f"{r.opsub_full:,.0f}", f"{r.incremental_usd_per_cooking_hh_year:,.0f}"]
            rows.append(row)
    cols = [labels or "Case"]
    for site in SITES:
        t = TITLE[site]
        cols += [f"{t} LCOE, no cooking", f"{t} LCOE, full cooking", f"{t} NPV, US$ million",
                 f"{t} subsidy, US$/connection/yr", f"{t} extra per cooking household"]
    return pd.DataFrame(rows, columns=cols)


def table_sensitivity(X):
    return _pair_cols(X, "parameter", "Input changed")


def table_structural(X):
    return _pair_cols(X, "case", "Design")


def table_bridge(X):
    return _pair_cols(X, "step", "Step (cumulative)")


def table_phi(E):
    """S6: daytime discount by share of supper cooking moved, mean of the seed
    ensemble with the 95% interval of the mean (sampling noise only)."""
    def cell(site, q, phi, dp=0, scale=1.0, sign=1.0):
        r = E[(E.site == site) & (E.quantity == f"{q}_phi{int(round(100 * phi)):02d}")].iloc[0]
        lo, hi = sorted((sign * scale * r.ci95_lo, sign * scale * r.ci95_hi))
        return (f"{sign * scale * r['mean']:.{dp}f} ({lo:.{dp}f} to {hi:.{dp}f})"
                .replace("-", "−"))
    phis = sorted({int(q[-2:]) / 100 for q in E.quantity if q.startswith("avoided_battery_pct_phi")})
    rows = []
    for phi in phis:
        row = [f"{phi:.1f}"]
        for site in SITES:
            row += [cell(site, "avoided_battery_pct", phi), cell(site, "tou_lcoe_change_pct", phi, 1, sign=-1.0),
                    cell(site, "break_even_discount", phi, 1, 100.0)]
        row += [cell(SITES[0], "peak_cooking_increase_pct", phi)]
        rows.append(row)
    cols = ["Share of supper cooking moved (φ)"]
    for site in SITES:
        t = TITLE[site]
        cols += [f"{t} battery saved, %", f"{t} LCOE fall, %", f"{t} break-even discount, US cents/kWh"]
    cols += ["Change in cooking peak, %"]
    return pd.DataFrame(rows, columns=cols)


def table_carbon(C):
    rows = []
    for basis, name in (("useful_energy", "Equal useful cooking energy"),
                        ("cdm_default", "CDM default, 0.5 t per person per year")):
        for f in sorted(C.fnrb.unique()):
            row = [name, pct(100 * f)]
            for site in SITES:
                r = C[(C.site == site) & (C.wood_basis == basis) & (C.fnrb == f)].iloc[0]
                row += [f"{r.wood_t_per_cooking_hh_year:.2f}", f"{r.tco2_per_cooking_hh_year:.2f}",
                        f"{r.usd_per_tco2:,.0f}"]
            rows.append(row)
    cols = ["Firewood displaced: basis", "Share non-renewable"]
    for site in SITES:
        t = TITLE[site]
        cols += [f"{t} wood, t/household/yr", f"{t} CO2 avoided, t/household/yr",
                 f"{t} extra subsidy, US$/t CO2"]
    return pd.DataFrame(rows, columns=cols)


def supplementary(results="results"):
    """{name: DataFrame} for the supplementary tables whose inputs exist."""
    R = Path(results)
    have = lambda f: (R / f).exists()
    out = {}
    if have("bridge.csv"):
        out["S2"] = table_bridge(pd.read_csv(R / "bridge.csv"))
    if have("sensitivity.csv"):
        out["S3"] = table_sensitivity(pd.read_csv(R / "sensitivity.csv"))
    if have("structural.csv"):
        out["S4"] = table_structural(pd.read_csv(R / "structural.csv"))
    if have("operating_subsidy.csv") and have("discount_sweep.csv"):
        a, b = table_grants(pd.read_csv(R / "operating_subsidy.csv"),
                            pd.read_csv(R / "discount_sweep.csv"))
        out["S5a"], out["S5b"] = a, b
    if have("ensemble_summary.csv"):
        out["S6"] = table_phi(pd.read_csv(R / "ensemble_summary.csv"))
    if have("carbon.csv"):
        out["S7"] = table_carbon(pd.read_csv(R / "carbon.csv"))
    return out


# ------------------------------------------------------------- in-text numbers
def headline_numbers(S, F, B, D, base_rate=0.12, discount=None):
    """Named quantities quoted in the text, from the phase 1 outputs."""
    out = {}
    flat = S[(S.tariff == "flat") & S.feasible]
    f = _frontier_rows(F, discount)
    for site in SITES:
        g = flat[flat.site == site].drop_duplicates("penetration").sort_values("penetration")
        lo, hi = g.iloc[0], g.iloc[-1]
        out[f"lcoe_zero_{site}"] = lo.lcoe
        out[f"lcoe_full_{site}"] = hi.lcoe
        if len(g) > 2:
            out[f"lcoe_half_{site}"] = g.iloc[1].lcoe
        out[f"lcoe_reduction_pct_{site}"] = 100 * (1 - hi.lcoe / lo.lcoe)
        for tag, r in (("zero", lo), ("full", hi)):
            out[f"curtailed_pct_{tag}_{site}"] = 100 * r.curtailed_fraction
            out[f"pv_w_per_connection_{tag}_{site}"] = 1000 * r.pv_kw / 300.0
        top = f[f.site == site].sort_values("phi").iloc[-1]
        col = ("avoided_battery_bought_pct" if "avoided_battery_bought_pct" in top
               else "avoided_battery_pct")
        out[f"avoided_storage_pct_{site}"] = top[col]
        out[f"tou_lcoe_reduction_pct_{site}"] = -top.lcoe_change_pct
        d = D[D.site == site].set_index("discount_rate")
        out[f"multiple_base_{site}"] = d.loc[base_rate, "multiple_of_regulated"]
        out[f"multiple_min_rate_{site}"] = d.iloc[0]["multiple_of_regulated"]
        out[f"multiple_max_rate_{site}"] = d.iloc[-1]["multiple_of_regulated"]
        out[f"breakeven_tariff_{site}"] = d.loc[base_rate, "cost_reflective_tariff"]
        b = B[(B.site == site) & (B.basis == "simulated")].sort_values("year")
        out[f"band_factor_year1_{site}"] = b.iloc[0].factor
        out[f"band_factor_final_{site}"] = b.iloc[-1].factor
        out[f"blended_pre_year1_{site}"] = b.iloc[0].rate_no_ecooking
        out[f"blended_post_year1_{site}"] = b.iloc[0].rate_full_ecooking
        out[f"kwh_month_pre_year1_{site}"] = b.iloc[0].kwh_no_ecooking
        out[f"kwh_month_post_year1_{site}"] = b.iloc[0].kwh_full_ecooking
        out[f"kwh_month_pre_final_{site}"] = b.iloc[-1].kwh_no_ecooking
        out[f"kwh_month_post_final_{site}"] = b.iloc[-1].kwh_full_ecooking
    for k in ("tou_lcoe_reduction_pct", "multiple_max_rate", "multiple_min_rate",
              "lcoe_reduction_pct", "avoided_storage_pct", "multiple_base", "lcoe_full",
              "breakeven_tariff"):
        vals = [out[f"{k}_{s}"] for s in SITES]
        out[f"{k}_min"], out[f"{k}_max"] = min(vals), max(vals)
    return out


SENS_SLUG = {"Capital cost": "capital", "Operating cost": "opex", "Discount rate": "rate",
             "Battery cost": "battery", "Appliance demand growth": "growth",
             "Energy per meal": "meal", "Bills collected": "collection",
             "Unserved demand allowed": "unserved", "All cost inputs together": "all"}
TARIFF_SLUG = {"national tariff": "national",
               "national tariff, all charges (US$0.20/kWh)": "allin",
               "site tariff, Oloika (KES 40/kWh)": "oloika",
               "site tariff, AMDA private model": "amda", "break-even tariff": "breakeven"}


def _struct_slug(case):
    c = case.lower()
    if c.startswith("base"):
        return "base"
    if c.startswith("single"):
        return "single"
    if c.startswith("anchor load and"):
        return "anchor_gen"
    if "anchor" in c:
        return "anchor"
    return "gen" + c.split("us$")[1].split()[0].replace(".", "")     # gen100, gen150, gen200


def phase_numbers(R):
    """Numbers from the later pipeline steps, when their outputs are present."""
    out = {}
    R = Path(R)
    have = lambda f: (R / f).exists()
    if have("ensemble_summary.csv"):
        e = pd.read_csv(R / "ensemble_summary.csv")
        out["ens_n_seeds"] = int(e.n_seeds.max())
        for _, r in e.iterrows():
            k = f"ens_{r.quantity}_{r.site}"
            out[k], out[k + "_lo"], out[k + "_hi"] = r["mean"], r.ci95_lo, r.ci95_hi
        # break-even discount in US cents; the share moved with the largest saving
        for site in SITES:
            g = e[(e.site == site) & e.quantity.str.startswith("break_even_discount_phi")]
            for _, r in g.iterrows():
                k = f"ens_break_even_cents_{r.quantity[-5:]}_{site}"
                out[k], out[k + "_lo"], out[k + "_hi"] = 100 * r["mean"], 100 * r.ci95_lo, 100 * r.ci95_hi
            out[f"ens_break_even_cents_max_{site}"] = 100 * g["mean"].max()
            out[f"ens_break_even_cents_min_{site}"] = 100 * g["mean"].min()
    if have("burden.csv"):
        b = pd.read_csv(R / "burden.csv")
        for _, r in b.iterrows():
            tag = f"{int(round(100 * r.penetration))}_{r.site}"
            out[f"burden_npv_musd_{tag}"] = r.npv / 1e6
            out[f"burden_opsub_{tag}"] = r.opsub_usd_per_conn_year
            out[f"burden_opsub_village_k_{tag}"] = r.opsub_usd_per_village_year / 1e3
            out[f"burden_lcoe_{tag}"] = r.lcoe
            if r.penetration > 0:
                out[f"burden_incremental_{tag}"] = r.incremental_usd_per_cooking_hh_year
                out[f"burden_incremental_per_kwh_{tag}"] = r.incremental_usd_per_cooking_kwh
                out[f"burden_cooking_cost_per_kwh_{tag}"] = r.incremental_cost_per_cooking_kwh
                out[f"burden_cooking_kwh_{tag}"] = r.cooking_kwh_per_cooking_hh_year
        for site in SITES:
            g = b[b.site == site].sort_values("penetration")
            out[f"burden_loss_increase_pct_{site}"] = 100 * (g.iloc[-1].npv / g.iloc[0].npv - 1)
            out[f"burden_opsub_increase_pct_{site}"] = 100 * (
                g.iloc[-1].opsub_usd_per_conn_year / g.iloc[0].opsub_usd_per_conn_year - 1)
    if have("tariff_scenarios.csv"):
        t = pd.read_csv(R / "tariff_scenarios.csv")
        for _, r in t.iterrows():
            tag = f"{TARIFF_SLUG.get(r.tariff, r.tariff)}_{r.site}"
            out[f"ts_price_{tag}"] = r.price_per_kwh
            out[f"ts_bill_cooking_{tag}"] = r.bill_month_cooking
            out[f"ts_bill_no_cooking_{tag}"] = r.bill_month_no_cooking
            out[f"ts_cooking_bill_{tag}"] = r.cooking_bill_month
            out[f"ts_npv_musd_{tag}"] = r.npv / 1e6
            out[f"ts_opsub_{tag}"] = r.opsub_usd_per_conn_year
            out[f"ts_incremental_{tag}"] = r.incremental_usd_per_cooking_hh_year
            out[f"ts_bill_multiple_{tag}"] = r.bill_multiple_of_national
    if have("carbon.csv"):
        c = pd.read_csv(R / "carbon.csv")
        for (site, basis), g in c.groupby(["site", "wood_basis"]):
            out[f"carbon_usd_min_{basis}_{site}"] = g.usd_per_tco2.min()
            out[f"carbon_usd_max_{basis}_{site}"] = g.usd_per_tco2.max()
            out[f"carbon_wood_t_{basis}_{site}"] = g.wood_t_per_cooking_hh_year.iloc[0]
        out["carbon_usd_min_all"] = c.usd_per_tco2.min()
        out["carbon_usd_max_all"] = c.usd_per_tco2.max()
    if have("sensitivity.csv"):
        x = pd.read_csv(R / "sensitivity.csv")
        for _, r in x[x.side != "base"].iterrows():
            tag = f"{SENS_SLUG[r.parameter]}_{r.side}_{r.site}"
            out[f"sens_lcoe_full_{tag}"] = r.lcoe_full
            out[f"sens_lcoe_zero_{tag}"] = r.lcoe_zero
            out[f"sens_incremental_{tag}"] = r.incremental_usd_per_cooking_hh_year
            out[f"sens_opsub_full_{tag}"] = r.opsub_full
            out[f"sens_lcoe_fall_pct_{tag}"] = r.lcoe_fall_pct
            out[f"sens_incremental_change_pct_{tag}"] = r.incremental_usd_per_cooking_hh_year_change_pct
            out[f"sens_lcoe_full_change_pct_{tag}"] = r.lcoe_full_change_pct
        for site in SITES:
            g = x[(x.site == site) & (x.parameter != "All cost inputs together")]
            out[f"sens_lcoe_fall_pct_min_{site}"] = g.lcoe_fall_pct.min()
            out[f"sens_lcoe_fall_pct_max_{site}"] = g.lcoe_fall_pct.max()
            out[f"sens_incremental_min_{site}"] = g.incremental_usd_per_cooking_hh_year.min()
            out[f"sens_incremental_max_{site}"] = g.incremental_usd_per_cooking_hh_year.max()
    if have("structural.csv"):
        x = pd.read_csv(R / "structural.csv")
        for _, r in x.iterrows():
            tag = f"{_struct_slug(r.case)}_{r.site}"
            out[f"struct_lcoe_zero_{tag}"] = r.lcoe_zero
            out[f"struct_lcoe_full_{tag}"] = r.lcoe_full
            out[f"struct_incremental_{tag}"] = r.incremental_usd_per_cooking_hh_year
            out[f"struct_npv_musd_full_{tag}"] = r.npv_full / 1e6
            out[f"struct_generator_pct_full_{tag}"] = 100 * r.generator_share_full
        for site in SITES:
            g = x[x.site == site]
            base = g[g.case.str.startswith("Base")].iloc[0]
            out[f"struct_incremental_min_{site}"] = g.incremental_usd_per_cooking_hh_year.min()
            out[f"struct_incremental_max_{site}"] = g.incremental_usd_per_cooking_hh_year.max()
            for slug in ("single", "anchor", "gen150"):
                r = g[g.case.map(_struct_slug) == slug].iloc[0]
                out[f"struct_lcoe_full_change_pct_{slug}_{site}"] = 100 * (r.lcoe_full / base.lcoe_full - 1)
    if have("bridge.csv"):
        x = pd.read_csv(R / "bridge.csv")
        for _, r in x.iterrows():
            tag = f"{r.step.split()[0]}_{r.site}"
            out[f"bridge_lcoe_zero_{tag}"] = r.lcoe_zero
            out[f"bridge_lcoe_full_{tag}"] = r.lcoe_full
            out[f"bridge_npv_musd_full_{tag}"] = r.npv_full / 1e6
            out[f"bridge_opsub_full_{tag}"] = r.opsub_full
            out[f"bridge_incremental_{tag}"] = r.incremental_usd_per_cooking_hh_year
    if have("kenya_ownership_check.csv"):
        k = pd.read_csv(R / "kenya_ownership_check.csv").set_index("quantity")
        for q, r in k.iterrows():
            out[f"kenya_{q}_m3"], out[f"kenya_{q}_core"] = r["m3"], r["core"]
            if "core_2022" in r:
                out[f"kenya_{q}_core_2022"] = r["core_2022"]
    if have("operating_subsidy.csv"):
        o = pd.read_csv(R / "operating_subsidy.csv").set_index("site")
        for site in SITES:
            if site in o.index:
                r = o.loc[site]
                out[f"opsub_{site}"] = r.opsub_grant0_usd_per_conn_year
                for g in (0, 50, 95):
                    out[f"opsub_grant{g}_{site}"] = r[f"opsub_grant{g}_usd_per_conn_year"]
                out[f"opsub_village_k_{site}"] = r.opsub_grant0_usd_per_village_year1 / 1e3
                out[f"opsub_npv_musd_{site}"] = r.opsub_grant0_npv_usd / 1e6
                out[f"opsub_grant95_cut_pct_{site}"] = 100 * (
                    1 - r.opsub_grant95_usd_per_conn_year / r.opsub_grant0_usd_per_conn_year)
                out[f"gross_capex_musd_{site}"] = r.gross_capex / 1e6
    if have("interannual_summary.csv"):
        for _, r in pd.read_csv(R / "interannual_summary.csv").iterrows():
            for q, v in r.items():
                if q != "site":
                    out[f"weather_{q}_{r.site}"] = v
            out[f"weather_lcoe_spread_pct_{r.site}"] = 100 * (r.lcoe_p95 - r.lcoe_p05) / r.lcoe_median
    if have("site_ownership_check.csv"):
        for _, r in pd.read_csv(R / "site_ownership_check.csv").iterrows():
            out[f"site_{r.quantity}_national_{r.site}"] = r.national
            out[f"site_{r.quantity}_island_{r.site}"] = r.island
            out[f"site_{r.quantity}_change_pct_{r.site}"] = r.change_pct
    if have("expansion.csv"):
        x = pd.read_csv(R / "expansion.csv")
        for site in SITES:
            g = x[x.site == site].set_index("design")
            out[f"single_stage_lcoe_change_pct_{site}"] = 100 * (
                g.loc["single, year 20", "lcoe"] / g.loc["staged, years 1-10 / 11-20", "lcoe"] - 1)
    if have("cooking_daytime_share.csv"):
        for _, r in pd.read_csv(R / "cooking_daytime_share.csv").iterrows():
            out[f"daytime_share_pct_phi{int(round(10 * r.phi))}_{r.site}"] = \
                100 * r.daytime_share_of_cooking_energy
    if have("cooking_validation_summary.csv"):
        v = pd.read_csv(R / "cooking_validation_summary.csv").mean(numeric_only=True)
        out["val_daily_kwh"] = v.daily_kwh_per_hh
        if "kwh_per_meal_simulated" in v:
            out["val_kwh_per_meal"] = v.kwh_per_meal_simulated
        out["val_daily_gap_pct"] = 100 * (1 - v.daily_kwh_per_hh / 1.30)
    if have("ringiti_benchmark.csv"):
        g = pd.read_csv(R / "ringiti_benchmark.csv")
        inst = g[g.basis.str.startswith("installed")]
        if len(inst) and "max_solar_kwh_per_connection_year" in g:
            i = inst.iloc[0]
            out["ringiti_w_per_customer"] = i.w_per_connection
            out["ringiti_max_kwh_per_customer"] = i.max_solar_kwh_per_connection_year
            for _, r in g[g.basis.str.startswith("model")].iterrows():
                p = int(r.basis.split()[-1].rstrip("%"))
                out[f"ringiti_pv_multiple_{p}"] = r.pv_multiple_of_installed
                out[f"ringiti_model_w_{p}"] = r.w_per_connection
                out[f"ringiti_kwh_year1_{p}"] = r.kwh_per_connection_year1
            out["ringiti_model_excess_pct_0"] = 100 * (out["ringiti_pv_multiple_0"] - 1)
    if have("household_cost.csv"):
        h = pd.read_csv(R / "household_cost.csv")
        for site in SITES:
            r = h[(h.site == site) & (h.option == "electric (EPC)")]
            if len(r):
                out[f"hh_electricity_usd_year_{site}"] = r.iloc[0].of_which_electricity
                out[f"hh_cooker_usd_year_{site}"] = r.iloc[0].of_which_appliance
    if have("cost_vs_price.csv"):
        cp = pd.read_csv(R / "cost_vs_price.csv")
        for site, g in cp.groupby("site"):
            g = g.set_index("penetration").sort_index()
            for pen, r in g.iterrows():
                p = int(round(100 * pen))
                for q in ("kwh_per_connection_year1", "gross_capex", "battery_kwh",
                          "per_connection_fixed", "supply", "avg_price_paid",
                          "lcoe_over_price", "gap_per_kwh", "npv"):
                    out[f"cvp_{q}_{p}_{site}"] = r[q]
                out[f"cvp_gross_capex_musd_{p}_{site}"] = r.gross_capex / 1e6
                out[f"cvp_npv_musd_{p}_{site}"] = r.npv / 1e6
                if "capital_pv" in r:
                    out[f"cvp_capital_pv_musd_{p}_{site}"] = r.capital_pv / 1e6
                    out[f"cvp_curtailed_pct_{p}_{site}"] = 100 * r.curtailed_fraction
            lo, hi = g.iloc[0], g.iloc[-1]          # no cooking, full cooking
            out[f"cvp_energy_ratio_{site}"] = (hi.kwh_per_connection_year1
                                               / lo.kwh_per_connection_year1)
            out[f"cvp_capex_ratio_{site}"] = hi.gross_capex / lo.gross_capex
            if "capital_pv" in g:
                out[f"cvp_capital_ratio_{site}"] = hi.capital_pv / lo.capital_pv
                out[f"cvp_battery_ratio_{site}"] = hi.battery_kwh_bought / lo.battery_kwh_bought
            else:
                out[f"cvp_battery_ratio_{site}"] = hi.battery_kwh / lo.battery_kwh
            out[f"cvp_fixed_share_of_fall_pct_{site}"] = (
                100 * (lo.per_connection_fixed - hi.per_connection_fixed) / (lo.lcoe - hi.lcoe))
            out[f"cvp_cost_factor_{site}"] = lo.lcoe / hi.lcoe
            out[f"cvp_price_factor_{site}"] = hi.avg_price_paid / lo.avg_price_paid
    if have("bill_example.csv"):
        for _, r in pd.read_csv(R / "bill_example.csv").iterrows():
            for q, v in r.items():
                if q not in ("site", "currency"):
                    out[f"bill_{q}_{r.site}"] = v
    return out


def render_abstract(numbers, template=Path(__file__).resolve().parents[1]
                    / "manuscript" / "abstract_template.md"):
    import re as _re
    text = _re.sub(r"<!--.*?-->", "", Path(template).read_text(), flags=_re.S).strip()
    return text.format_map(numbers)


def build_all(results="results", validation=None):
    R = Path(results)
    have = lambda f: (R / f).exists()
    S = pd.read_csv(R / "scenarios_both.csv")
    F = pd.read_csv(R / "frontier_both.csv")
    B = pd.read_csv(R / "tariff_band_recomputed.csv")
    D = pd.read_csv(R / "discount_sweep.csv")
    if validation is None:
        validation = pd.read_csv(R / "cooking_validation_summary.csv")
    ringiti = pd.read_csv(R / "ringiti_benchmark.csv") if have("ringiti_benchmark.csv") else None
    tables = {1: table1(), 2: table2(validation, ringiti, B), 3: table3(S), 4: table4(B)}
    if have("burden.csv"):
        tables[5] = table5(pd.read_csv(R / "burden.csv"))
    if have("tariff_scenarios.csv"):
        tables[6] = table6(pd.read_csv(R / "tariff_scenarios.csv"))
    return tables, {**headline_numbers(S, F, B, D), **phase_numbers(R)}


def to_markdown(df):
    cols = [str(c).strip() for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.values]
    return "\n".join(lines)


def write(tables, numbers, out, supp=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    md = []
    for n, t in tables.items():
        t.to_csv(out / f"table{n}.csv", index=False)
        md += [f"### Table {n}", "", to_markdown(t), ""]
    for name, t in (supp or {}).items():
        t.to_csv(out / f"table{name}.csv", index=False)
        md += [f"### Table {name}", "", to_markdown(t), ""]
    (out / "tables.md").write_text("\n".join(md))
    pd.Series(numbers).to_csv(out / "headline_numbers.csv", header=["value"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None)
    ap.add_argument("--abstract", action="store_true",
                    help="print the abstract rendered from the results")
    a = ap.parse_args()
    if a.abstract:
        print(render_abstract(build_all(a.results)[1]))
        return
    tables, numbers = build_all(a.results)
    write(tables, numbers, a.out or Path(a.results) / "tables", supplementary(a.results))
    for n, t in tables.items():
        print(f"\nTable {n}\n{t.to_string(index=False)}")
    print("\nHeadline numbers")
    for k, v in numbers.items():
        print(f"  {k:<44} {v:.4f}" if isinstance(v, (int, float)) else f"  {k:<44} {v}")


if __name__ == "__main__":
    main()
