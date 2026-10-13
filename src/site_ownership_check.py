"""Robustness: are the model villages' appliances typical of the islands?

Ownership comes from national samples of rural grid-connected households
(few survey households live on or near the islands). The censuses report
ownership of a few appliances for every household, down to the islands' own
areas, so they show whether the island areas sit above or below the national
rural average:

  Rwanda  Nkombo sector against rural Rwanda, 2022 census
          (NISR 2023, Rusizi district profile, Table 4.13; NISR, RPHC5
          thematic report on households and housing, Figures 9.1 and 9.4:
          rural values are given as "about").
  Kenya   Suba North sub-county (Ringiti's sub-county in 2019) against rural
          Kenya, 2019 census (KNBS, 2019 KPHC Volume IV, Table 2.36).

The check scales each matching appliance's ownership by the island-area to
national-rural ratio (capped at 100%), leaves the rest unchanged, and reruns
the headline numbers. Census shares cover all households, grid-connected or
not, so the ratio, not the level, is carried over.

    python src/pipeline.py site_check   ->  results/site_ownership_check.csv
"""
import copy

import pandas as pd

from final_cfg import country_cfg
from kenya_ownership_check import headline_for

CENSUS = {
    "rwanda": {"site": "Nkombo sector", "reference": "rural Rwanda", "year": 2022,
               "shares": {"radio": (83.5, 77.0), "television": (7.8, 5.0),
                          "mobile phone": (82.8, 73.0)}},
    "kenya": {"site": "Suba North sub-county", "reference": "rural Kenya", "year": 2019,
              "shares": {"radio": (61.2, 58.5), "television": (27.8, 26.9),
                         "refrigerator": (3.1, 2.4)}},
}
APPLIANCES = {"radio": ("radio", "radio_cd_system"),
              "television": ("tv_colour", "tv_flat", "tv_bw"),
              "mobile phone": ("mobile_charger", "smartphone_charger"),
              "refrigerator": ("refrigerator",)}


def ratios(site):
    return {item: island / national
            for item, (island, national) in CENSUS[site]["shares"].items()}


def scaled_appliances(appliances, site):
    out = copy.deepcopy(appliances)
    for item, r in ratios(site).items():
        for name in APPLIANCES[item]:
            if name in out:
                spec = list(out[name])
                spec[0] = min(1.0, spec[0] * r)
                out[name] = tuple(spec)
    return out


def compare(resources, n_households=300, connections=300, seed=42):
    rows = []
    for site, res in resources.items():
        base = country_cfg(site)
        island = copy.deepcopy(base)
        island["appliances"] = scaled_appliances(base["appliances"], site)
        a = headline_for(base, res, n_households, connections, seed)
        b = headline_for(island, res, n_households, connections, seed)
        for q in a:
            rows.append({"site": site, "quantity": q, "national": a[q], "island": b[q],
                         "change_pct": 100 * (b[q] / a[q] - 1) if a[q] else None})
        for item, r in ratios(site).items():
            rows.append({"site": site, "quantity": f"census_ratio_{item.replace(' ', '_')}",
                         "national": CENSUS[site]["shares"][item][1],
                         "island": CENSUS[site]["shares"][item][0], "change_pct": 100 * (r - 1)})
    return pd.DataFrame(rows)
