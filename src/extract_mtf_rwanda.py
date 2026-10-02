"""Rwanda MTF 2022 extraction, corrected.

WHY THIS FILE EXISTS
--------------------
src/extract_mtf.py reads SECTION_I.csv, groups by I02, and writes the result
to appliance_ownership_rwanda.csv under the heading "RWANDA appliance
ownership". Per the published data dictionary for RWA_2022_MTF_v01_M
(catalog.ihsn.org/catalog/12731, data file F21):

    SECTION_I   102,708 cases, 41 variables
      I02   "Fuel"
      I03   "used fuel"
      I04   "Lighting"      I05  "Cooking"     I06  "Heating"
      I13   "How often a household member purchase or collect or receive
             this fuel"

SECTION_I is the FUEL section. It contains no appliances at all. The figures
labelled I02_code_3 = 0.707 and I02_code_2 = 0.379 are the weighted shares of
households using fuel codes 3 and 2, not appliance ownership rates.

Consequences for the manuscript:

  * s3.2's Rwandan appliance figures (phone charging 70.9%, CFL 53.9%,
    colour TV 6.9%) cannot have come from this pipeline. Nothing in it reads
    Rwandan appliance data.
  * s6.6's "70.7% of households collect firewood while 37.9% purchase it"
    matches I02_code_3 and I02_code_2 to three decimal places. But those are
    two different FUELS, each with a usage share - not collect-versus-purchase
    of one fuel. Collect/purchase is I13, which the script never reads.
  * s3.2 states that "appliance wattages and daily use durations are not
    recorded in the MTF and are assumed". Daily use duration IS recorded:
    SECTION_EF1 carries E01C, E02C, E03C, E04C, E05C, E06C, E07C, E09C, E10C,
    E30C, E31C and E32C, each labelled "Number of hours of usage in typical
    day". Only wattage is genuinely absent.

Appliances live in SECTION_EF1 (F15): 5,706 household-level cases, E00A-E37B.

STATUS: written against the published data dictionary, NOT yet executed
against the microdata, which is not in this container. Run it, check the
printed labels against the questionnaire, then paste the resulting dict into
final_cfg.APPLIANCES_RWANDA.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# code -> (label, count_var, used_var, hours_var or None)
# Labels transcribed from the RWA_2022_MTF_v01_M data dictionary, SECTION_EF1.
APPLIANCES = {
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
    "microwave":         ("E11A", "E11B", None),
    "electric_iron":     ("E13A", "E13B", None),
    "hair_dryer":        ("E14A", "E14B", None),
    "blender":           ("E15A", "E15B", None),
    "rice_cooker":       ("E16A", "E16B", None),
    "freezer":           ("E17A", "E17B", None),
    "washing_machine":   ("E18A", "E18B", None),
    "sewing_machine":    ("E20A", "E20B", None),
    "air_cooler":        ("E21A", "E21B", None),
    "air_conditioner":   ("E22A", "E22B", None),
    "space_heater":      ("E23A", "E23B", None),
    "water_heater":      ("E24A", "E24B", None),
    "computer":          ("E26A", "E26B", None),
    "kettle":            ("E27A", "E27B", None),
    "smartphone_charger":("E28A", "E28B", None),
    "mobile_charger":    ("E29A", "E29B", None),
    "tv_bw":             ("E30A", "E30B", "E30C"),
    "tv_colour":         ("E31A", "E31B", "E31C"),
    "tv_flat":           ("E32A", "E32B", "E32C"),
    "modem_router":      ("E33A", "E33B", None),
    "electric_mill":     ("E34A", "E34B", None),
    "water_pump":        ("E35A", "E35B", None),
}

YES = {"yes", "1", "1.0", "true"}


def _owns(df, count_var, used_var):
    """Owned = a positive count, or an explicit yes on the usage flag."""
    owned = pd.Series(False, index=df.index)
    if count_var in df:
        owned |= pd.to_numeric(df[count_var], errors="coerce").fillna(0) > 0
    if used_var in df:
        owned |= df[used_var].astype(str).str.strip().str.lower().isin(YES)
    return owned


def appliance_ownership(root, urban_rural="Rural", include_camp=False,
                        grid_access_var=None, grid_access_value=None):
    """Weighted appliance ownership and mean daily usage hours.

    grid_access_var/value: SECTION_EF1 carries no electricity-access variable,
    so restricting to households WITH grid access (which is what s3.2 says the
    parameters represent) needs a merge on hhid against the electricity
    section. Confirm the variable name in the data dictionary before using it;
    left None here rather than guessed.
    """
    df = pd.read_csv(Path(root) / "SECTION_EF1.csv", low_memory=False)
    if not include_camp:
        df = df[df.camp.isna()]          # NULL means non-refugee. Not 0.
    if urban_rural is not None and "HI04" in df:
        df = df[df.HI04.astype(str).str.strip().str.lower()
                  .eq(urban_rural.strip().lower())]
    if grid_access_var is not None:
        df = df[df[grid_access_var] == grid_access_value]
    if df.empty:
        raise ValueError("filter removed every household - check HI04 coding")

    w = pd.to_numeric(df.HH_WT, errors="coerce").fillna(1.0)
    rows = []
    for name, (cnt, used, hrs) in APPLIANCES.items():
        if cnt not in df and used not in df:
            continue
        owned = _owns(df, cnt, used)
        rate = float((owned * w).sum() / w.sum())
        mean_hours = np.nan
        if hrs and hrs in df:
            h = pd.to_numeric(df.loc[owned, hrs], errors="coerce")
            ww = w[owned]
            ok = h.notna()
            if ok.any():
                mean_hours = float((h[ok] * ww[ok]).sum() / ww[ok].sum())
        rows.append({"appliance": name, "count_var": cnt,
                     "ownership_rate": round(rate, 4),
                     "mean_hours_per_day": (round(mean_hours, 2)
                                            if mean_hours == mean_hours else None),
                     "n_households": int(df.hhid.nunique())})
    return (pd.DataFrame(rows).sort_values("ownership_rate", ascending=False)
                              .reset_index(drop=True))


def fuel_use(root, include_camp=False):
    """What SECTION_I actually measures: fuel usage and acquisition mode.

    This is the correct home for the s6.6 firewood statistics. Fuel codes must
    be read off the questionnaire; they are printed here unmapped so the
    mapping is done deliberately rather than assumed.
    """
    si = pd.read_csv(Path(root) / "SECTION_I.csv", low_memory=False)
    if not include_camp:
        si = si[si.camp.isna()]
    w = pd.to_numeric(si.HH_WT, errors="coerce").fillna(1.0)
    used = pd.to_numeric(si.I03, errors="coerce").fillna(0)
    t = pd.DataFrame({"fuel_code": si.I02, "_num": used * w, "_den": w})
    g = t.groupby("fuel_code")[["_num", "_den"]].sum()
    out = (g["_num"] / g["_den"]).rename("share_of_households").reset_index()

    # Cooking-fuel share and acquisition mode, which is what s6.6 needs.
    if "I05" in si:
        cook = si[pd.to_numeric(si.I05, errors="coerce").fillna(0) > 0]
        cshare = (cook.groupby("I02").apply(
            lambda g: (pd.to_numeric(g.HH_WT, errors="coerce").fillna(1.0)).sum())
            / w.sum()).rename("share_cooking_with_this_fuel")
        out = out.merge(cshare.reset_index().rename(
            columns={"I02": "fuel_code"}), on="fuel_code", how="left")
    return out.sort_values("share_of_households", ascending=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rwanda", required=True, help="dir holding SECTION_*.csv")
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--urban-rural", default="Rural")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    own = appliance_ownership(args.rwanda, urban_rural=args.urban_rural)
    own.to_csv(out / "appliance_ownership_rwanda_SECTIONEF1.csv", index=False)
    print(f"RWANDA appliance ownership, {args.urban_rural}, SECTION_EF1")
    print(own.head(15).to_string(index=False))

    fu = fuel_use(args.rwanda)
    fu.to_csv(out / "fuel_use_rwanda_SECTIONI.csv", index=False)
    print("\nRWANDA fuel use, SECTION_I (codes need questionnaire mapping)")
    print(fu.head(10).to_string(index=False))
    print("\nCheck: the values previously reported as appliance ownership "
          "(0.707, 0.510, 0.379 ...) should reappear in THIS table, which is "
          "where they came from.")


if __name__ == "__main__":
    main()
