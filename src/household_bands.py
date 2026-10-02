"""Phase 3: does assigning bands from the MEAN household bias revenue and the
adoption penalty?

tariff_revenue() applies each month's band to the mean household's
consumption. Under a non-linear schedule that is not the same as billing every
household on its own consumption (Jensen's inequality): Rwanda's telescopic
schedule is convex, so mean-household billing UNDERSTATES revenue; Kenya's
non-telescopic steps are neither convex nor concave, so the sign is an
empirical question.

Household consumption = non-cooking (household_noncooking_monthly: Bernoulli
draws on MTF ownership, rescaled so the village total equals the RAMP
aggregate) + cooking (each cooking household's own simulated events).
Ownership correlation is ignored, which understates dispersion, so the bias
reported here is a lower bound.
"""
import numpy as np
import pandas as pd

from load_builder import build_cooking_load, household_noncooking_monthly
from model import MONTH_EDGES, _band_rate
from run_scenarios import make_load_builder


def bill(kwh, t):
    return _band_rate(kwh, t) * kwh


def household_monthly(cfg, n, penetration, phi, seed):
    """(n, 12) kWh per household per month in year 1."""
    b = make_load_builder(cfg, n, penetration, phi, seed)
    agg_month = np.array([b.noncooking[a:z].sum() for a, z in
                          zip(MONTH_EDGES[:-1], MONTH_EDGES[1:])])
    nc = household_noncooking_monthly(cfg["appliances"], n, seed)
    nc *= (agg_month / nc.sum(axis=0).clip(min=1e-12))[None, :]
    _, cook = build_cooking_load(n, penetration, phi, seed=seed,
                                 return_household_monthly=True)
    hh = nc.copy()
    hh[:len(cook)] += cook               # cooking households are the first n_cook
    return hh


def check(cfg, n=300, penetration=1.0, phi=0.0, seed=42, years=(1, 10, 20)):
    t = cfg["tariff"]
    g = cfg["demand"]["annual_growth_rate"]
    base = household_monthly(cfg, n, penetration, phi, seed)
    rows = []
    for y in years:
        hh = base * (1 + g) ** (y - 1)
        mean = hh.mean(axis=0)
        rev_hh = sum(bill(k, t) for k in hh.ravel())
        rev_mean = sum(n * bill(k, t) for k in mean)
        annual = hh.sum(axis=1)
        # households with no consumption have no blended rate; exclude them
        rate_hh = np.array([sum(bill(k, t) for k in row) / row.sum()
                            for row in hh if row.sum() > 0])
        rows.append({
            "year": y, "penetration": penetration,
            "mean_kwh_month": float(mean.mean()),
            "p10_kwh_month": float(np.percentile(annual / 12, 10)),
            "p90_kwh_month": float(np.percentile(annual / 12, 90)),
            "revenue_household_billing": rev_hh,
            "revenue_mean_household": rev_mean,
            "bias_pct": 100 * (rev_mean / rev_hh - 1),
            "blended_rate_mean_hh": rev_mean / hh.sum(),
            "blended_rate_household_p10": float(np.percentile(rate_hh, 10)),
            "blended_rate_household_median": float(np.median(rate_hh)),
            "blended_rate_household_p90": float(np.percentile(rate_hh, 90)),
            "share_hh_months_above_lifeline": float((hh > t["bands"][0][0]).mean()),
            "share_hh_zero_consumption": float((annual == 0).mean()),
        })
    return pd.DataFrame(rows)


def adoption_penalty_distribution(cfg, n=300, seed=42, year=1):
    """Each household's blended-rate factor on adopting eCooking: its own
    non-cooking consumption, with and without its own cooking load."""
    t = cfg["tariff"]
    g = (1 + cfg["demand"]["annual_growth_rate"]) ** (year - 1)
    pre = household_monthly(cfg, n, 0.0, 0.0, seed) * g
    post = household_monthly(cfg, n, 1.0, 0.0, seed) * g
    rate = lambda m: sum(bill(k, t) for k in m) / max(m.sum(), 1e-12)
    f = np.array([rate(b) / rate(a) for a, b in zip(pre, post) if a.sum() > 0])
    mean_pre, mean_post = pre.mean(axis=0), post.mean(axis=0)
    return {"year": year, "factor_p10": float(np.percentile(f, 10)),
            "factor_median": float(np.median(f)),
            "factor_p90": float(np.percentile(f, 90)),
            "factor_mean_household": rate(mean_post) / rate(mean_pre)}
