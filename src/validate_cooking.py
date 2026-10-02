"""Validate the modelled cooking profile against an independent metered target.

The daypart split used to build the cooking module comes from the Kenya MTF
cooking module - RECALL data. The validation target here is METERED data from
the MECS monitoring campaigns. Different instrument, different households,
different study, so the comparison is not circular.

    python src/validate_cooking.py --target data/raw/mecs_profile_kenya.csv \
        --households 300 --out results/validation

Target CSV format (digitised from the published figure):
    hour,mean_w_per_household[,p05_w,p95_w]
    0,12.4,2.1,31.0
    ...
24 rows. Include the confidence band columns if the source publishes them -
falling inside the band is a stronger result than any single error metric.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from load_builder import build_cooking_load, cooking_daypart_shares, DAYPART_WINDOWS


def modelled_diurnal(n_households, penetration=1.0, phi=0.0, seed=42):
    """Mean W per cooking household, by hour of day."""
    load_kw = build_cooking_load(n_households, penetration, phi, seed=seed)
    hours = np.arange(len(load_kw)) % 24
    per_hh_w = np.array([load_kw[hours == h].mean() for h in range(24)]) * 1000.0
    n_cook = max(int(round(n_households * penetration)), 1)
    return per_hh_w / n_cook


def metrics(model_w, target_w):
    m, t = np.asarray(model_w, float), np.asarray(target_w, float)
    resid = m - t
    rmse = float(np.sqrt((resid ** 2).mean()))
    nrmse = rmse / t.mean() if t.mean() else np.nan
    # Shape agreement independent of level
    ms, ts = m / m.sum(), t / t.sum()
    return {
        "rmse_w": rmse,
        "nrmse_pct": 100 * nrmse,
        "mean_bias_w": float(resid.mean()),
        "peak_hour_model": int(np.argmax(m)),
        "peak_hour_target": int(np.argmax(t)),
        "peak_hour_error_h": int(np.argmax(m) - np.argmax(t)),
        "peak_w_model": float(m.max()),
        "peak_w_target": float(t.max()),
        "peak_error_pct": 100 * (m.max() - t.max()) / t.max() if t.max() else np.nan,
        "daily_kwh_model": float(m.sum() / 1000),
        "daily_kwh_target": float(t.sum() / 1000),
        "shape_correlation": float(np.corrcoef(m, t)[0, 1]),
        "shape_mae_pct_pts": float(100 * np.abs(ms - ts).mean()),
    }


def daypart_table(model_w, target_w):
    rows = []
    for name, (lo, hi) in DAYPART_WINDOWS.items():
        sel = (np.arange(24) >= lo) & (np.arange(24) < hi)
        rows.append({"daypart": name,
                     "model_share": model_w[sel].sum() / model_w.sum(),
                     "target_share": target_w[sel].sum() / target_w.sum()})
    d = pd.DataFrame(rows)
    d["difference_pp"] = 100 * (d.model_share - d.target_share)
    return d


def band_coverage(model_w, p05, p95):
    """Share of hours where the model sits inside the measured 5-95% band."""
    inside = (model_w >= np.asarray(p05)) & (model_w <= np.asarray(p95))
    return float(inside.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--households", type=int, default=300)
    ap.add_argument("--penetration", type=float, default=1.0)
    ap.add_argument("--out", default="results/validation")
    args = ap.parse_args()

    tgt = pd.read_csv(args.target).sort_values("hour")
    assert len(tgt) == 24, "target must have 24 hourly rows"
    model = modelled_diurnal(args.households, args.penetration, phi=0.0)
    target = tgt.mean_w_per_household.values

    m = metrics(model, target)
    dp = daypart_table(model, target)

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([m]).to_csv(out / "cooking_validation_metrics.csv", index=False)
    dp.to_csv(out / "cooking_validation_dayparts.csv", index=False)
    pd.DataFrame({"hour": range(24), "model_w": model,
                  "target_w": target}).to_csv(out / "cooking_profile_comparison.csv",
                                              index=False)

    print("Cooking profile validation (phi=0, no tuning)\n")
    for k, v in m.items():
        print(f"  {k:<22} {v:>10.3f}" if isinstance(v, float) else f"  {k:<22} {v:>10}")
    print("\nDaypart shares")
    print(dp.to_string(index=False))
    if {"p05_w", "p95_w"} <= set(tgt.columns):
        cov = band_coverage(model, tgt.p05_w, tgt.p95_w)
        print(f"\n  hours inside measured 5-95% band: {cov*100:.0f}%")
    print(f"\nWrote 3 CSVs to {out}")


if __name__ == "__main__":
    main()
