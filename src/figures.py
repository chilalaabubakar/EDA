"""All manuscript figures, from the results CSVs (Phase 4).

    python src/figures.py --results results

Conventions (checked by tests/test_figures.py):
  * colour: validated categorical slots (blue, orange, aqua) - CVD-safe on
    every pair (worst deltaE 9.2, deutan). Aqua is below 3:1 contrast on white,
    so every series is ALSO direct-labelled and carries its own marker and
    line style: identity never rests on colour alone, and figures survive
    greyscale printing.
  * one y-axis per panel - two measures become two panels, never a twin axis
  * 300 dpi PNG plus vector PDF
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

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # validated slots 1-3
MARKERS = ["o", "s", "^"]
STYLES = ["-", "--", ":"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SITE = {"rwanda": "Rwanda (Nkombo)", "kenya": "Kenya (Ringiti)"}
DPI = 300

plt.rcParams.update({
    "font.size": 9, "axes.titlesize": 9.5, "axes.labelsize": 9,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "text.color": INK, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False, "lines.linewidth": 1.8,
    "lines.markersize": 6, "savefig.bbox": "tight", "pdf.fonttype": 42,
})


def style(i):
    return dict(color=SERIES[i], marker=MARKERS[i], linestyle=STYLES[i])


def label_end(ax, x, y, text, i, dx=4, dy=0):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points",
                color=INK, fontsize=8, va="center")


def save(fig, out, name):
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.png", dpi=DPI)
    fig.savefig(out / f"{name}.pdf")
    plt.close(fig)


# ------------------------------------------------------------------ figure 1
def fig1_structure(out):
    fig, ax = plt.subplots(figsize=(6.8, 2.9))
    ax.set_axis_off()
    ax.set_xlim(0, 10); ax.set_ylim(0, 4.2)
    boxes = {
        "demand": (0.2, 1.6, "Stochastic demand\nRAMP appliances +\ncooking events (φ)"),
        "dispatch": (2.7, 1.6, "Hourly dispatch\nPV → load → battery\n(8,760 h × 20 yr)"),
        "sizing": (5.2, 1.6, "Least-cost sizing\nworst-year\nunmet ≤ 5%"),
        "finance": (7.7, 1.6, "Finance\nLCOE, NPV, IRR,\ninverse solvers"),
    }
    for x, y, t in boxes.values():
        ax.add_patch(plt.Rectangle((x, y), 2.1, 1.2, fc="#f3f2ef", ec=INK2, lw=0.8))
        ax.text(x + 1.05, y + 0.6, t, ha="center", va="center", fontsize=7.5)
    for a, b in (("demand", "dispatch"), ("dispatch", "sizing"), ("sizing", "finance")):
        xa, ya = boxes[a][0] + 2.1, boxes[a][1] + 0.6
        ax.annotate("", (boxes[b][0], ya), (xa, ya),
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.0))
    inputs = [(1.25, "MTF microdata\n(ownership, dayparts)", "demand"),
              (3.75, "NASA POWER\nGHI, T (LST)", "dispatch"),
              (6.25, "AMDA / SEforALL\ncost benchmarks", "sizing"),
              (8.75, "RURA / EPRA\ntariff schedules", "finance")]
    for x, t, b in inputs:
        ax.text(x, 3.75, t, ha="center", va="center", fontsize=7, color=INK2)
        ax.annotate("", (x, 2.8), (x, 3.4), arrowprops=dict(
            arrowstyle="->", color=INK2, lw=0.8, linestyle=(0, (3, 2))))
    ax.text(5.0, 0.8, "scenario sweep: penetration × φ × tariff × discount × seed",
            ha="center", fontsize=7.5, color=INK2)
    save(fig, out, "fig1_model_structure")


# ------------------------------------------------------------------ figure 2
def fig2_cooking(out, n=300, seeds=range(10)):
    from load_builder import build_cooking_load
    prof = np.mean([build_cooking_load(n, 1.0, 0.0, seed=s).reshape(-1, 24).mean(0)
                    for s in seeds], axis=0) * 1000 / n
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    for a, b, lab in ((6, 9, "breakfast"), (12, 14, "lunch"), (19, 21, "supper")):
        ax.axvspan(a - 0.5, b - 0.5, color="#ecebe7", lw=0, zorder=0)
        ax.text((a + b) / 2 - 0.5, prof.max() * 1.07, lab, ha="center",
                fontsize=7.5, color=INK2)
    ax.plot(np.arange(24), prof, **style(0))
    ax.set_xlabel("hour of day (local solar time)")
    ax.set_ylabel("cooking load, W per household")
    ax.set_xticks(range(0, 24, 3)); ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, prof.max() * 1.18)
    save(fig, out, "fig2_cooking_profile")


# ------------------------------------------------------------------ figure 3
def fig3_penetration(S, out):
    flat = S[(S.tariff == "flat") & S.feasible].drop_duplicates(["site", "penetration"])
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.8))
    for i, site in enumerate(SITE):
        g = flat[flat.site == site].sort_values("penetration")
        x = 100 * g.penetration
        dy = 7 if i == 0 else -7          # dodge: end values can coincide
        axes[0].plot(x, g.lcoe, **style(i))
        label_end(axes[0], x.iloc[-1], g.lcoe.iloc[-1], SITE[site].split()[0], i, dy=dy)
        axes[1].plot(x, g.battery_kwh, **style(i))
        label_end(axes[1], x.iloc[-1], g.battery_kwh.iloc[-1], SITE[site].split()[0], i, dy=dy)
    axes[0].set_ylabel("LCOE, US$/kWh"); axes[0].set_title("(a) levelised cost", loc="left")
    axes[1].set_ylabel("storage, kWh"); axes[1].set_title("(b) least-cost storage", loc="left")
    for ax in axes:
        ax.set_xlabel("eCooking penetration, %"); ax.set_xticks([0, 50, 100])
        ax.set_xlim(-5, 125); ax.set_ylim(bottom=0)
    axes[0].legend([SITE[s] for s in SITE], loc="upper right", fontsize=7.5)
    fig.tight_layout()
    save(fig, out, "fig3_penetration")


# ------------------------------------------------------------------ figure 4
def fig4_substitution(T, out):
    T = T[T.response == "step"]
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.8), sharey=True)
    for ax, site in zip(axes, SITE):
        g = T[T.site == site]
        for i, phi in enumerate(sorted(g.phi_nominal.unique())):
            h = g[g.phi_nominal == phi].sort_values("discount")
            ax.plot(100 * h.discount, h.avoided_battery_kwh, drawstyle="steps-post",
                    color=SERIES[i], linestyle=STYLES[i], marker=MARKERS[i],
                    markersize=4.5, mec="white", mew=0.8)
            label_end(ax, 100 * h.discount.iloc[-1], h.avoided_battery_kwh.iloc[-1],
                      f"φ = {phi:.1f}", i)
        ax.set_title(SITE[site], loc="left")
        ax.set_xlabel("daytime discount, US¢/kWh")
        ax.set_xlim(-0.3, 100 * g.discount.max() + 3.5)
    axes[0].set_ylabel("avoided storage, kWh")
    axes[0].set_ylim(bottom=0)
    axes[0].legend([f"φ = {p:.1f}" for p in sorted(T.phi_nominal.unique())],
                   loc="center right", fontsize=7.5)
    fig.tight_layout()
    save(fig, out, "fig4_substitution")


# ------------------------------------------------------------------ figure 5
def fig5_bands(B, out):
    from final_cfg import country_cfg
    from model import _band_rate
    kwh = np.linspace(1, 120, 480)
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    for i, site in enumerate(SITE):
        t = country_cfg(site)["tariff"]
        ax.plot(kwh, [_band_rate(k, t) for k in kwh], color=SERIES[i],
                linestyle=STYLES[i])
        sim = B[(B.site == site) & (B.basis == "simulated")]
        for _, r in sim[sim.year.isin([1, 20])].iterrows():
            ax.plot(r.kwh_full_ecooking, r.rate_full_ecooking, marker=MARKERS[i],
                    color=SERIES[i], linestyle="none", mec="white", mew=1.0)
            ax.annotate(f"yr {int(r.year)}", (r.kwh_full_ecooking, r.rate_full_ecooking),
                        xytext=(-22, 6) if i == 0 else (3, -11), textcoords="offset points",
                        fontsize=7, color=INK2)
        label_end(ax, kwh[-1], _band_rate(kwh[-1], t), SITE[site].split()[0], i)
    ax.set_xlabel("household consumption, kWh/month")
    ax.set_ylabel("blended tariff, US$/kWh")
    ax.set_xlim(0, 138); ax.set_ylim(0, None)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=SERIES[i], linestyle=STYLES[i], marker=MARKERS[i])
               for i in range(len(SITE))]
    ax.legend(handles, [f"{SITE[s]} ({'telescopic' if i == 0 else 'non-telescopic'})"
                        for i, s in enumerate(SITE)], loc="lower right", fontsize=7.5)
    save(fig, out, "fig5_blended_tariff")


# ------------------------------------------------------------------ figure 6
def fig6_viability(D, out):
    from final_cfg import country_cfg
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    for i, site in enumerate(SITE):
        g = D[D.site == site].sort_values("discount_rate")
        ax.plot(100 * g.discount_rate, g.cost_reflective_tariff, **style(i))
        label_end(ax, 100 * g.discount_rate.iloc[-1], g.cost_reflective_tariff.iloc[-1],
                  f"{SITE[site].split()[0]}, cost-reflective", i, dy=6 if i == 0 else -6)
        reg = country_cfg(site)["tariff"]["flat_rate_per_kwh"]
        ax.axhline(reg, color=SERIES[i], lw=1.0, linestyle=(0, (1, 2)))
        ax.annotate(f"{SITE[site].split()[0]} regulated ${reg:.3f}", (7.3, reg),
                    xytext=(0, 3 if i == 0 else -9), textcoords="offset points",
                    fontsize=7, color=INK2)
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator([0.1, 0.2, 0.5, 1, 2, 5]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}"))
    ax.set_ylim(0.1, max(D.cost_reflective_tariff.max() * 1.6, 2))
    ax.set_xlabel("real discount rate, %")
    ax.set_ylabel("tariff, US$/kWh (log scale)")
    ax.set_xlim(7, 29)
    save(fig, out, "fig6_viability")


# ------------------------------------------------- journal figures (Phase 4b)
def fig_tou_operator(T, out, phi=0.5):
    """(a) avoided storage and (b) operator NPV gain against the daytime
    discount, full penetration, one phi. Shows the step response: storage
    avoided is flat in the discount, the revenue given up is not."""
    T = T[(T.response == "step") & (T.phi_nominal == phi)]
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.7))
    for i, site in enumerate(SITE):
        g = T[T.site == site].sort_values("discount")
        x = 100 * g.discount
        axes[0].plot(x, g.avoided_battery_kwh, drawstyle="steps-post",
                     color=SERIES[i], linestyle=STYLES[i])
        axes[0].plot(x, g.avoided_battery_kwh, linestyle="none", marker=MARKERS[i],
                     color=SERIES[i], markersize=4, mec="white", mew=0.6)
        pos = g[g.discount > 0]
        axes[1].plot(100 * pos.discount, pos.operator_npv_gain / 1000, **style(i),
                     markersize=4, mec="white", mew=0.6)
        name = SITE[site].split()[0]
        label_end(axes[0], x.iloc[-1], g.avoided_battery_kwh.iloc[-1], name, i,
                  dy=6 if i else -6)
        label_end(axes[1], 100 * pos.discount.iloc[-1],
                  pos.operator_npv_gain.iloc[-1] / 1000, name, i)
    axes[0].set_title("(a) storage avoided", loc="left")
    axes[0].set_ylabel("kWh")
    axes[0].set_ylim(0, T.avoided_battery_kwh.max() * 1.25)
    axes[1].set_title("(b) change in operator NPV", loc="left")
    axes[1].set_ylabel("US$ thousand")
    axes[1].axhline(0, color=INK2, lw=0.8)
    axes[1].set_ylim(bottom=-5)
    for ax in axes:
        ax.set_xlabel("daytime discount, US cents/kWh")
        ax.set_xlim(-0.3, 100 * T.discount.max() + 3.2)
    fig.tight_layout()
    save(fig, out, "fig_tou_operator")


def fig_esmap(W, out):
    """Cumulative LCOE bridge from the headline to benchmark-like conventions."""
    steps = ["Headline", "Discount\nrate 10%", "No growth\nreserve",
             "Demand\nx2", "Bench-\nmark"]
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.9), sharey=True)
    for ax, site in zip(axes, SITE):
        v = W[W.site == site].lcoe.values
        x = np.arange(len(v) + 1)
        ax.bar(0, v[0], color="#b8b6ae", width=0.62)
        for i in range(1, len(v)):
            ax.bar(i, v[i] - v[i - 1], bottom=v[i - 1], color="#1baf7a", alpha=0.75,
                   width=0.62)
            ax.annotate(f"\u2212{v[i - 1] - v[i]:.2f}", (i, v[i - 1]), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=7.5)
            ax.plot([i - 1.31, i - 0.31], [v[i - 1], v[i - 1]], color=INK2, lw=0.6,
                    ls=":")
        ax.bar(len(v), v[-1], color="#b8b6ae", width=0.62)
        ax.plot([len(v) - 1.31, len(v) - 0.31], [v[-1], v[-1]], color=INK2, lw=0.6, ls=":")
        for i, val in ((0, v[0]), (len(v), v[-1])):
            ax.annotate(f"${val:.2f}", (i, val), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=7.5, fontweight="bold")
        ax.axhline(0.55, color=INK2, lw=0.8, ls=(0, (4, 3)))
        ax.annotate("ESMAP reference $0.55", (2.0, 0.55), xytext=(0, -11),
                    textcoords="offset points", ha="center", fontsize=7, color=INK2)
        ax.set_axisbelow(True)
        ax.set_xticks(x)
        ax.set_xticklabels(steps, fontsize=7)
        ax.set_title(SITE[site], loc="left")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("LCOE, US$/kWh")
    axes[0].set_ylim(0, 1.25)
    fig.tight_layout()
    save(fig, out, "fig_esmap")


def build(results, out=None):
    R = Path(results)
    out = Path(out or R / "figures")
    fig1_structure(out)
    fig2_cooking(out)
    fig3_penetration(pd.read_csv(R / "scenarios_both.csv"), out)
    if (R / "tou_sweep.csv").exists():
        fig4_substitution(pd.read_csv(R / "tou_sweep.csv"), out)
    fig5_bands(pd.read_csv(R / "tariff_band_recomputed.csv"), out)
    fig6_viability(pd.read_csv(R / "discount_sweep.csv"), out)
    if (R / "tou_sweep.csv").exists():
        fig_tou_operator(pd.read_csv(R / "tou_sweep.csv"), out)
    if (R / "esmap_waterfall.csv").exists():
        fig_esmap(pd.read_csv(R / "esmap_waterfall.csv"), out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    print("figures ->", build(a.results, a.out))


if __name__ == "__main__":
    main()
