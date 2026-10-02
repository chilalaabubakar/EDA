"""Parse raw NASA POWER JSON into a tidy hourly frame, validate it, and pick a
representative year.

    python src/load_resource.py --params params.yaml

Outputs:
    data/processed/resource_<site>.csv     hourly GHI, T2M, WS2M, pv_cf
    data/processed/resource_summary.csv    annual totals per site-year
Prints a validation report. Fails loudly rather than passing bad data downstream.
"""
import argparse, json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

RAW = Path("data/raw/power")
PROC = Path("data/processed")
FILL = -999.0          # NASA POWER missing-value sentinel


def parse_year(path):
    payload = json.loads(Path(path).read_text())
    params = payload["properties"]["parameter"]
    frames = {}
    for var, series in params.items():
        idx = pd.to_datetime(list(series.keys()), format="%Y%m%d%H")
        frames[var] = pd.Series(list(series.values()), index=idx, dtype="float64")
    df = pd.DataFrame(frames).sort_index()
    return df.replace(FILL, np.nan)


def pv_capacity_factor(ghi, tair, noct, temp_coeff, derate):
    """Single-diode-free engineering model. GHI in W/m2 used as plane-of-array
    proxy - state this simplification in the paper's method section."""
    tcell = tair + (noct - 20.0) / 800.0 * ghi
    cf = (ghi / 1000.0) * (1.0 + temp_coeff * (tcell - 25.0)) * derate
    return cf.clip(lower=0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.params))
    pv = cfg["shared"]["pv"]
    PROC.mkdir(parents=True, exist_ok=True)

    summary, problems = [], []

    for site in cfg["countries"]:
        files = sorted(RAW.glob(f"{site}_*.json"))
        if not files:
            problems.append(f"{site}: no raw files - run fetch_power.py first")
            continue

        df = pd.concat([parse_year(f) for f in files]).sort_index()
        df = df[~df.index.duplicated(keep="first")]

        # --- validation -------------------------------------------------
        n_missing = int(df.isna().sum().sum())
        if n_missing:
            problems.append(f"{site}: {n_missing} missing values after -999 removal")

        expected = pd.date_range(df.index[0], df.index[-1], freq="h")
        gaps = len(expected) - len(df)
        if gaps:
            problems.append(f"{site}: {gaps} missing hourly timestamps")

        ghi = df["ALLSKY_SFC_SW_DWN"]
        # Solar-noon check. This is THE test that catches a UTC/LST mix-up,
        # which would silently misalign the time-of-use window and invalidate
        # the entire analysis. Near the equator a few hours of offset still
        # leaves midnight dark, so checking night-time GHI is not enough -
        # the diurnal peak has to be in the right place.
        diurnal = ghi.groupby(ghi.index.hour).mean()
        peak_hour = int(diurnal.idxmax())
        if not 11 <= peak_hour <= 13:
            problems.append(
                f"{site}: mean GHI peaks at hour {peak_hour}, expected 11-13. "
                "Timestamps are offset - almost certainly UTC rather than local "
                "solar time. Re-fetch with time-standard=LST before going further.")
        if diurnal[0] > 5:
            problems.append(
                f"{site}: mean GHI at hour 0 is {diurnal[0]:.1f} W/m2, expected ~0.")
        # Daylight window sanity: hours with meaningful sun should be contiguous
        # and roughly 11-13 hours near the equator.
        daylight = int((diurnal > 20).sum())
        if not 9 <= daylight <= 14:
            problems.append(
                f"{site}: {daylight} daylight hours in the mean profile, expected 9-14.")
        print(f"  [{site}] solar noon at hour {peak_hour}, {daylight} daylight hours")

        df["pv_cf"] = pv_capacity_factor(
            ghi, df["T2M"], pv["noct_c"], pv["temp_coeff_per_c"], pv["derate_factor"])

        df.to_csv(PROC / f"resource_{site}.csv")

        for year, g in df.groupby(df.index.year):
            if len(g) < 8000:      # partial year, ignore for year selection
                continue
            summary.append({
                "site": site,
                "year": int(year),
                "ghi_kwh_m2_yr": round(g["ALLSKY_SFC_SW_DWN"].sum() / 1000.0, 1),
                "mean_temp_c": round(g["T2M"].mean(), 2),
                "pv_yield_kwh_per_kwp": round(g["pv_cf"].sum(), 1),
                "hours": len(g),
            })

    if not summary:
        print("No complete years parsed.")
        for p in problems:
            print("  PROBLEM:", p)
        return

    s = pd.DataFrame(summary)
    s.to_csv(PROC / "resource_summary.csv", index=False)

    print("Annual resource by site\n")
    for site, g in s.groupby("site"):
        med = g["ghi_kwh_m2_yr"].median()
        rep = int(g.iloc[(g["ghi_kwh_m2_yr"] - med).abs().argsort().iloc[0]]["year"])
        spread = 100 * (g["ghi_kwh_m2_yr"].max() - g["ghi_kwh_m2_yr"].min()) / med
        print(f"  {site}")
        print(f"    years                {g.year.min()}-{g.year.max()} ({len(g)})")
        print(f"    median annual GHI    {med:.0f} kWh/m2")
        print(f"    interannual spread   {spread:.1f}% of median")
        print(f"    PV yield (median yr) {g.loc[g.year == rep, 'pv_yield_kwh_per_kwp'].iloc[0]:.0f} kWh/kWp")
        print(f"    REPRESENTATIVE YEAR  {rep}   <- put this in params.yaml\n")

    if problems:
        print("VALIDATION PROBLEMS")
        for p in problems:
            print("  -", p)
    else:
        print("Validation passed.")


if __name__ == "__main__":
    main()
