"""Household load construction: RAMP for appliances, bespoke module for cooking.

Two builders, deliberately separate:

  build_noncooking_load()  - RAMP stochastic appliance model, parameterised from
                             MTF ownership rates for rural households WITH grid
                             access (the post-connection appliance set, not the
                             current off-grid one).

  build_cooking_load()     - meal events anchored to the MEASURED daypart split
                             from the Kenya MTF cooking module, with a shiftable
                             fraction phi moving evening cooking into the
                             afternoon window.

Diversity is emergent: households are drawn independently and summed. Never
scale a single average profile by N.
"""
from dataclasses import dataclass

import numpy as np

HOURS = 8760

# Measured, Kenya MTF, rural households without grid access (n=1,771).
# Minutes/household/day: morning 49.5, afternoon 59.5, evening 71.1.
MEASURED_DAYPART = {"morning": 0.275, "afternoon": 0.330, "evening": 0.395}

# Daypart windows (local solar time), inclusive start, exclusive end.
DAYPART_WINDOWS = {"morning": (5, 10), "afternoon": (10, 16), "evening": (16, 22)}


@dataclass
class CookingParams:
    meals_per_day: float = 2.5
    kwh_per_meal_mean: float = 0.35
    kwh_per_meal_cv: float = 0.43          # sd/mean from MECS diaries
    epc_power_kw: float = 1.0
    min_event_minutes: int = 20
    thermal_retention_hours: int = 5       # bounds how far a meal can shift


def _hour_pool(window):
    lo, hi = DAYPART_WINDOWS[window]
    return np.arange(lo, hi)


def build_cooking_load(n_households, penetration, phi, params=None,
                       seed=42, days=365):
    """Aggregate electric cooking load, kW per hour, 8760 values.

    penetration : share of households owning an electric pressure cooker
    phi         : share of *evening* cooking events shifted into the afternoon,
                  above the measured baseline. phi=0 reproduces the survey split.
    """
    p = params or CookingParams()
    rng = np.random.default_rng(seed)
    n_cook = int(round(n_households * penetration))
    load = np.zeros(HOURS)
    if n_cook == 0:
        return load

    shape = 1.0 / (p.kwh_per_meal_cv ** 2)
    scale = p.kwh_per_meal_mean / shape

    dayparts = list(MEASURED_DAYPART)
    base_probs = np.array([MEASURED_DAYPART[d] for d in dayparts])

    for day in range(days):
        h0 = day * 24
        if h0 + 24 > HOURS:
            break
        for _ in range(n_cook):
            n_meals = rng.poisson(p.meals_per_day)
            if n_meals == 0:
                continue
            choice = rng.choice(len(dayparts), size=n_meals, p=base_probs)
            for c in choice:
                part = dayparts[c]
                # phi shifts evening events into the afternoon
                if part == "evening" and rng.random() < phi:
                    part = "afternoon"
                hour = rng.choice(_hour_pool(part))
                energy = rng.gamma(shape, scale)
                # spread the event over its physical duration
                dur_h = max(energy / p.epc_power_kw, p.min_event_minutes / 60)
                full = int(dur_h)
                for k in range(full):
                    if h0 + hour + k < HOURS:
                        load[h0 + hour + k] += p.epc_power_kw
                frac = dur_h - full
                if frac > 0 and h0 + hour + full < HOURS:
                    load[h0 + hour + full] += p.epc_power_kw * frac
    return load


def cooking_daypart_shares(load):
    """Energy share by daypart - the validation check against the survey."""
    hours = np.arange(len(load)) % 24
    out = {}
    for name, (lo, hi) in DAYPART_WINDOWS.items():
        out[name] = float(load[(hours >= lo) & (hours < hi)].sum())
    total = sum(out.values())
    return {k: v / total for k, v in out.items()} if total else out


def build_noncooking_load(ownership, n_households, mean_power_w,
                          seed=42, days=365):
    """RAMP-based appliance load. `ownership` maps appliance -> (rate, watts,
    daily_minutes, window). Returns kW per hour, 8760 values.

    SEEDING. RAMP 0.5.0 draws exclusively from the *stdlib* `random` module
    (ramp/core/core.py uses random.uniform, random.gauss, random.randint;
    there is not a single np.random call in the package). Seeding numpy does
    NOT make this function reproducible - it must be `random.seed`.

    Before this was fixed, `seed` was accepted and silently ignored, so every
    call returned a different appliance profile. Annual energy moved by ~0.8%
    but the aggregate PEAK moved by up to 16% (5.89-6.83 kW over eight calls
    at N=300), and peak is what sets battery capacity. That is the true source
    of the +/-20 kWh differences between matched flat and ToU arms previously
    attributed to the discrete sizing grid.
    """
    import random

    from ramp import User, UseCase

    random.seed(seed)

    def _win(spec):
        """'18:00-23:00' -> [1080, 1380] minutes of day, as RAMP expects."""
        a, b = spec.split("-")
        to_min = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
        return np.array([to_min(a), min(to_min(b), 1439)])

    users = []
    for name, (rate, watts, minutes, window) in ownership.items():
        n = int(round(n_households * rate))
        if n == 0:
            continue
        u = User(user_name=name, num_users=n)
        app = u.add_appliance(number=1, power=watts, num_windows=1,
                              func_time=minutes, time_fraction_random_variability=0.2,
                              func_cycle=10, name=name)
        app.windows(window_1=_win(window), random_var_w=0.2)
        users.append(u)

    # date_start/date_end already initialises the use case; do not call
    # initialize() again or RAMP warns about re-initialisation.
    uc = UseCase(users=users, date_start="2026-01-01", date_end="2026-01-07")
    prof = uc.generate_daily_load_profiles()          # minute resolution, W
    arr = np.asarray(prof).flatten()
    hourly = arr.reshape(-1, 60).mean(axis=1) / 1000.0   # kW
    # Seven representative days tiled across the year. Defensible within a
    # degree of the equator, where seasonality in household routine is weak,
    # but state it as a simplification in the method section.
    reps = int(np.ceil(HOURS / len(hourly)))
    return np.tile(hourly, reps)[:HOURS]
