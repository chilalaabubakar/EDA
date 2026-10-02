"""Symmetric MTF appliance extraction for Rwanda and Kenya (option (a)).

WHAT THIS REPLACES
------------------
v3 set BASE_CFG["appliances"] once from a hand-typed Kenyan dict, and Rwanda
inherited it. This module derives BOTH countries' ownership rates from their
own MTF microdata, using the same method, and emits a paste-ready dict.

THE SYMMETRY PROBLEM, AND HOW IT IS HANDLED
-------------------------------------------
The two surveys are not equally rich:

  Rwanda  SECTION_EF1  counts (E**A), usage flags (E**B) AND daily usage
                       hours (E**C) for 12 appliances
  Kenya   M3_Asset     binary ownership flags only (asset_bulb, asset_cfl,
                       ...). No counts, no hours.

If Rwanda used measured durations and Kenya used assumed ones, part of the
cross-country difference would be an artefact of data richness, and s4's
claim that the two cases "reduce largely to the tariff and regulatory regime"
would fail. So durations are controlled by a switch:

  durations="assumed"   both countries use the shared DEFAULT_MINUTES table.
                        This is the HEADLINE specification: the only things
                        that differ between countries are the measured
                        ownership rates, the solar resource and the tariff.

  durations="measured"  Rwanda uses its MTF-recorded hours where available,
                        Kenya falls back to DEFAULT_MINUTES. Run this as a
                        ROBUSTNESS CHECK and report it as such.

Reporting both is what makes option (a) defensible. Reporting only
"measured" would confound the comparison.

WATTAGE is recorded by neither survey and is assumed in both. Use windows are
recorded by neither and are assumed in both, identically. So s3.2 should now
read: ownership measured, durations measured for Rwanda in the robustness
specification only, wattages and use windows assumed and held identical.

USAGE
-----
    python src/mtf_appliances.py --scan-access --rwanda data/raw/rwanda
    python src/mtf_appliances.py \
        --rwanda data/raw/rwanda \
        --kenya  data/raw/KEN_2016-2018_MTF_v02_M_CSV \
        --rwanda-access-var C002 --rwanda-access-value 1 \
        --durations assumed --out data/processed
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

YES = {"yes", "y", "1", "1.0", "true", "oui"}

# --------------------------------------------------------------- assumptions
# Wattage is not recorded in either survey. These are carried over from the v3
# notebook where they existed, extended where new appliances appear.
# ACTION BEFORE SUBMISSION: attach a citation to each. Efficiency for Access /
# CLASP LEIA appliance data and the ESMAP MTF appliance annex are the usual
# sources. Do not submit with "source: v3, uncited".
WATTS = {
    "incandescent_bulb":  (25,   "v3 notebook, uncited"),
    "fluorescent_tube":   (20,   "v3 notebook, uncited"),
    "cfl_bulb":           (15,   "assumed, uncited"),
    "led_bulb":           (7,    "assumed, uncited"),
    "torch_lantern":      (3,    "assumed, uncited"),
    "radio":              (15,   "v3 notebook, uncited"),
    "radio_cd_system":    (40,   "assumed, uncited"),
    "vcd_dvd":            (30,   "v3 notebook, uncited"),
    "fan":                (50,   "assumed, uncited"),
    "refrigerator":       (100,  "v3 notebook, uncited"),
    "electric_iron":      (1000, "v3 notebook, uncited"),
    "computer":           (100,  "assumed, uncited"),
    "kettle":             (1500, "assumed, uncited"),
    "mobile_charger":     (5,    "assumed, uncited"),
    "smartphone_charger": (10,   "assumed, uncited"),
    "tv_bw":              (40,   "assumed, uncited"),
    "tv_colour":          (60,   "v3 notebook 'tv', uncited"),
    "tv_flat":            (40,   "v3 notebook 'flat_tv', uncited"),
    "modem_router":       (10,   "assumed, uncited"),
}

# Use windows are recorded by neither survey. Assumed, and IDENTICAL across
# countries so they cannot drive a cross-country difference.
WINDOWS = {
    "incandescent_bulb": "18:00-23:00", "fluorescent_tube": "18:00-23:00",
    "cfl_bulb": "18:00-23:00", "led_bulb": "18:00-23:00",
    "torch_lantern": "18:00-23:00", "radio": "06:00-22:00",
    "radio_cd_system": "12:00-22:00", "vcd_dvd": "18:00-22:00",
    "fan": "11:00-22:00", "refrigerator": "00:00-23:59",
    "electric_iron": "07:00-20:00", "computer": "08:00-22:00",
    "kettle": "06:00-21:00", "mobile_charger": "18:00-23:00",
    "smartphone_charger": "18:00-23:00", "tv_bw": "18:00-23:00",
    "tv_colour": "18:00-23:00", "tv_flat": "18:00-23:00",
    "modem_router": "00:00-23:59",
}

# Shared fallback durations, minutes/household/day. Used for BOTH countries in
# the headline specification.
DEFAULT_MINUTES = {
    "incandescent_bulb": 300, "fluorescent_tube": 300, "cfl_bulb": 300,
    "led_bulb": 300, "torch_lantern": 120, "radio": 300,
    "radio_cd_system": 180, "vcd_dvd": 120, "fan": 300,
    "refrigerator": 900, "electric_iron": 30, "computer": 120,
    "kettle": 20, "mobile_charger": 120, "smartphone_charger": 120,
    "tv_bw": 240, "tv_colour": 240, "tv_flat": 240, "modem_router": 900,
}

# ---------------------------------------------------- survey variable maps
# Rwanda SECTION_EF1: (count, used_flag, hours_or_None). Labels transcribed
# from the RWA_2022_MTF_v01_M data dictionary, file F15.
RWANDA_VARS = {
    "incandescent_bulb": ("E01A", "E01B", "E01C"),
    "fluorescent_tube":  ("E02A", "E02B", "E02C"),
    "cfl_bulb":          ("E03A", "E03B", "E03C"),
    "led_bulb":          ("E04A", "E04B", "E04C"),
    "torch_lantern":     ("E05A", "E05B", "E05C"),
    "radio":             ("E06A", "E06B", "E06C"),
    "radio_cd_system":   ("E07A", "E07B", "E07C"),
    "vcd_dvd":           ("E08A", "E08B", None),
    "fan":               ("E09A", "E09B", "E09C"),
    "refrigerator":      ("E10A", "E10B", "E10C"),
    "electric_iron":     ("E13A", "E13B", None),
    "computer":          ("E26A", "E26B", None),
    "kettle":            ("E27A", "E27B", None),
    "smartphone_charger":("E28A", "E28B", None),
    "mobile_charger":    ("E29A", "E29B", None),
    "tv_bw":             ("E30A", "E30B", "E30C"),
    "tv_colour":         ("E31A", "E31B", "E31C"),
    "tv_flat":           ("E32A", "E32B", "E32C"),
    "modem_router":      ("E33A", "E33B", None),
}

# Kenya M3_Asset_Data_Final: binary flags, no counts, no hours.
#
# MAPPING VERIFIED against MTF_KENYA_Questionnaire_Household.pdf (Section M,
# items M.15-M.40), published openly on energydata.info under CC-BY 4.0.
# The variable NAMES are correct. FOUR LABELS in Codebook_KENYA.xlsx are
# shifted up by one row and must not be trusted:
#
#   variable        codebook label (WRONG)       questionnaire (CORRECT)
#   asset_radio     "owns Rechargeable Torch"    M.20 Radio/CD/sound system
#   asset_ekettle   "owns Computer"              M.33 Electric hot water pot/kettle
#   asset_tv        "owns Black/White TV"        M.37 Regular Color TV
#   asset_flatv     "owns Regular Colar TV"      M.38 Flat color TV
#
# This matters: read literally, the labels put a 60 W colour TV on the
# black-and-white row and turn the kettle into a computer.
#
# The questionnaire also asks usage hours (column b) but "only for fan, radio
# and TV", and that column is absent from the distributed data. So Kenya still
# has no appliance durations and the symmetry handling below stands.
KENYA_VARS = {
    "incandescent_bulb": "asset_bulb",        # M.15
    "fluorescent_tube":  "asset_ftube",       # M.16
    "cfl_bulb":          "asset_cfl",         # M.17
    "led_bulb":          "asset_led",         # M.18
    "torch_lantern":     "asset_rchtorch",    # M.19
    "radio":             "asset_radio",       # M.20
    "vcd_dvd":           "asset_dvd",         # M.21
    "fan":               "asset_fan",         # M.22
    "refrigerator":      "asset_fridge",      # M.23
    "electric_iron":     "asset_iron",        # M.25
    "computer":          "asset_cmpter",      # M.32
    "kettle":            "asset_ekettle",     # M.33
    "smartphone_charger": "asset_spcharger",  # M.34
    "mobile_charger":    "asset_charger",     # M.35
    "tv_bw":             "asset_bwtv",        # M.36
    "tv_colour":         "asset_tv",          # M.37
    "tv_flat":           "asset_flatv",       # M.38
}


# ------------------------------------------------------------------ helpers
def _yes(series):
    num = pd.to_numeric(series, errors="coerce")
    txt = series.astype(str).str.strip().str.lower().isin(YES)
    return (num.fillna(0) > 0) | txt


def scan_access_candidates(path, weight_col="HH_WT", top=25):
    """Find the electricity-access variable without guessing its name.

    SECTION_EF1 carries no access variable, so restricting to households WITH
    electricity (which is what s3.2 says the parameters represent) needs a
    merge. Rather than hard-code a variable name I have not verified, this
    prints every binary column alongside its weighted share, so the one
    matching the published Rwanda MTF headline can be picked by eye:

        national grid connection  ~51%   (Rwanda MTF 2022, June 2022)
        any electricity access    ~73%

    Run with --scan-access, pick the variable, pass it via --rwanda-access-var.
    """
    df = pd.read_csv(path, low_memory=False)
    w = pd.to_numeric(df.get(weight_col, pd.Series(1.0, index=df.index)),
                      errors="coerce").fillna(1.0)
    rows = []
    for c in df.columns:
        s = df[c].dropna()
        if s.empty or s.nunique() > 3:
            continue
        share = float((_yes(df[c]) * w).sum() / w.sum())
        rows.append({"variable": c, "n_distinct": int(s.nunique()),
                     "weighted_share_yes": round(share, 4),
                     "n_valid": int(s.notna().sum())})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["dist_to_grid_51pct"] = (out.weighted_share_yes - 0.51).abs()
    return out.sort_values("dist_to_grid_51pct").head(top).reset_index(drop=True)


# ---------------------------------------------------------------- extraction
def rwanda_ownership(root, urban_rural="rural", include_camp=False,
                     access_file="SECTION_C1.csv", access_var=None,
                     access_value=1):
    """Weighted appliance ownership and mean daily usage hours.

    HI04 is numeric in the distributed file, not the string the label suggests:
    1 = Urban (89.3% grid-connected), 2 = Rural (42.2%). Confirmed against the
    published national shares, which the file reproduces to three decimals
    (grid 0.5065 vs 51%; any access 0.7374 vs 73%).
    """
    root = Path(root)
    df = pd.read_csv(root / "SECTION_EF1.csv", low_memory=False)
    n0 = len(df)
    if not include_camp:
        df = df[df.camp.isna()]            # NULL means non-refugee. Not 0.
    if urban_rural and "HI04" in df:
        code = {"urban": 1, "rural": 2}[str(urban_rural).strip().lower()]
        df = df[pd.to_numeric(df.HI04, errors="coerce") == code]
    if access_var:
        acc = pd.read_csv(root / access_file, low_memory=False,
                          usecols=lambda c: c in {"hhid", access_var})
        acc = acc.drop_duplicates("hhid")
        df = df.merge(acc, on="hhid", how="inner")
        df = df[df[access_var] == access_value]
    if df.empty:
        raise ValueError("filters removed every household; run --scan-access")

    w = pd.to_numeric(df.HH_WT, errors="coerce").fillna(1.0)
    rows = []
    for name, (cnt, used, hrs) in RWANDA_VARS.items():
        if cnt not in df and used not in df:
            continue
        owned = pd.Series(False, index=df.index)
        if cnt in df:
            owned |= pd.to_numeric(df[cnt], errors="coerce").fillna(0) > 0
        if used in df:
            owned |= _yes(df[used])
        rate = float((owned * w).sum() / w.sum())
        minutes = np.nan
        if hrs and hrs in df:
            h = pd.to_numeric(df.loc[owned, hrs], errors="coerce")
            ww = w[owned]
            ok = h.notna() & (h >= 0) & (h <= 24)     # 888 = "don't know"
            if ok.any():
                minutes = float((h[ok] * ww[ok]).sum() / ww[ok].sum()) * 60
        rows.append({"country": "rwanda", "appliance": name,
                     "ownership_rate": round(rate, 4),
                     "measured_minutes": (round(minutes) if minutes == minutes
                                          else None),
                     "n_households": int(df.hhid.nunique()),
                     "n_before_filters": n0})
    return pd.DataFrame(rows).sort_values("ownership_rate", ascending=False)


def kenya_ownership(root, grid_loc="Rural with grid access",
                    denominator="all_households", weight_file="weight.csv"):
    """Kenya ownership from M3 flags, weighted, on a stated denominator.

    THREE ASYMMETRIES vs Rwanda that v3 left open, all closed here.

    1. DENOMINATOR. Rwanda's SECTION_EF1 has a row for all 5,706 households
       with explicit zeros (2,434 households record E29A = 0), so its
       denominator is every household. Kenya's M3 is an owner roster: it holds
       324 of the 521 rural-with-grid households, and only 20 of its 2,684 rows
       record no assets at all. M1 (vehicles, 613 hh) and M2 (livestock, 1,889
       hh) follow the same owner-roster pattern, so absence from M3 most
       likely means "owns none of the listed appliances".

         denominator="all_households"  absence counts as non-ownership.
                                       Comparable with Rwanda. DEFAULT.
         denominator="asset_file"      M3 rows only. This is what v3 did and
                                       what s3.2's 15.1% / 13.3% report. It
                                       inflates Kenyan ownership ~1.6x
                                       relative to Rwanda's basis.

       Confirm the questionnaire skip pattern to close this definitively; the
       two bounds are reported side by side so the choice is visible.

    2. WEIGHTS. Rwanda uses HH_WT. v3's Kenya extraction was unweighted.
       pw_final in weight.csv is the Kenyan equivalent and is applied here.

    3. USAGE HOURS. Rwanda records them, Kenya does not. Handled by the
       durations switch in to_ramp_dict(), not here.
    """
    if denominator not in ("all_households", "asset_file"):
        raise ValueError(denominator)
    root = Path(root)
    m3 = pd.read_csv(root / "MTF_HH_Sec.M3_Asset_Data_Final.csv",
                     low_memory=False)
    core = pd.read_csv(root / "MTF_HH_Core_Survey_Final_Data_trimmed-2.csv",
                       low_memory=False, encoding="latin-1",
                       usecols=["PARENT_KEY", "grid_loc"])
    core = core.drop_duplicates("PARENT_KEY")

    # grid_loc is a Stata labelled variable. Converted with labels it reads
    # "Rural with grid access"; converted without, it is a bare code. Accept
    # both rather than silently returning an empty frame.
    GRID_CODES = {"Urban with grid access": 1, "Urban without grid access": 2,
                  "Rural with grid access": 3, "Rural without grid access": 4}
    sub = core[core.grid_loc == grid_loc]
    if sub.empty and grid_loc in GRID_CODES:
        sub = core[pd.to_numeric(core.grid_loc, errors="coerce")
                   == GRID_CODES[grid_loc]]
    if sub.empty:
        raise ValueError(
            f"grid_loc={grid_loc!r} matched no households. Values present: "
            f"{sorted(core.grid_loc.dropna().unique())[:6]}. If these are "
            "numeric codes, the .dta was converted with "
            "convert_categoricals=False; re-convert with it True.")
    merged = sub.merge(m3, on="PARENT_KEY", how="left")

    w = pd.Series(1.0, index=merged.index)
    wpath = root / weight_file
    if wpath.exists():
        wt = pd.read_csv(wpath, low_memory=False,
                         usecols=["PARENT_KEY", "pw_final"]).drop_duplicates(
                             "PARENT_KEY")
        merged = merged.merge(wt, on="PARENT_KEY", how="left")
        w = pd.to_numeric(merged.pw_final, errors="coerce").fillna(1.0)

    rows = []
    for name, col in KENYA_VARS.items():
        if col not in merged:
            continue
        present = merged[col].notna()
        owned = _yes(merged[col].fillna("No"))
        if denominator == "asset_file":
            num, den = (owned & present) * w, w[present]
            rate = float(num.sum() / den.sum())
        else:
            rate = float((owned * w).sum() / w.sum())
        rows.append({"country": "kenya", "appliance": name,
                     "ownership_rate": round(rate, 4),
                     "measured_minutes": None,
                     "n_households": int(len(sub)),
                     "n_in_asset_file": int(present.sum()),
                     "denominator": denominator})
    return pd.DataFrame(rows).sort_values("ownership_rate", ascending=False)


# ------------------------------------------------------------------- emitter
def to_ramp_dict(df, durations="assumed", min_rate=0.005):
    """appliance -> (rate, watts, daily_minutes, window), RAMP's format."""
    if durations not in ("assumed", "measured"):
        raise ValueError(durations)
    out = {}
    for r in df.itertuples():
        if r.appliance not in WATTS or r.ownership_rate < min_rate:
            continue
        mins = DEFAULT_MINUTES[r.appliance]
        measured = r.measured_minutes
        # NaN survives the DataFrame round-trip and is truthy, so test for it
        # explicitly rather than relying on `if measured:`.
        has_measured = (measured is not None
                        and not (isinstance(measured, float) and measured != measured)
                        and float(measured) > 0)
        if durations == "measured" and has_measured:
            mins = int(round(float(measured)))
        out[r.appliance] = (round(float(r.ownership_rate), 4),
                            WATTS[r.appliance][0], int(mins),
                            WINDOWS[r.appliance])
    return out


def emit_python(varname, d, note=""):
    lines = [f"# {note}" if note else "", f"{varname} = {{"]
    width = max((len(k) for k in d), default=0)
    for k, v in sorted(d.items(), key=lambda kv: -kv[1][0]):
        lines.append(f'    "{k}":{" " * (width - len(k))} '
                     f'({v[0]}, {v[1]}, {v[2]}, "{v[3]}"),')
    lines.append("}")
    return "\n".join(x for x in lines if x)


def sanity(df, country):
    bad = df[(df.ownership_rate < 0) | (df.ownership_rate > 1)]
    assert bad.empty, f"{country}: ownership outside [0,1]\n{bad}"
    assert df.ownership_rate.max() > 0, f"{country}: every rate is zero"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rwanda"); ap.add_argument("--kenya")
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--durations", choices=["assumed", "measured"],
                    default="assumed")
    ap.add_argument("--rwanda-access-file", default="SECTION_C1.csv")
    ap.add_argument("--rwanda-access-var", default=None)
    ap.add_argument("--rwanda-access-value", default=1, type=int)
    ap.add_argument("--kenya-grid-loc", default="Rural with grid access")
    ap.add_argument("--scan-access", action="store_true")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    if a.scan_access:
        p = Path(a.rwanda) / a.rwanda_access_file
        print(f"Binary variables in {p}, ranked by closeness to the published "
              f"51% grid-connection share:\n")
        print(scan_access_candidates(p).to_string(index=False))
        print("\nPick one and pass it as --rwanda-access-var. ~0.51 is grid "
              "connection; ~0.73 is any electricity access (Rwanda MTF 2022).")
        return

    frames = []
    if a.rwanda:
        rw = rwanda_ownership(a.rwanda, access_file=a.rwanda_access_file,
                              access_var=a.rwanda_access_var,
                              access_value=a.rwanda_access_value)
        sanity(rw, "rwanda"); frames.append(rw)
    if a.kenya:
        ke = kenya_ownership(a.kenya, grid_loc=a.kenya_grid_loc)
        sanity(ke, "kenya"); frames.append(ke)
    if not frames:
        ap.error("give --rwanda and/or --kenya")

    allf = pd.concat(frames, ignore_index=True)
    allf.to_csv(out / "appliance_ownership_both.csv", index=False)
    print(allf.to_string(index=False))

    print("\n" + "=" * 70)
    print(f"PASTE INTO src/final_cfg.py   (durations={a.durations})")
    print("=" * 70)
    for f in frames:
        c = f.country.iloc[0]
        d = to_ramp_dict(f, durations=a.durations)
        print()
        print(emit_python(f"APPLIANCES_{c.upper()}", d,
                          note=f"MTF-derived, {c}, durations={a.durations}. "
                               f"Wattages and windows assumed, identical "
                               f"across countries."))

    if a.rwanda and a.kenya:
        piv = (allf.pivot_table(index="appliance", columns="country",
                                values="ownership_rate")
                   .fillna(0.0).sort_values("rwanda", ascending=False))
        piv["ratio_rw_ke"] = (piv.rwanda / piv.kenya.replace(0, np.nan)).round(2)
        print("\nCross-country ownership, the thing s3.2 is meant to report:")
        print(piv.round(4).to_string())
        if (piv.rwanda == piv.kenya).all():
            raise SystemExit("ERROR: identical ownership in both countries - "
                             "the inheritance bug has returned")


if __name__ == "__main__":
    main()
