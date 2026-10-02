"""Phase 3 (optional item): what does switching cost the HOUSEHOLD?

s2.5 and s6.6 name appliance cost as the binding constraint and then exclude
it. This folds the electric pressure cooker into an annual household cost of
cooking, against the counterfactual s6.6 identifies: firewood that is mostly
COLLECTED (82% of rural Rwandan households collect, 45% purchase - national
70.7% / 37.9%; see data/processed/fuel_use_rwanda.csv).

  electric  = incremental electricity bill for the household's cooking kWh,
              at the band schedule (the band penalty is included because the
              bill is computed on total, not incremental, consumption)
              + EPC capital annualised at the household discount rate
  firewood  = cash for purchased wood + (optionally) collection time valued
              at a shadow wage. Collected wood has ~zero cash cost, which is
              the s6.6 point: a cash comparison understates the barrier.

Parameters marked TO CONFIRM are assumptions; none is estimated here.
"""
import numpy as np
import pandas as pd

from model import _band_rate

HOUSEHOLD = {
    "epc_price_usd": 140.0,          # s2.5, Bondo (Malawi) average, MWK 250,000
    "epc_life_years": 5,             # TO CONFIRM
    "household_discount_rate": 0.25,  # high implicit rates; TO CONFIRM
    # Purchased firewood cash spend, USD/month, for households that buy.
    # TO CONFIRM: derive from SECTION_I I16 x purchase frequency (I13 codes
    # need the questionnaire to convert to a monthly rate).
    "purchased_wood_usd_month": None,
    # Collection time and shadow wage - for the time-cost variant only.
    "collection_hours_week": 6.0,    # TO CONFIRM (MTF has collection time)
    "shadow_wage_usd_hour": 0.15,    # TO CONFIRM
}


def crf(r, n):
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


def bill_month(kwh, t):
    return _band_rate(kwh, t) * kwh


def compare(cfg, noncooking_kwh_month, cooking_kwh_month, h=HOUSEHOLD):
    t = cfg["tariff"]
    elec_bill = 12 * (bill_month(noncooking_kwh_month + cooking_kwh_month, t)
                      - bill_month(noncooking_kwh_month, t))
    epc = h["epc_price_usd"] * crf(h["household_discount_rate"], h["epc_life_years"])
    rows = [{"option": "electric (EPC)", "cash_usd_year": elec_bill + epc,
             "of_which_electricity": elec_bill, "of_which_appliance": epc,
             "incremental_rate_usd_kwh": elec_bill / (12 * cooking_kwh_month)}]
    rows.append({"option": "firewood, collected (cash)", "cash_usd_year": 0.0})
    rows.append({"option": "firewood, collected (time at shadow wage)",
                 "cash_usd_year": 52 * h["collection_hours_week"] * h["shadow_wage_usd_hour"]})
    if h["purchased_wood_usd_month"] is not None:
        rows.append({"option": "firewood, purchased",
                     "cash_usd_year": 12 * h["purchased_wood_usd_month"]})
    else:
        rows.append({"option": "firewood, purchased: SOURCE NEEDED"})
    return pd.DataFrame(rows)
