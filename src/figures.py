"""All manuscript figures, from the results CSVs (Phase 4).

    python src/figures.py --results results

House style follows the figures4papers "scientific-figure-making" guide
(github.com/ChenLiu-1996/figures4papers):
  * Arial/Helvetica-type sans serif, top and right spines off, thicker axes,
    no grid, frameless legends
  * its blue / green / red / neutral palette: Rwanda dark blue, Kenya strong
    red, gains in green, reference bars in neutral grey; bars carry black
    edges and their values are printed on them
  * every series is ALSO direct-labelled and carries its own marker and line
    style, so identity never rests on colour alone and figures survive
    greyscale printing
  * one y-axis per panel - two measures become two panels, never a twin axis
  * 300 dpi PNG plus vector PDF with editable text, tight_layout(pad=1)
  * captions in figures/captions.md are self-sufficient: what, where, which
    scenario, which units, and the source CSV
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

PALETTE = {"blue_main": "#0F4D92", "blue_secondary": "#3775BA",
           "green_1": "#DDF3DE", "green_2": "#AADCA9", "green_3": "#8BCF8B",
           "red_1": "#F6CFCB", "red_2": "#E9A6A1", "red_strong": "#B64342",
           "neutral": "#CFCECE", "teal": "#42949E"}
SERIES = [PALETTE["blue_main"], PALETTE["red_strong"], PALETTE["teal"]]
MARKERS = ["o", "s", "^"]
STYLES = ["-", "--", ":"]
INK, INK2 = "#272727", "#4D4D4D"
SITE = {"rwanda": "Rwanda (Nkombo)", "kenya": "Kenya (Ringiti)"}
DPI = 300

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"],
    "font.size": 10, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.linewidth": 1.2, "xtick.major.width": 1.2, "ytick.major.width": 1.2,
    "xtick.major.size": 4, "ytick.major.size": 4,
    "axes.edgecolor": INK, "axes.labelcolor": INK, "xtick.color": INK,
    "ytick.color": INK, "text.color": INK, "axes.grid": False,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "lines.linewidth": 2.2, "lines.markersize": 6.5,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.04, "savefig.facecolor": "white",
    "pdf.fonttype": 42, "svg.fonttype": "none",
})


def style(i):
    return dict(color=SERIES[i], marker=MARKERS[i], linestyle=STYLES[i])


def label_end(ax, x, y, text, i, dx=4, dy=0):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points",
                color=SERIES[i] if i < len(SERIES) else INK, fontsize=9,
                fontweight="bold", va="center")


def save(fig, out, name):
    out.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(pad=1)
    fig.savefig(out / f"{name}.png", dpi=DPI)
    fig.savefig(out / f"{name}.pdf")
    plt.close(fig)


# ------------------------------------------------------------------ figure 1
def fig1_structure(out):
    fig, ax = plt.subplots(figsize=(6.8, 2.3))
    ax.set_axis_off()
    ax.set_xlim(0, 10); ax.set_ylim(0.95, 4.15)
    boxes = {
        "demand": (0.2, 1.6, "Household demand\nRAMP appliances +\ncooking meals (φ)"),
        "dispatch": (2.7, 1.6, "Hourly operation\nsolar, load, battery\n(8,760 h × 20 yr)"),
        "sizing": (5.2, 1.6, "Least-cost sizing\ntwo stages; unserved\n≤ 5% in every year"),
        "finance": (7.7, 1.6, "Finance\nLCOE, NPV and\noperating subsidy"),
    }
    for x, y, t in boxes.values():
        ax.add_patch(plt.Rectangle((x, y), 2.1, 1.2, fc="#E8EEF6",
                                   ec=PALETTE["blue_main"], lw=1.6))
        head, rest = t.split("\n", 1)
        ax.text(x + 1.05, y + 0.86, head, ha="center", va="center", fontsize=8.5,
                fontweight="bold", color=PALETTE["blue_main"])
        ax.text(x + 1.05, y + 0.42, rest, ha="center", va="center", fontsize=7.5)
    for a, b in (("demand", "dispatch"), ("dispatch", "sizing"), ("sizing", "finance")):
        xa, ya = boxes[a][0] + 2.1, boxes[a][1] + 0.6
        ax.annotate("", (boxes[b][0], ya), (xa, ya),
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.4,
                                    mutation_scale=12))
    inputs = [(1.25, "MTF microdata\n(ownership, dayparts)", "demand"),
              (3.75, "NASA POWER\nsolar and temperature", "dispatch"),
              (6.25, "AMDA / SEforALL\ncost benchmarks", "sizing"),
              (8.75, "National and site\ntariff scenarios", "finance")]
    for x, t, b in inputs:
        ax.text(x, 3.75, t, ha="center", va="center", fontsize=7.5, color=INK2)
        ax.annotate("", (x, 2.8), (x, 3.4), arrowprops=dict(
            arrowstyle="-|>", color=INK2, lw=1.0, linestyle=(0, (3, 2)),
            mutation_scale=10))
    ax.text(5.0, 1.15, "scenarios: share cooking × share of supper moved (φ) × tariff × random seed",
            ha="center", fontsize=8, color=INK2, style="italic")
    save(fig, out, "fig1_model_structure")


# ------------------------------------------------------------------ figure 2
def fig2_cooking(out, n=300, seeds=range(10)):
    from load_builder import build_cooking_load
    prof = np.mean([build_cooking_load(n, 1.0, 0.0, seed=s).reshape(-1, 24).mean(0)
                    for s in seeds], axis=0) * 1000 / n
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    for a, b, lab in ((6, 9, "breakfast"), (12, 14, "lunch"), (19, 21, "supper")):
        ax.axvspan(a - 0.5, b - 0.5, color=PALETTE["green_1"], lw=0, zorder=0)
        ax.text((a + b) / 2 - 0.5, prof.max() * 1.07, lab, ha="center",
                fontsize=7.5, color=INK2)
    ax.plot(np.arange(24), prof, **style(0))
    ax.set_xlabel("hour of day (local solar time)")
    ax.set_ylabel("cooking load, W per household")
    ax.set_xticks(range(0, 24, 3)); ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, prof.max() * 1.18)
    save(fig, out, "fig2_cooking_profile")


# ------------------------------------------------------------------ figure 5
def fig5_bands(B, out):
    """Average price per unit against monthly use, with the simulated average
    household marked without cooking (open marker) and with it (filled)."""
    from final_cfg import country_cfg
    from model import _band_rate
    kwh = np.linspace(1, 120, 480)
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    for i, site in enumerate(SITE):
        t = country_cfg(site)["tariff"]
        ax.plot(kwh, [_band_rate(k, t) for k in kwh], color=SERIES[i],
                linestyle=STYLES[i], lw=2.4)
        r = B[(B.site == site) & (B.basis == "simulated") & (B.year == 1)].iloc[0]
        a = (r.kwh_no_ecooking, r.rate_no_ecooking)
        b = (r.kwh_full_ecooking, r.rate_full_ecooking)
        ax.plot(*a, marker=MARKERS[i], color="white", linestyle="none", mec=SERIES[i],
                mew=1.8, ms=7, zorder=5)
        ax.plot(*b, marker=MARKERS[i], color=SERIES[i], linestyle="none", mec="black",
                mew=1.0, ms=7.5, zorder=5)
        ax.annotate("", b, a, arrowprops=dict(arrowstyle="-|>", color=SERIES[i], lw=1.1,
                                              shrinkA=6, shrinkB=6, alpha=0.9,
                                              connectionstyle="arc3,rad=-0.25" if i == 0
                                              else "arc3,rad=0.25"))
        label_end(ax, kwh[-1], _band_rate(kwh[-1], t),
                  ["Rwanda\n(block tariff)", "Kenya\n(single band)"][i], i)
    ax.plot([], [], marker="o", color="white", mec=INK, mew=1.6, ms=6.5, linestyle="none",
            label="average household, no cooking")
    ax.plot([], [], marker="o", color=INK2, mec="black", ms=6.5, linestyle="none",
            label="average household, all meals cooked")
    ax.legend(loc="lower right", fontsize=7.5)
    ax.set_xlabel("household use, kWh/month")
    ax.set_ylabel("average price paid, US$/kWh")
    ax.set_xlim(0, 120); ax.set_ylim(0, 0.235)
    ax.set_xticks(range(0, 121, 20))
    save(fig, out, "fig5_blended_tariff")


# ----------------------------------------------------------- sensitivity
SENS_LABEL = {"Capital cost": "Capital cost, −30% / +30%",
              "Operating cost": "Operating cost, −50% / +50%",
              "Discount rate": "Discount rate, 8% / 20%",
              "Battery cost": "Battery, US$150 / 450 per kWh",
              "Appliance demand growth": "Appliance growth, 0 / 5% a year",
              "Cooking energy": "Cooking, 0.87 / 2.0 kWh a day",
              "Bills collected": "Bills collected, 100% / 80%",
              "Unserved demand allowed": "Unserved demand, 10% / 2%",
              "All cost inputs together": "Capital, operating, discount\nrate and collection together"}


def fig_sensitivity(X, out):
    """Range of (a) the levelised cost with full cooking and (b) the extra
    subsidy per cooking household when each input moves between its low and
    high value, re-sizing the system each time. Vertical lines mark the base
    case. Source: sensitivity.csv."""
    base = X[X.side == "base"].set_index("site")
    V = X[X.side != "base"]
    q_b = "incremental_usd_per_cooking_hh_year"
    order = (V[V.site == "rwanda"].groupby("parameter")[q_b]
             .agg(lambda v: v.max() - v.min()).sort_values().index.tolist())
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.5), sharey=True,
                             gridspec_kw={"width_ratios": [1, 1]})
    h = 0.34
    for ax, q, title, xlabel in (
            (axes[0], "lcoe_full", "(a) LCOE, all households cooking", "LCOE, US$/kWh"),
            (axes[1], q_b, "(b) Extra subsidy per cooking household", "US$ per household per year")):
        for i, site in enumerate(SITE):
            g = V[V.site == site]
            for y, name in enumerate(order):
                v = g[g.parameter == name][q]
                ax.barh(y + (0.5 - i) * (h + 0.04), v.max() - v.min(), h, left=v.min(),
                        color=SERIES[i], edgecolor="black", linewidth=0.7,
                        hatch="///" if i else None, alpha=0.92 if i == 0 else 0.85)
            ax.axvline(base.loc[site, q], color=SERIES[i], lw=1.3,
                       ls=STYLES[i], zorder=0)
        ax.set_title(title, loc="left", fontsize=9.5)
        ax.set_xlabel(xlabel)
        ax.set_xlim(left=0)
    axes[0].set_yticks(range(len(order)))
    axes[0].set_yticklabels([SENS_LABEL.get(n, n) for n in order], fontsize=8)
    from matplotlib.patches import Patch
    axes[1].legend([Patch(facecolor=SERIES[0], edgecolor="black"),
                    Patch(facecolor=SERIES[1], edgecolor="black", hatch="///")],
                   ["Rwanda", "Kenya"], fontsize=8, loc="lower right")
    save(fig, out, "fig_sensitivity")


# ------------------------------------------------------- daytime discount
def fig_daytime(E, out):
    """Effect of moving a share of supper cooking to the afternoon, full
    adoption: mean of the seed ensemble with the 95% interval of the mean.
    (a) batteries bought over the project, saving against the flat tariff;
    (b) the largest daytime discount the operator can give before the saving
    is used up; (c) change in the cooking peak. Source: ensemble_summary.csv."""
    def series(site, q):
        g = E[(E.site == site) & E.quantity.str.startswith(q + "_phi")].copy()
        g["phi"] = g.quantity.str[-2:].astype(int) / 100.0
        return g.sort_values("phi")
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7))
    for i, site in enumerate(SITE):
        name = SITE[site].split()[0]
        for ax, q, scale in ((axes[0], "avoided_battery_pct", 1.0),
                             (axes[1], "break_even_discount", 100.0)):
            g = series(site, q)
            ax.fill_between(g.phi, scale * g.ci95_lo, scale * g.ci95_hi, color=SERIES[i],
                            alpha=0.2, lw=0)
            ax.plot(g.phi, scale * g["mean"], **style(i), markersize=5, mec="black", mew=0.6)
            label_end(ax, g.phi.iloc[-1], scale * g["mean"].iloc[-1], name, i,
                      dy=5 if i else -5)
    g = series("rwanda", "peak_cooking_increase_pct")     # same cooking in both villages
    axes[2].fill_between(g.phi, g.ci95_lo, g.ci95_hi, color=SERIES[2], alpha=0.2, lw=0)
    axes[2].plot(g.phi, g["mean"], **style(2), markersize=5, mec="black", mew=0.6)
    axes[2].axhline(0, color=INK2, lw=1.0, ls=(0, (4, 3)))
    axes[0].set_title("(a) Battery saved", loc="left", fontsize=9.5)
    axes[0].set_ylabel("% of battery capacity bought")
    axes[1].set_title("(b) Break-even discount", loc="left", fontsize=9.5)
    axes[1].set_ylabel("US cents/kWh")
    axes[2].set_title("(c) Cooking peak", loc="left", fontsize=9.5)
    axes[2].set_ylabel("change, %")
    for ax in axes:
        ax.set_xlabel("share of supper cooking moved, φ")
        ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.5])
        ax.set_xlim(0.07, 0.62 if ax is not axes[2] else 0.53)
    for ax in axes[:2]:
        ax.set_ylim(bottom=0)
    save(fig, out, "fig_daytime")


def fig_cost_vs_price(CP, out):
    """(a) LCOE split into per-connection costs and solar, battery and inverter,
    by share of households cooking; (b) average price paid per kWh, labelled
    with the LCOE as a multiple of that price. Source: cost_vs_price.csv."""
    from matplotlib.patches import Patch
    pens = sorted(CP.penetration.unique())
    lab = [f"{p:.0%}" for p in pens]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.9),
                               gridspec_kw={"width_ratios": [1.25, 1]})
    edge = dict(edgecolor="black", linewidth=0.8)
    w = 0.38
    for i, (site, col) in enumerate(zip(SITE, SERIES)):
        c = CP[CP.site == site].set_index("penetration").loc[pens]
        x = np.arange(len(pens)) + (i - 0.5) * (w + 0.04)
        a.bar(x, c.per_connection_fixed, w, color=PALETTE["neutral"], hatch="///", **edge)
        a.bar(x, c.supply, w, bottom=c.per_connection_fixed, color=col, **edge)
        for xi, tot in zip(x, c.lcoe):
            a.annotate(f"{tot:.2f}", (xi, tot), xytext=(0, 2), textcoords="offset points",
                       ha="center", fontsize=8, fontweight="bold", color=col)
    a.set_xticks(np.arange(len(pens)))
    a.set_xticklabels(lab)
    a.set_xlabel("Households cooking with electricity")
    a.set_ylabel("LCOE, US$/kWh")
    a.set_ylim(0, CP.lcoe.max() * 1.18)
    a.set_title("(a) Cost of supply per kWh", loc="left")
    a.legend([Patch(facecolor=PALETTE["neutral"], hatch="///", edgecolor="black"),
              Patch(facecolor=SERIES[0], edgecolor="black"),
              Patch(facecolor=SERIES[1], edgecolor="black")],
             ["Per connection: connection, its\nsoft cost, customer operation",
              "Solar, battery, inverter (Rwanda)", "Solar, battery, inverter (Kenya)"],
             fontsize=7, loc="upper right")
    for i, (site, col) in enumerate(zip(SITE, SERIES)):
        r = CP[CP.site == site].set_index("penetration").loc[pens]
        b.plot(np.arange(len(pens)), r.avg_price_paid, **style(i), label=SITE[site])
        for xi, (p, m) in enumerate(zip(r.avg_price_paid, r.lcoe_over_price)):
            # Rwanda's price starts below Kenya's and ends above it: put each
            # series' labels on the side away from the other line.
            up = (r.avg_price_paid.iloc[xi] >=
                  CP[(CP.site != site)].set_index("penetration").avg_price_paid.loc[pens[xi]])
            b.annotate(f"{m:.0f}×" if m >= 10 else f"{m:.1f}×", (xi, p),
                       xytext=(0, 8 if up else -15), textcoords="offset points",
                       ha="center", fontsize=8, fontweight="bold", color=col)
    b.set_xticks(np.arange(len(pens)))
    b.set_xticklabels(lab)
    b.set_xlabel("Households cooking with electricity")
    b.set_ylabel("Average price paid, US$/kWh")
    b.set_ylim(0, CP.avg_price_paid.max() * 1.45)
    b.set_xlim(-0.3, len(pens) - 0.7)
    b.set_title("(b) Price paid per kWh (labels: LCOE ÷ price)", loc="left", fontsize=9.5)
    b.legend(fontsize=7.5, loc="upper left")
    save(fig, out, "fig_cost_vs_price")


def build(results, out=None):
    R = Path(results)
    out = Path(out or R / "figures")
    have = lambda f: (R / f).exists()
    fig1_structure(out)
    fig2_cooking(out)
    if have("cost_vs_price.csv"):
        fig_cost_vs_price(pd.read_csv(R / "cost_vs_price.csv"), out)
    if have("sensitivity.csv"):
        fig_sensitivity(pd.read_csv(R / "sensitivity.csv"), out)
    if have("ensemble_summary.csv"):
        fig_daytime(pd.read_csv(R / "ensemble_summary.csv"), out)
    fig5_bands(pd.read_csv(R / "tariff_band_recomputed.csv"), out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    print("figures ->", build(a.results, a.out))


if __name__ == "__main__":
    main()
