"""Regenerate every MTF-derived number the paper uses, and record the data
checks behind Phase 1, item 2 (map the MTF codes against the questionnaire).

    python src/mtf_checks.py [--kenya DIR] [--rwanda DIR] [--out data/processed]

Needs the raw microdata in data/raw (not in the repository: the Rwanda MTF
2022 licence forbids redistribution; see docs/DATA_ACCESS.md). Writes only
aggregate tables, which are committed.

Outputs
  appliance_ownership_both.csv          headline sets (Rwanda EF1; Kenya M3)
  appliance_ownership_kenya_sources.csv Kenya M3 flags vs core multi-select
  cooking_dayparts_kenya.csv            Table/s3.2 daypart shares
  fuel_use_rwanda.csv                   s6.6 firewood evidence
  mtf_checks.md                         human-readable summary
"""
import argparse
from pathlib import Path

import pandas as pd

import mtf_appliances as M

KEN = "data/raw/KEN_2016-2018_MTF_v02_M_CSV"
RWA = "data/raw/household_survey_data"
DAYPART = {"morning": "i_23_hrs_morning", "afternoon": "i_24_hrs_afternoon",
           "evening": "i_25_hrs_evening"}


def kenya_dayparts(root):
    """s3.2: minutes of cooking by daypart, household level (the cooking file
    is stove-level; 'hrs' variables are in MINUTES despite the name).
    Unweighted, as published; the weighted shares are reported alongside."""
    root = Path(root)
    cook = pd.read_csv(root / "MTF_HH_Cooking_Data_Final.csv", low_memory=False)
    for c in DAYPART.values():
        cook[c] = pd.to_numeric(cook[c], errors="coerce")
    hh = (cook.groupby("PARENT_KEY")
              .agg(**{k: (v, "sum") for k, v in DAYPART.items()},
                   grid_loc=("grid_loc", "first")).reset_index())
    hh["total"] = hh[list(DAYPART)].sum(axis=1)
    hh = hh[hh.total > 0]
    wt = pd.read_csv(root / "weight.csv", usecols=["PARENT_KEY", "pw_final"])
    hh = hh.merge(wt.drop_duplicates("PARENT_KEY"), on="PARENT_KEY", how="left")
    hh["pw_final"] = hh.pw_final.fillna(1.0)
    rows = []
    for grp, g in list(hh.groupby("grid_loc")) + [("ALL", hh)]:
        m = {k: g[k].mean() for k in DAYPART}
        wm = {k: (g[k] * g.pw_final).sum() / g.pw_final.sum() for k in DAYPART}
        t, wt_ = sum(m.values()), sum(wm.values())
        rows.append({"group": grp, "n": len(g),
                     **{f"{k}_min": round(v, 1) for k, v in m.items()},
                     **{f"share_{k}": round(v / t, 4) for k, v in m.items()},
                     **{f"share_{k}_weighted": round(v / wt_, 4) for k, v in wm.items()}})
    return pd.DataFrame(rows)


def rwanda_fuels(root):
    """s6.6 claims "70.7% of households collect firewood while 37.9% purchase
    it". v4 concluded those were two different FUELS and the sentence was
    wrong. The microdata point the other way: fuel code 3 has NO quantity
    (I15) or price (I16) recorded for any user - the skip pattern of a
    collected fuel - while code 2 carries prices (mean RWF ~1,900). So codes 2
    and 3 look like firewood purchased / firewood collected, and the sentence
    is probably right. Confirm the code labels against the questionnaire.
    I13 is purchase/collection FREQUENCY, not mode.
    """
    si = pd.read_csv(Path(root) / "SECTION_I.csv", low_memory=False)
    si = si[si.camp.isna()]                 # NULL = non-refugee
    rows = []
    for scope, d in (("national", si), ("rural", si[si.HI04 == 2])):
        for code, g in d.groupby("I02"):
            used = g.I03 == 1
            w = g.HH_WT
            u = g[used]
            rows.append({
                "scope": scope, "fuel_code": int(code),
                "share_using": round(float((w * used).sum() / w.sum()), 4),
                "share_cooking": round(float((w * (g.I05 == 1)).sum() / w.sum()), 4),
                "n_users": int(used.sum()),
                "users_with_quantity": int(u.I15.notna().sum()),
                "users_with_price": int(u.I16.notna().sum()),
                "mean_price_rwf": round(float(u.I16.mean()), 0) if u.I16.notna().any() else None,
            })
    out = pd.DataFrame(rows)
    out["inferred"] = None
    out.loc[out.fuel_code == 2, "inferred"] = "firewood, purchased (has price)"
    out.loc[out.fuel_code == 3, "inferred"] = "firewood, collected (no qty/price)"
    return out


def kenya_sources(root):
    m3 = M.kenya_ownership(root, denominator="all_households").assign(source="M3 asset flags")
    core = M.kenya_ownership_core(root)
    both = pd.concat([m3, core], ignore_index=True)
    return both.pivot_table(index="appliance", columns="source",
                            values="ownership_rate").fillna(0).sort_values(
        "core m_m_3_group", ascending=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kenya", default=KEN)
    ap.add_argument("--rwanda", default=RWA)
    ap.add_argument("--out", default="data/processed")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    rw = M.rwanda_ownership(a.rwanda, access_var="C002")
    ke = M.kenya_ownership(a.kenya, denominator="all_households")
    pd.concat([rw, ke], ignore_index=True).to_csv(out / "appliance_ownership_both.csv",
                                                  index=False)
    src = kenya_sources(a.kenya)
    src.to_csv(out / "appliance_ownership_kenya_sources.csv")
    dp = kenya_dayparts(a.kenya)
    dp.to_csv(out / "cooking_dayparts_kenya.csv", index=False)
    fu = rwanda_fuels(a.rwanda)
    fu.to_csv(out / "fuel_use_rwanda.csv", index=False)

    md = ["# MTF data checks (generated by src/mtf_checks.py)", "",
          "## Kenya cooking dayparts", "", dp.to_string(index=False), "",
          "## Kenya appliance ownership: M3 flags vs core multi-select "
          "(rural, grid-connected, pw_final)", "", src.to_string(), "",
          "## Rwanda fuel use (SECTION_I, non-refugee, HH_WT)", "",
          fu[fu.share_using > 0].to_string(index=False), ""]
    (out / "mtf_checks.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
