"""The cooking model must be the one s3.8 describes.

v4 drew meal start hours uniformly within dayparts, producing the flat
plateau s3.8 says was replaced. These tests pin the calibrated model.
"""
import numpy as np
import pytest

from load_builder import (CookingParams, MEASURED_DAYPART, build_cooking_load,
                          cooking_daypart_shares, diversity_factor)

N = 300


@pytest.fixture(scope="module")
def ensemble():
    return [build_cooking_load(N, 1.0, 0.0, seed=s) for s in range(5)]


def test_diversity_factor_is_calibrated_to_kenya(ensemble):
    df = np.mean([diversity_factor(L, N) for L in ensemble])
    assert 9.5 < df < 10.0, f"DF {df:.2f}; MECS Kenya 9.75"


def test_profile_has_three_peaks_not_a_plateau(ensemble):
    prof = np.mean([L.reshape(-1, 24).mean(0) for L in ensemble], axis=0)
    assert int(prof.argmax()) == 20, "supper peak must sit at 20:00"
    # three local maxima separated by troughs below half their height
    for a, b in ((5, 10), (10, 16), (16, 22)):
        peak = prof[a:b].max()
        assert prof[a:b].min() < 0.5 * peak, f"window {a}-{b} is a plateau"


def test_night_minimum(ensemble):
    prof = np.mean([L.reshape(-1, 24).mean(0) for L in ensemble], axis=0)
    # 22:00 still carries the tail of late suppers; 23:00-05:00 is empty.
    assert np.r_[prof[23:], prof[:5]].max() < 0.01 * prof.max()
    assert prof.argmin() in (22, 23, 0, 1, 2, 3, 4)


def test_measured_daypart_split_still_reproduced(ensemble):
    s = cooking_daypart_shares(ensemble[0])
    for part, target in MEASURED_DAYPART.items():
        assert s[part] == pytest.approx(target, abs=0.02)


def test_phi_conserves_energy_exactly():
    a = build_cooking_load(N, 1.0, 0.0, seed=3)
    b = build_cooking_load(N, 1.0, 0.5, seed=3)
    assert a.sum() == pytest.approx(b.sum(), rel=1e-12)


def test_shifting_raises_the_cooking_peak():
    """Phase 3 finding: shifting cuts storage but lifts the coincident peak."""
    a = build_cooking_load(N, 1.0, 0.0, seed=3)
    b = build_cooking_load(N, 1.0, 0.5, seed=3)
    assert b.max() > a.max()


def test_household_monthly_matches_aggregate():
    L, hm = build_cooking_load(N, 1.0, 0.3, seed=9, return_household_monthly=True)
    assert hm.shape == (N, 12)
    assert hm.sum() == pytest.approx(L.sum(), rel=1e-9)


def test_builder_is_fast():
    import time
    t = time.time()
    build_cooking_load(N, 1.0, 0.5, seed=1)
    assert time.time() - t < 2.0
