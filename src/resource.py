"""Solar resource access for the model.

Real data: data/processed/resource_<site>.csv, written by load_resource.py from
NASA POWER hourly JSON (fetch_power.py), in LOCAL SOLAR TIME.

Synthetic data: `synthetic_resource()` exists ONLY so the test-suite and CI can
exercise the pipeline where NASA POWER is unreachable. Anything computed from
it is written under results/synthetic/ by pipeline.py and must never be quoted.
"""
from pathlib import Path

import numpy as np
import pandas as pd

PROC = Path("data/processed")
HOURS = 8760
GHI, T2M = "ALLSKY_SFC_SW_DWN", "T2M"


def _frame(site, proc=PROC):
    path = Path(proc) / f"resource_{site}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing. Run `python src/pipeline.py resource` (needs "
            "network access to power.larc.nasa.gov), or pass --synthetic for a "
            "smoke run.")
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _year(d, year):
    d = d[d.index.year == year]
    # Leap years: drop 29 Feb so every year is 8760 hours on the same calendar.
    d = d[~((d.index.month == 2) & (d.index.day == 29))].iloc[:HOURS]
    if len(d) != HOURS:
        raise ValueError(f"year {year}: {len(d)} hours, expected {HOURS}")
    return {"ghi": d[GHI].values.astype(float), "tair": d[T2M].values.astype(float),
            "year": int(year)}


def load_site_resource(site, year, proc=PROC):
    """One weather year as {'ghi', 'tair', 'year'}."""
    return _year(_frame(site, proc), year)


def resource_years(site, proc=PROC):
    """{year: resource} for every complete year on file."""
    d = _frame(site, proc)
    out = {}
    for y in sorted(set(d.index.year)):
        try:
            out[y] = _year(d, y)
        except ValueError:
            continue
    return out


def synthetic_resource(seed=0, peak_ghi=950.0, cloudiness=0.25, year=None):
    """Clear-sky-shaped GHI with seeded cloud noise. TEST/CI ONLY."""
    rng = np.random.default_rng(seed)
    h = np.arange(HOURS) % 24
    ghi = (np.clip(np.sin((h - 6) / 12 * np.pi), 0, None) * peak_ghi
           * (1 - cloudiness * rng.random(HOURS)))
    tair = 22 + 6 * np.clip(np.sin((h - 7) / 12 * np.pi), 0, None)
    return {"ghi": ghi, "tair": tair, "year": year, "synthetic": True}


def synthetic_years(site, years=range(2005, 2025)):
    """Twenty synthetic years with ~8% interannual spread. TEST/CI ONLY."""
    base = {"rwanda": 870.0, "kenya": 1000.0}.get(site, 950.0)
    rng = np.random.default_rng(len(site))
    out = {}
    for y in years:
        out[y] = synthetic_resource(seed=y, peak_ghi=base * (1 + 0.03 * rng.standard_normal()),
                                    year=y)
    return out
