"""Household load construction: RAMP for appliances, bespoke module for cooking.

Two builders, deliberately separate:

  build_noncooking_load()  - RAMP stochastic appliance model, parameterised from
                             MTF ownership rates for rural households WITH grid
                             access (the post-connection appliance set, not the
                             current off-grid one).

  build_cooking_load()     - meal events anchored to the MEASURED daypart split
                             from the Kenya MTF cooking module, timed about
                             mealtime centres, with a shiftable fraction phi
                             moving evening cooking into the afternoon.

Diversity is emergent: households are drawn independently and summed. Never
scale a single average profile by N.

PHASE 1 (integrity) changes to the cooking builder
--------------------------------------------------
s3.8 of the manuscript says event timing was re-specified as "normally
distributed about observed mealtime centres, with the spread calibrated against
the Kenyan diversity factor", giving DF 9.60 and a 104 W/household peak. The
v4 notebook did not contain that model: it drew the start hour UNIFORMLY within
each daypart, which is exactly the "flat load plateau" s3.8 says was replaced.
Measured on v4 at N=300, seed 42: DF 15.0, peak 67 W/household, plateau from
05:00-16:00. The code now does what the paper says. The spread is calibrated by
`validate_cooking.calibrate_timing_sd()`; the value used is recorded in
CookingParams.timing_sd_h with the DF it achieves.

Events are now resolved at minute resolution and averaged to hours, rather than
snapped to the top of the hour, and the builder is vectorised (~50x faster),
which is what makes the 20-seed ensembles in Phase 2 affordable.
"""
import contextlib
import io
import random
from dataclasses import dataclass, field

import numpy as np

HOURS = 8760
MINUTES = HOURS * 60

# Measured, Kenya MTF, rural households without grid access (n=1,771).
# Minutes/household/day: morning 49.5, afternoon 59.5, evening 71.1.
# Reproduced from the microdata by src/extract_mtf.py (unweighted, as published).
MEASURED_DAYPART = {"morning": 0.275, "afternoon": 0.330, "evening": 0.395}

# Daypart windows (local solar time), inclusive start, exclusive end.
DAYPART_WINDOWS = {"morning": (5, 10), "afternoon": (10, 16), "evening": (16, 22)}
_PARTS = ("morning", "afternoon", "evening")


@dataclass
class CookingParams:
    meals_per_day: float = 2.5
    kwh_per_meal_mean: float = 0.35
    kwh_per_meal_cv: float = 0.43          # sd/mean from MECS diaries
    epc_power_kw: float = 1.0
    min_event_minutes: int = 20
    # Mealtime centres, hours local solar time. Supper centre placed so the
    # modelled peak falls at 20:00, inside the MECS-observed 19:00-21:00
    # supper window (a 19:45 centre puts it in the 19:00 hour instead).
    mealtime_centres_h: dict = field(default_factory=lambda: {
        "morning": 7.0, "afternoon": 13.0, "evening": 20.0})
    # CALIBRATED by validate_cooking.calibrate_timing_sd() to the MECS Kenya
    # diversity factor of 9.75 (average-profile basis), N=300, seeds 0-9.
    # Achieved: DF 9.76, worst-hour DF 7.41, peak 20:00, 102 W/household,
    # 1.00 kWh/household/day. s3.8 reported 9.60 / 7.10 / 20:00 / 104 W.
    timing_sd_h: float = 1.716
    # Where a SHIFTED evening meal goes. An EPC retains heat for ~5 h, so a
    # supper cooked in the afternoon is cooked late in it, not at lunch.
    # ASSUMPTION - stated in s3.3. Moving it to 13:00 would stack shifted
    # suppers on the lunch peak and overstate the peak effect.
    shifted_centre_h: float = 15.0
    shifted_window: tuple = (14, 16)
    thermal_retention_hours: int = 5       # bounds how far a meal can shift


def _truncated_normal(rng, centre, sd, lo, hi):
    """Normal draws resampled until inside [lo, hi). Vectorised."""
    x = centre + rng.normal(0.0, sd, size=centre.shape)
    bad = (x < lo) | (x >= hi)
    while bad.any():
        x[bad] = centre[bad] + rng.normal(0.0, sd, size=int(bad.sum()))
        bad = (x < lo) | (x >= hi)
    return x


def build_cooking_load(n_households, penetration, phi, params=None,
                       seed=42, days=365, return_household_monthly=False):
    """Aggregate electric cooking load, kW per hour, 8760 values.

    penetration : share of households owning an electric pressure cooker
    phi         : share of *evening* cooking events shifted into the afternoon,
                  above the measured baseline. phi=0 reproduces the survey split.

    With return_household_monthly=True also returns an (n_cook, 12) array of
    each cooking household's monthly cooking kWh, for the household-level band
    check (Phase 3).
    """
    p = params or CookingParams()
    rng = np.random.default_rng(seed)
    n_cook = int(round(n_households * penetration))
    if n_cook == 0:
        z = np.zeros(HOURS)
        return (z, np.zeros((0, 12))) if return_household_monthly else z

    shape = 1.0 / (p.kwh_per_meal_cv ** 2)
    scale = p.kwh_per_meal_mean / shape
    base_probs = np.array([MEASURED_DAYPART[d] for d in _PARTS])

    n_meals = rng.poisson(p.meals_per_day, size=(days, n_cook))
    total = int(n_meals.sum())
    day = np.repeat(np.repeat(np.arange(days), n_cook), n_meals.ravel())
    hh = np.repeat(np.tile(np.arange(n_cook), days), n_meals.ravel())

    part = rng.choice(3, size=total, p=base_probs)
    shifted = (part == 2) & (rng.random(total) < phi)
    part = np.where(shifted, 1, part)
    # Energy is drawn BEFORE timing: the truncated-normal resampler consumes a
    # phi-dependent number of draws, and drawing energy after it would make
    # total cooking energy depend on phi. Shifting moves energy, never makes it.
    energy = rng.gamma(shape, scale, size=total)

    centres = np.array([p.mealtime_centres_h[d] for d in _PARTS])
    lo = np.array([DAYPART_WINDOWS[d][0] for d in _PARTS], float)[part]
    hi = np.array([DAYPART_WINDOWS[d][1] for d in _PARTS], float)[part]
    c = centres[part].astype(float)
    c[shifted] = p.shifted_centre_h
    lo[shifted], hi[shifted] = p.shifted_window
    start_h = _truncated_normal(rng, c, p.timing_sd_h, lo, hi)
    dur_min = np.maximum(np.rint(energy / p.epc_power_kw * 60),
                         p.min_event_minutes).astype(np.int64)

    start = day.astype(np.int64) * 1440 + np.rint(start_h * 60).astype(np.int64)
    end = np.minimum(start + dur_min, MINUTES)
    keep = start < MINUTES
    start, end = start[keep], end[keep]

    diff = np.zeros(MINUTES + 1)
    np.add.at(diff, start, p.epc_power_kw)
    np.add.at(diff, end, -p.epc_power_kw)
    minute_kw = np.cumsum(diff)[:MINUTES]
    load = minute_kw.reshape(HOURS, 60).mean(axis=1)

    if not return_household_monthly:
        return load
    month_of_day = np.repeat(np.arange(12), (31, 28, 31, 30, 31, 30,
                                             31, 31, 30, 31, 30, 31))[:days]
    kwh = (end - start) / 60.0 * p.epc_power_kw
    hh_month = np.zeros((n_cook, 12))
    np.add.at(hh_month, (hh[keep], month_of_day[day[keep]]), kwh)
    return load, hh_month


def cooking_daypart_shares(load):
    """Energy share by daypart - the validation check against the survey."""
    hours = np.arange(len(load)) % 24
    out = {}
    for name, (lo, hi) in DAYPART_WINDOWS.items():
        out[name] = float(load[(hours >= lo) & (hours < hi)].sum())
    total = sum(out.values())
    return {k: v / total for k, v in out.items()} if total else out


def diversity_factor(load, n_cooking, rating_kw=1.0, definition="mecs"):
    """Diversity factor, as MECS define it unless told otherwise.

    mecs        theoretical maximum (n x rating) / peak of the AVERAGE daily
                profile. This is the definition s3.8 reports.
    worst_hour  theoretical maximum / single worst hour of the year.
    """
    if n_cooking <= 0:
        return np.nan
    peak = (load.reshape(-1, 24).mean(axis=0).max() if definition == "mecs"
            else load.max())
    return n_cooking * rating_kw / peak


# ------------------------------------------------------------------ RAMP part
_RAMP_CACHE = {}


def _ownership_key(ownership):
    return tuple(sorted((k, tuple(v)) for k, v in ownership.items()))


def build_noncooking_load(ownership, n_households, mean_power_w=None,
                          seed=42, days=365):
    """RAMP-based appliance load. `ownership` maps appliance -> (rate, watts,
    daily_minutes, window). Returns kW per hour, 8760 values.

    SEEDING. RAMP 0.5.0 draws exclusively from the *stdlib* `random` module
    (ramp/core/core.py uses random.uniform, random.gauss, random.randint;
    there is not a single np.random call in the package). Seeding numpy does
    NOT make this function reproducible - it must be `random.seed`.

    The global `random` state is saved and restored around the call, so
    building a load does not silently reseed anything else in the process.

    Results are memoised on (ownership, n_households, seed): RAMP is the
    slowest step, and every scenario in a sweep uses the same appliance load.
    A copy is returned so callers cannot corrupt the cache.

    `mean_power_w` is unused and kept only for call compatibility with v3/v4.
    """
    key = (_ownership_key(ownership), int(n_households), seed)
    if key in _RAMP_CACHE:
        return _RAMP_CACHE[key].copy()

    from ramp import User, UseCase

    def _win(spec):
        """'18:00-23:00' -> [1080, 1380] minutes of day, as RAMP expects."""
        a, b = spec.split("-")
        to_min = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
        return np.array([to_min(a), min(to_min(b), 1439)])

    state = random.getstate()
    try:
        random.seed(seed)
        users = []
        for name, (rate, watts, minutes, window) in ownership.items():
            n = int(round(n_households * rate))
            if n == 0:
                continue
            u = User(user_name=name, num_users=n)
            app = u.add_appliance(number=1, power=watts, num_windows=1,
                                  func_time=minutes,
                                  time_fraction_random_variability=0.2,
                                  func_cycle=10, name=name)
            app.windows(window_1=_win(window), random_var_w=0.2)
            users.append(u)

        # date_start/date_end already initialises the use case; do not call
        # initialize() again or RAMP warns about re-initialisation.
        with contextlib.redirect_stdout(io.StringIO()):
            uc = UseCase(users=users, date_start="2026-01-01",
                         date_end="2026-01-07")
            prof = uc.generate_daily_load_profiles()      # minute, W
    finally:
        random.setstate(state)

    arr = np.asarray(prof).flatten()
    hourly = arr.reshape(-1, 60).mean(axis=1) / 1000.0   # kW
    # Seven representative days tiled across the year. Defensible within a
    # degree of the equator, where seasonality in household routine is weak,
    # but state it as a simplification in the method section.
    reps = int(np.ceil(HOURS / len(hourly)))
    out = np.tile(hourly, reps)[:HOURS]
    _RAMP_CACHE[key] = out
    return out.copy()


def household_noncooking_monthly(ownership, n_households, seed=42):
    """(n_households, 12) monthly non-cooking kWh, one row per household.

    RAMP aggregates users by appliance type and cannot attribute load to an
    individual household, so the household-level band check (Phase 3) draws
    each household's appliance set by independent Bernoulli trials on the MTF
    ownership rates and charges it rated power x daily minutes. This matches
    RAMP in expectation. Ownership correlation between appliances is ignored,
    which UNDERSTATES dispersion (TV owners are likelier to own lights) - so
    the band-assignment error it reveals is a lower bound.
    """
    rng = np.random.default_rng(seed)
    days = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    daily = np.zeros(n_households)
    for _, (rate, watts, minutes, _w) in sorted(ownership.items()):
        owns = rng.random(n_households) < rate
        daily += owns * watts * minutes / 60.0 / 1000.0
    return daily[:, None] * days[None, :]
