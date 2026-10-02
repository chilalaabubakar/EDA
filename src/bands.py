"""Blended tariff at the consumption the model actually simulates (Table 5).

The submitted Table 5 and abstract evaluate the band schedules at 15 and
60 kWh/month, chosen by hand as "approximately the transition implied by
adopting electric cooking". The model never produced those levels. Phase 1
recomputes the adoption penalty at the simulated mean household consumption,
per country (each on its OWN MTF appliance set - the v4 notebook cell used
Kenya's for both) and by project year, since 5%/yr demand growth moves
households across band edges over the project life.

The illustrative 15 -> 60 row is kept, labelled as such, so the change is
visible.
"""
import pandas as pd

from final_cfg import country_cfg
from model import _band_rate
from run_scenarios import make_load_builder

YEARS = (1, 5, 10, 20)


def monthly_kwh_per_household(builder, year, n_households):
    return float(builder(year).sum() / n_households / 12.0)


def blended_rate_table(sites=("rwanda", "kenya"), n_households=300, seed=42,
                       years=YEARS, phi=0.0):
    rows = []
    for site in sites:
        cfg = country_cfg(site)
        t = cfg["tariff"]
        rows.append({"site": site, "basis": "illustrative", "year": None,
                     "kwh_no_ecooking": 15.0, "kwh_full_ecooking": 60.0,
                     "rate_no_ecooking": _band_rate(15, t),
                     "rate_full_ecooking": _band_rate(60, t)})
        b0 = make_load_builder(cfg, n_households, 0.0, 0.0, seed)
        b1 = make_load_builder(cfg, n_households, 1.0, phi, seed)
        for y in years:
            a = monthly_kwh_per_household(b0, y, n_households)
            b = monthly_kwh_per_household(b1, y, n_households)
            rows.append({"site": site, "basis": "simulated", "year": y,
                         "kwh_no_ecooking": a, "kwh_full_ecooking": b,
                         "rate_no_ecooking": _band_rate(a, t),
                         "rate_full_ecooking": _band_rate(b, t)})
    df = pd.DataFrame(rows)
    df["factor"] = df.rate_full_ecooking / df.rate_no_ecooking
    return df


if __name__ == "__main__":
    print(blended_rate_table().round(4).to_string(index=False))
