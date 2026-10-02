"""Tests for option (a): both countries' appliances derived from their own MTF.

These run against synthetic surveys shaped like the documented schemas, so the
extraction path is verified before it ever touches the microdata.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import mtf_appliances as M  # noqa: E402


@pytest.fixture(scope="module")
def surveys(tmp_path_factory):
    """Synthetic SECTION_EF1 / SECTION_C1 and Kenya M3 / core."""
    rng = np.random.default_rng(0)
    root = tmp_path_factory.mktemp("mtf")
    rw, ke = root / "rw", root / "ke"
    rw.mkdir(); ke.mkdir()

    n = 1500
    hhid = [f"h{i:05d}" for i in range(n)]
    rural = rng.random(n) < 0.7
    grid = rng.random(n) < 0.51
    d = {"hhid": hhid, "HH_WT": rng.uniform(0.5, 2, n), "camp": [None] * n,
         "HI04": np.where(rural, 2, 1)}   # real file is numeric: 1=Urban, 2=Rural
    spec = {"E29": (0.75, 2.0), "E03": (0.55, 4.5), "E06": (0.40, 3.0),
            "E31": (0.10, 3.5), "E01": (0.22, 4.0), "E10": (0.04, 20.0)}
    for pre, (base, hrs) in spec.items():
        own = rng.random(n) < np.where(grid, base, base * 0.35)
        d[pre + "A"] = own.astype(int)
        d[pre + "B"] = np.where(own, "Yes", "No")
        if pre == "E29":
            continue                       # no hours variable, as in the real file
        h = np.where(own, np.clip(rng.normal(hrs, 1, n), 0.5, 16), np.nan)
        h[rng.random(n) < 0.05] = 888      # "don't know" sentinel
        d[pre + "C"] = h
    pd.DataFrame(d).to_csv(rw / "SECTION_EF1.csv", index=False)
    pd.DataFrame({"hhid": hhid, "HH_WT": d["HH_WT"],
                  "C002": grid.astype(int)}).to_csv(rw / "SECTION_C1.csv",
                                                    index=False)

    m = 1200
    pk = [f"k{i:05d}" for i in range(m)]
    gl = rng.choice(["Rural with grid access", "Rural without grid access"],
                    m, p=[.45, .55])
    pd.DataFrame({"PARENT_KEY": pk, "grid_loc": gl}).to_csv(
        ke / "MTF_HH_Core_Survey_Final_Data_trimmed-2.csv",
        index=False, encoding="latin-1")
    sub = rng.random(m) < 0.55
    k = {"PARENT_KEY": [p for p, s in zip(pk, sub) if s]}
    for c, p in {"asset_bulb": .13, "asset_cfl": .09, "asset_radio": .30,
                 "asset_tv": .15, "asset_fridge": .02,
                 "asset_charger": .32}.items():
        k[c] = np.where(rng.random(int(sub.sum())) < p * 1.8, "Yes", "No")
    pd.DataFrame(k).to_csv(ke / "MTF_HH_Sec.M3_Asset_Data_Final.csv",
                           index=False)
    return rw, ke


# ------------------------------------------------------------- extraction
def test_hi04_is_treated_as_numeric(surveys):
    """The distributed file codes HI04 as 1=Urban, 2=Rural, not as the strings
    the variable label implies. Filtering on "Rural" silently drops everything."""
    rw, _ = surveys
    df = M.rwanda_ownership(rw, urban_rural="rural", access_var="C002")
    assert not df.empty
    urban = M.rwanda_ownership(rw, urban_rural="urban", access_var="C002")
    assert not urban.empty
    assert not df.ownership_rate.equals(urban.ownership_rate)


def test_rwanda_reads_the_appliance_section(surveys):
    rw, _ = surveys
    df = M.rwanda_ownership(rw, access_var="C002")
    assert not df.empty
    assert set(df.appliance) <= set(M.RWANDA_VARS)
    assert df.ownership_rate.between(0, 1).all()


def test_grid_access_filter_actually_binds(surveys):
    """s3.2 says parameters come from households WITH access. Verify the
    filter changes the answer rather than silently doing nothing."""
    rw, _ = surveys
    unfiltered = M.rwanda_ownership(rw).set_index("appliance").ownership_rate
    filtered = M.rwanda_ownership(rw, access_var="C002") \
                .set_index("appliance").ownership_rate
    assert filtered["mobile_charger"] > unfiltered["mobile_charger"] + 0.05


def test_dont_know_sentinel_is_excluded(surveys):
    """888 means 'don't know'. Averaging it in inflates duration ~50x."""
    rw, _ = surveys
    df = M.rwanda_ownership(rw, access_var="C002").set_index("appliance")
    assert df.measured_minutes.dropna().max() <= 24 * 60


def test_appliances_without_an_hours_variable_return_none(surveys):
    rw, _ = surveys
    df = M.rwanda_ownership(rw, access_var="C002").set_index("appliance")
    assert pd.isna(df.measured_minutes["mobile_charger"])


def test_kenya_uses_the_full_household_denominator(surveys):
    """M3 covers a subset of households. Absence must count as non-ownership,
    not be dropped, or ownership is overstated."""
    _, ke = surveys
    df = M.kenya_ownership(ke)
    assert (df.n_in_asset_file < df.n_households).all()
    assert df.ownership_rate.between(0, 1).all()


# --------------------------------------------------------------- symmetry
def test_countries_do_not_share_an_appliance_set(surveys):
    """The v3 bug: Rwanda inheriting Kenya's appliances."""
    rw, ke = surveys
    a = M.to_ramp_dict(M.rwanda_ownership(rw, access_var="C002"))
    b = M.to_ramp_dict(M.kenya_ownership(ke))
    assert a != b


def test_assumed_durations_are_identical_across_countries(surveys):
    """Headline specification. Only ownership, resource and tariff may differ,
    or s4's 'the difference reduces largely to the tariff regime' fails."""
    rw, ke = surveys
    a = M.to_ramp_dict(M.rwanda_ownership(rw, access_var="C002"), "assumed")
    b = M.to_ramp_dict(M.kenya_ownership(ke), "assumed")
    for name in set(a) & set(b):
        assert a[name][1] == b[name][1], f"{name}: wattage differs"
        assert a[name][2] == b[name][2], f"{name}: duration differs"
        assert a[name][3] == b[name][3], f"{name}: use window differs"


def test_measured_durations_only_move_rwanda(surveys):
    """The robustness specification, and why it must be reported separately."""
    rw, ke = surveys
    df = M.rwanda_ownership(rw, access_var="C002")
    a = M.to_ramp_dict(df, "assumed")
    m = M.to_ramp_dict(df, "measured")
    assert any(a[k][2] != m[k][2] for k in a), "measured switch did nothing"
    kd = M.kenya_ownership(ke)
    assert M.to_ramp_dict(kd, "assumed") == M.to_ramp_dict(kd, "measured")


def test_nan_durations_do_not_crash_the_emitter(surveys):
    """NaN survives the DataFrame round-trip and is truthy."""
    rw, _ = surveys
    d = M.to_ramp_dict(M.rwanda_ownership(rw, access_var="C002"), "measured")
    assert all(isinstance(v[2], int) and v[2] > 0 for v in d.values())


# -------------------------------------------------------------- plumbing
def test_emitted_dict_is_valid_ramp_input(surveys):
    rw, _ = surveys
    d = M.to_ramp_dict(M.rwanda_ownership(rw, access_var="C002"))
    for name, (rate, watts, minutes, window) in d.items():
        assert 0 < rate <= 1 and watts > 0 and 0 < minutes <= 1440
        a, b = window.split("-")
        assert int(a[:2]) < 24 and int(b[:2]) <= 24


def test_emitted_python_round_trips(surveys):
    rw, _ = surveys
    d = M.to_ramp_dict(M.rwanda_ownership(rw, access_var="C002"))
    ns = {}
    exec(M.emit_python("APPLIANCES_RWANDA", d), {}, ns)
    assert ns["APPLIANCES_RWANDA"] == d


def test_access_scan_surfaces_the_right_variable(surveys):
    rw, _ = surveys
    got = M.scan_access_candidates(rw / "SECTION_C1.csv")
    assert got.iloc[0].variable == "C002"
    assert abs(got.iloc[0].weighted_share_yes - 0.51) < 0.05


def test_every_emitted_appliance_has_a_wattage_and_window():
    for name in set(M.RWANDA_VARS) | set(M.KENYA_VARS):
        assert name in M.WATTS, f"{name} has no wattage"
        assert name in M.WINDOWS, f"{name} has no use window"
        assert name in M.DEFAULT_MINUTES, f"{name} has no fallback duration"


# ------------------------------------------- grid_loc representation (fetch)
def test_grid_loc_accepts_stata_codes_as_well_as_labels(tmp_path):
    """MTF_HH_Core_Survey .dta carries duplicate value labels, so pandas
    refuses convert_categoricals=True and falls back to numeric codes. A
    label-only filter then matches nothing and every rate returns NaN through
    a silent divide-by-zero. Both representations must work."""
    import mtf_appliances as MM
    for rep, val in (("labels", "Rural with grid access"), ("codes", 3)):
        d = tmp_path / rep; d.mkdir()
        pd.DataFrame({"PARENT_KEY": ["a", "b", "c"],
                      "grid_loc": [val, val, 99 if rep == "codes" else "Urban with grid access"]
                      }).to_csv(d / "MTF_HH_Core_Survey_Final_Data_trimmed-2.csv",
                                index=False, encoding="latin-1")
        pd.DataFrame({"PARENT_KEY": ["a", "b"],
                      "asset_tv": ["Yes", "No"]}).to_csv(
            d / "MTF_HH_Sec.M3_Asset_Data_Final.csv", index=False)
        got = MM.kenya_ownership(d).set_index("appliance").ownership_rate
        assert got["tv_colour"] == pytest.approx(0.5), f"{rep} representation failed"


def test_unmatched_grid_loc_raises_instead_of_returning_nan(tmp_path):
    import mtf_appliances as MM
    pd.DataFrame({"PARENT_KEY": ["a"], "grid_loc": ["something else"]}).to_csv(
        tmp_path / "MTF_HH_Core_Survey_Final_Data_trimmed-2.csv",
        index=False, encoding="latin-1")
    pd.DataFrame({"PARENT_KEY": ["a"], "asset_tv": ["Yes"]}).to_csv(
        tmp_path / "MTF_HH_Sec.M3_Asset_Data_Final.csv", index=False)
    with pytest.raises(ValueError, match="matched no households"):
        MM.kenya_ownership(tmp_path)


def test_kenya_mapping_matches_the_questionnaire():
    """Codebook_KENYA.xlsx shifts four labels up by one row. The variable
    NAMES are correct; verified against Section M, items M.15-M.40."""
    import mtf_appliances as MM
    assert MM.KENYA_VARS["radio"] == "asset_radio"          # M.20, not a torch
    assert MM.KENYA_VARS["kettle"] == "asset_ekettle"       # M.33, not a computer
    assert MM.KENYA_VARS["tv_colour"] == "asset_tv"         # M.37, not B/W
    assert MM.KENYA_VARS["tv_flat"] == "asset_flatv"        # M.38
    assert MM.KENYA_VARS["tv_bw"] == "asset_bwtv"           # M.36
