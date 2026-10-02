"""Regression tests for the Phase 1 defects.

Each test fails against the code as submitted and passes against the fix.
They exist so the defects cannot silently return.
"""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from model import capex, financials, fixed_opex_year_one, simulate  # noqa: E402
from load_builder import build_noncooking_load  # noqa: E402
import final_cfg  # noqa: E402

APPLIANCES = final_cfg.APPLIANCES_KENYA


# ------------------------------------------------ defect 1: unseeded RAMP
def test_noncooking_load_is_reproducible():
    """RAMP 0.5.0 draws from the stdlib `random`, not np.random. Before the
    fix, `seed` was accepted and ignored: eight calls at seed=42 gave eight
    different profiles, with the aggregate PEAK ranging 5.89-6.83 kW at
    N=300. Peak sets battery capacity, so this is what produced the +/-20 kWh
    differences between matched flat and ToU arms.
    """
    a = build_noncooking_load(APPLIANCES, 300, None, seed=42)
    b = build_noncooking_load(APPLIANCES, 300, None, seed=42)
    assert np.array_equal(a, b), "same seed returned different appliance loads"


def test_noncooking_load_peak_is_reproducible():
    """Guard the statistic that actually drives sizing, not just the total."""
    peaks = {build_noncooking_load(APPLIANCES, 300, None, seed=42).max()
             for _ in range(3)}
    assert len(peaks) == 1, f"peak varied across identical calls: {peaks}"


def test_noncooking_load_still_varies_with_seed():
    """Seeding must not accidentally make the model deterministic in seed."""
    a = build_noncooking_load(APPLIANCES, 300, None, seed=42)
    b = build_noncooking_load(APPLIANCES, 300, None, seed=7)
    assert not np.array_equal(a, b)


def test_seeding_numpy_alone_is_not_sufficient():
    """Documents the trap: np.random.seed does not reach RAMP's RNG."""
    import random
    random.seed(1); a = build_noncooking_load(APPLIANCES, 120, None, seed=1)
    np.random.seed(1); random.seed(2)
    b = build_noncooking_load(APPLIANCES, 120, None, seed=2)
    assert not np.array_equal(a, b), (
        "if this passes, RAMP is being seeded by numpy and this test is stale")


# ------------------------------------------------- defect 2: OPEX basis
CFG = {
    "capex": {"pv_per_kw": 1228, "battery_per_kwh": 300, "diesel_per_kw": 700,
              "inverter_per_kw": 400, "connection_per_customer": 400,
              "soft_cost_fraction": 0.333},
    "bos": {"inverter_eff": 0.97, "dc_ac_ratio": 1.2},
    "opex": {"basis": "per_customer", "per_customer_year": 80.0,
             "om_fraction_of_capex_per_year": 0.04, "staff_annual": 6000,
             "escalation_rate": 0.05, "fuel_escalation_rate": 0.05,
             "fuel_cost_per_litre": 2.0},
    "finance": {"discount_rate_real": 0.12, "tax_rate": 0.0,
                "project_life_years": 20},
    "battery": {"replacement_year": 10},
}
SIZING = {"pv_kw": 305, "battery_kwh": 640, "diesel_kw": 0.0,
          "connections": 300, "households": 300}


def test_opex_basis_must_be_explicit():
    cfg = copy.deepcopy(CFG); cfg["opex"].pop("basis")
    with pytest.raises(KeyError):
        fixed_opex_year_one(cfg, SIZING, 1_000_000)


def test_per_customer_basis_is_actually_used():
    """per_customer_year was defined in the config and read nowhere."""
    assert fixed_opex_year_one(CFG, SIZING, 1_000_000) == pytest.approx(24_000)


def test_per_customer_opex_does_not_scale_with_plant_size():
    small = fixed_opex_year_one(CFG, SIZING, 283_200)
    large = fixed_opex_year_one(CFG, SIZING, 1_050_679)
    assert small == large


def test_capex_fraction_basis_still_available_for_reproduction():
    cfg = copy.deepcopy(CFG); cfg["opex"]["basis"] = "capex_fraction"
    assert fixed_opex_year_one(cfg, SIZING, 1_050_679) == pytest.approx(
        1_050_679 * 0.04 + 6000)


# ------------------------------- defect 3: grant must not cut operating cost
def test_capital_grant_does_not_reduce_operating_cost():
    """A donor paying for the plant does not make it cheaper to run.

    Previously OPEX was a fraction of POST-grant CAPEX, so a 95% grant cut
    operating cost by 95% and flattered the capital-subsidy solver.
    """
    cfg = copy.deepcopy(CFG); cfg["opex"]["basis"] = "capex_fraction"
    annual = [{"year": y, "revenue": 5e4, "fuel_l": 0.0, "served_kwh": 3e5,
               "unmet_kwh": 0.0, "demand_kwh": 3e5, "curtailed_kwh": 0.0}
              for y in range(1, 21)]

    gross, _ = capex(cfg, SIZING)
    granted = copy.deepcopy(cfg)
    granted["capex"] = {**cfg["capex"], "_grant_fraction": 0.95}
    net, items = capex(granted, SIZING)

    assert items["_gross_capex"] == pytest.approx(gross)
    a, _ = financials(annual, cfg, SIZING, gross, gross_capex=gross)
    b, _ = financials(annual, granted, SIZING, net, gross_capex=gross)
    assert a.fixed_opex.iloc[0] == pytest.approx(b.fixed_opex.iloc[0]), (
        "capital grant changed operating cost")


# --------------------------------- defect 4: Rwanda inherited Kenyan appliances
def test_both_countries_have_their_own_mtf_appliance_set():
    """Option (a) is done: each country carries its own MTF-derived set."""
    rw = final_cfg.country_cfg("rwanda")["appliances"]
    ke = final_cfg.country_cfg("kenya")["appliances"]
    assert rw and ke and rw != ke
    assert rw is not ke
    # Rwanda's stock is materially heavier - the finding that reverses s3.2.
    assert rw["mobile_charger"][0] > 5 * ke["mobile_charger"][0]


def test_config_still_refuses_a_missing_appliance_set(monkeypatch):
    monkeypatch.setitem(final_cfg.COUNTRY_OVERRIDES["rwanda"], "appliances", None)
    with pytest.raises(ValueError, match="no appliance set"):
        final_cfg.country_cfg("rwanda")


def test_config_refuses_a_shared_appliance_object(monkeypatch):
    shared = final_cfg.APPLIANCES_KENYA
    monkeypatch.setitem(final_cfg.COUNTRY_OVERRIDES["rwanda"], "appliances", shared)
    with pytest.raises(ValueError, match="sharing one appliance object"):
        final_cfg.country_cfg("rwanda")


def test_kenya_country_config_builds():
    cfg = final_cfg.country_cfg("kenya")
    assert cfg["appliances"] is final_cfg.APPLIANCES_KENYA
    assert cfg["tariff"]["telescopic"] is False


def test_measured_duration_variant_exists_and_differs():
    """The robustness specification must be available and must actually differ
    from the headline one, or reporting it as a sensitivity is vacuous."""
    a = final_cfg.APPLIANCES_RWANDA
    m = final_cfg.APPLIANCES_RWANDA_MEASURED
    assert set(a) == set(m)
    assert any(a[k][2] != m[k][2] for k in a), "measured durations identical"


# ------------------------------------- defect 5: diesel is declared, not default
def test_diesel_is_explicit_in_the_config():
    assert "diesel_kw" in final_cfg.BASE_CFG, (
        "diesel capacity must be stated, not left to a .get() default")


def test_published_results_are_solar_plus_storage_only():
    assert final_cfg.BASE_CFG["diesel_kw"] == 0.0, (
        "diesel is now non-zero: s3.4 and the fuel-price references become "
        "live and every published table must be re-run")


# ------------------------------------------------- curtailment is now reported
def test_curtailment_is_surfaced_in_metrics():
    """Computed hourly and then discarded. It is the physical justification
    for a daytime discount, so it has to reach the results table."""
    h = np.arange(8760) % 24
    ghi = np.clip(np.sin((h - 6) / 12 * np.pi), 0, None) * 950
    tair = 22 + 6 * np.clip(np.sin((h - 7) / 12 * np.pi), 0, None)
    cfg = copy.deepcopy(CFG)
    cfg.update({
        "pv": {"temp_coeff_per_c": -0.004, "noct_c": 45, "derate_factor": 0.85,
               "degradation_rate": 0.008},
        "battery": {"round_trip_efficiency": 0.90, "depth_of_discharge": 0.80,
                    "cycle_life": 3000, "replacement_year": 10,
                    "max_c_rate": 0.5},
        "tariff": {"flat_rate_per_kwh": 0.1466, "bands": None,
                   "telescopic": False, "daytime_discount_per_kwh": 0.0,
                   "daytime_window_hours": [9, 16], "collection_rate": 0.90},
    })
    load = lambda y: np.tile(np.full(24, 5.0), 365) * (1.05 ** (y - 1))
    _, m = simulate(cfg, SIZING, load, {"ghi": ghi, "tair": tair})
    assert "curtailed_fraction" in m
    assert 0.0 <= m["curtailed_fraction"] < 1.0
