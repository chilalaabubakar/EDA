"""Phase 1 exit test: the same command twice gives the same answer.

  * build_noncooking_load / full load builder: bit-identical for a seed
  * RAMP seeding does not leak into the caller's global `random` state
  * a sweep run twice writes byte-identical CSVs
  * identical scenarios return identical LCOE to four decimals
"""
import random

import numpy as np
import pandas as pd

import final_cfg
import load_builder
from solar_resource import synthetic_years
from run_scenarios import make_load_builder, run, scenario_row

RES = synthetic_years("rwanda")[2015]


def _small_cfg(site="rwanda"):
    cfg = final_cfg.country_cfg(site)
    cfg["scenarios"] = {"penetration_sweep": [0.5], "shiftable_fraction_sweep": [0.5],
                        "tariffs": ["flat", "tou"], "tou_daytime_discount_sweep": [0.0, 0.02]}
    cfg["sizing"] = {"pv_range": [10, 400], "battery_range": [0, 1200]}
    return cfg


def test_full_load_builder_bit_identical_across_fresh_calls():
    cfg = final_cfg.country_cfg("kenya")
    load_builder._RAMP_CACHE.clear()
    a = make_load_builder(cfg, 300, 1.0, 0.3, 42)(7)
    load_builder._RAMP_CACHE.clear()
    b = make_load_builder(cfg, 300, 1.0, 0.3, 42)(7)
    assert np.array_equal(a, b)


def test_ramp_seed_does_not_leak_into_global_random():
    random.seed(123); expected = random.random()
    random.seed(123)
    load_builder._RAMP_CACHE.clear()
    load_builder.build_noncooking_load(final_cfg.APPLIANCES_KENYA, 100, None, seed=9)
    assert random.random() == expected


def test_cache_returns_copies():
    a = load_builder.build_noncooking_load(final_cfg.APPLIANCES_KENYA, 100, None, seed=9)
    a[:] = -1
    b = load_builder.build_noncooking_load(final_cfg.APPLIANCES_KENYA, 100, None, seed=9)
    assert (b >= 0).all()


def test_identical_scenarios_identical_lcoe_to_four_decimals():
    cfg = _small_cfg()
    a = scenario_row(cfg, RES, 300, 300, 1.0, 0.5, "tou", 0.02, 42)
    load_builder._RAMP_CACHE.clear()
    b = scenario_row(cfg, RES, 300, 300, 1.0, 0.5, "tou", 0.02, 42)
    assert round(a["lcoe"], 4) == round(b["lcoe"], 4)
    assert a["battery_kwh"] == b["battery_kwh"] and a["pv_kw"] == b["pv_kw"]


def test_sweep_reruns_clean(tmp_path):
    cfg = _small_cfg()
    run(cfg, RES, 300, 300, tmp_path / "a.csv", verbose=False)
    load_builder._RAMP_CACHE.clear()
    run(cfg, RES, 300, 300, tmp_path / "b.csv", verbose=False)
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()


def test_zero_discount_tou_arm_equals_flat_arm():
    """No discount -> no shifting -> identical sizing. The +/-20 kWh leak
    previously blamed on the sizing grid came from unseeded RAMP."""
    cfg = _small_cfg()
    df = run(cfg, RES, 300, 300, verbose=False)
    flat = df[df.tariff == "flat"].iloc[0]
    tou0 = df[(df.tariff == "tou") & (df.discount == 0)].iloc[0]
    assert flat.battery_kwh == tou0.battery_kwh
    assert round(flat.lcoe, 4) == round(tou0.lcoe, 4)
