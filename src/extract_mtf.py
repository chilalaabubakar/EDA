"""Extract RAMP inputs and cooking daypart shares from MTF microdata.

    python src/extract_mtf.py --kenya path/to/KEN_..._CSV --rwanda path/to/rwanda --out data/processed

Writes small, shareable summary CSVs. No household records leave this script.

Gotchas already handled (each cost real debugging time):
  * Kenya core CSV is latin-1, not utf-8.
  * Kenya asset flags are the strings "Yes"/"No", not 1/0.
  * Rwanda `camp` is NULL for non-refugees, not 0. Filtering on ==0 silently
    keeps refugee households.
  * Kenya cooking "hrs" variables are in MINUTES despite the name.
  * Kenya cooking file is stove-level: aggregate to household before averaging.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DAYPART = {"morning": "i_23_hrs_morning",
           "afternoon": "i_24_hrs_afternoon",
           "evening": "i_25_hrs_evening"}


def kenya(root, out):
    root = Path(root)
    cook = pd.read_csv(root / "MTF_HH_Cooking_Data_Final.csv", low_memory=False)
    core = pd.read_csv(root / "MTF_HH_Core_Survey_Final_Data_trimmed-2.csv",
                       low_memory=False, encoding="latin-1",
                       usecols=["PARENT_KEY", "grid_loc"])
    m3 = pd.read_csv(root / "MTF_HH_Sec.M3_Asset_Data_Final.csv", low_memory=False)

    for c in DAYPART.values():
        cook[c] = pd.to_numeric(cook[c], errors="coerce")

    hh = (cook.groupby("PARENT_KEY")
              .agg(morning=(DAYPART["morning"], "sum"),
                   afternoon=(DAYPART["afternoon"], "sum"),
                   evening=(DAYPART["evening"], "sum"),
                   grid_loc=("grid_loc", "first"))
              .reset_index())
    hh["total"] = hh[["morning", "afternoon", "evening"]].sum(axis=1)
    hh = hh[hh.total > 0]

    rows = []
    for grp, g in list(hh.groupby("grid_loc")) + [("ALL", hh)]:
        m, a, e = g.morning.mean(), g.afternoon.mean(), g.evening.mean()
        t = m + a + e
        rows.append({"country": "kenya", "group": grp, "n": len(g),
                     "morning_min": round(m, 1), "afternoon_min": round(a, 1),
                     "evening_min": round(e, 1), "total_min": round(t, 1),
                     "share_morning": round(m / t, 4),
                     "share_afternoon": round(a / t, 4),
                     "share_evening": round(e / t, 4)})
    dayparts = pd.DataFrame(rows)
    dayparts.to_csv(out / "cooking_dayparts_kenya.csv", index=False)

    # appliance ownership, rural off-grid
    m = m3.merge(core, on="PARENT_KEY", how="left")
    ro = m[m.grid_loc == "Rural without grid access"]
    acols = [c for c in m3.columns if c.startswith("asset_")]
    own = pd.DataFrame({
        "appliance": acols,
        "ownership_rate": [ro[c].astype(str).str.strip().str.lower().eq("yes").mean()
                           for c in acols],
        "n": len(ro),
        "country": "kenya",
    }).sort_values("ownership_rate", ascending=False)
    own.to_csv(out / "appliance_ownership_kenya.csv", index=False)
    return dayparts, own


def rwanda(root, out, include_camp=False):
    root = Path(root)
    si = pd.read_csv(root / "SECTION_I.csv", low_memory=False)
    if not include_camp:
        si = si[si.camp.isna()]          # NULL means non-refugee. Not 0.
    # Vectorised weighted mean. Avoids groupby.apply, whose `include_groups`
    # argument exists only in pandas>=2.2 - and RAMP pins us below that.
    w = si.HH_WT.fillna(1.0)
    tmp = pd.DataFrame({"I02": si.I02, "_num": si.I03 * w, "_den": w})
    g = tmp.groupby("I02")[["_num", "_den"]].sum()
    own = (g["_num"] / g["_den"]).reset_index()
    own.columns = ["I02", "ownership_rate"]
    own["appliance"] = "I02_code_" + own.I02.astype(int).astype(str)
    own["country"] = "rwanda"
    own["n_households"] = si.hhid.nunique()
    own = own.sort_values("ownership_rate", ascending=False)
    own.to_csv(out / "appliance_ownership_rwanda.csv", index=False)
    return own


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kenya", required=True)
    ap.add_argument("--rwanda", required=True)
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--include-camp", action="store_true",
                    help="Rwanda: include refugee households (default excludes)")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    dp, ko = kenya(args.kenya, out)
    ro = rwanda(args.rwanda, out, args.include_camp)

    print("KENYA cooking dayparts (minutes/household/day)")
    print(dp[["group", "n", "morning_min", "afternoon_min", "evening_min",
              "share_afternoon"]].to_string(index=False))
    print("\nKENYA appliance ownership, rural off-grid (top 10)")
    print(ko.head(10)[["appliance", "ownership_rate"]].to_string(index=False))
    print("\nRWANDA appliance ownership (top 10, codes need questionnaire mapping)")
    print(ro.head(10)[["appliance", "ownership_rate"]].to_string(index=False))
    print(f"\nWrote 3 summary CSVs to {out}")


if __name__ == "__main__":
    main()
