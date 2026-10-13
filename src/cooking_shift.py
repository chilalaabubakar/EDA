"""How much cooking falls in the daytime discount window, by phi.

The share of evening meals moved (phi) is a scenario value, not an estimate.
The one metered time-of-use pilot found (Oloika mini-grid, Kenya; COSMO
Phase 2 final report, University of Southampton for MECS, 2025) measured 57%
of e-cooking energy in the discounted daylight hours over April to July 2025,
with seven customers, mostly restaurants. This writes the model's daytime
share of cooking energy for each phi, so the two can be compared.

    python src/pipeline.py daytime_share  ->  results/cooking_daytime_share.csv
"""
import numpy as np
import pandas as pd

from run_scenarios import make_load_builder

OLOIKA_DAYTIME_SHARE = 0.57


def daytime_share(cfg, n_households, phi, seed=42, year=1):
    """Share of cooking energy inside the discount window (cooking = load with
    full adoption minus load with none, same seed)."""
    w = cfg["tariff"]["daytime_window_hours"]
    ck = (make_load_builder(cfg, n_households, 1.0, phi, seed)(year)
          - make_load_builder(cfg, n_households, 0.0, 0.0, seed)(year))
    h = np.arange(len(ck)) % 24
    return float(ck[(h >= w[0]) & (h < w[1])].sum() / ck.sum())


def table(cfgs, n_households, phis=(0.0, 0.3, 0.5), seed=42):
    rows = [{"site": site, "phi": phi,
             "daytime_share_of_cooking_energy": daytime_share(cfg, n_households, phi, seed),
             "oloika_measured": OLOIKA_DAYTIME_SHARE}
            for site, cfg in cfgs.items() for phi in phis]
    return pd.DataFrame(rows)
