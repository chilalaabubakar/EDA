"""Sourced configuration. Every value has a provenance comment."""
KES_USD, RWF_USD = 129.0, 1460.0    # RWF confirmed: RWF2,205/L = USD1.51 (RURA via GPP, 25 May 2026)
ISLAND_PREMIUM  = 1.15              # assumption: boat delivery to island sites

# CAPEX components: SEforALL 2024 benchmark shares applied to the AMDA
# all-in figure of $6,824/kWp (SSA 2020-24 average).
BASE_CFG = {
 "pv":{"temp_coeff_per_c":-0.004,"noct_c":45,"derate_factor":0.85,"degradation_rate":0.008},
 "battery":{"round_trip_efficiency":0.90,"depth_of_discharge":0.80,"cycle_life":3000,
            "replacement_year":10,"max_c_rate":0.5},
 "bos":{"inverter_eff":0.97,"dc_ac_ratio":1.2},
 "capex":{"pv_per_kw":1228,            # SEforALL solar share 18% x $6,824
          "battery_per_kwh":300,       # ESMAP mini-grid range $100-300/kWh, upper bound
          "diesel_per_kw":700,
          "inverter_per_kw":400,
          "connection_per_customer":400,   # SEforALL 12% share ~ $273 + island premium
          "soft_cost_fraction":0.333},     # duties 10 + soft 6 + distribution 5 + construction 4
 # OPEX BASIS MUST BE EXPLICIT. Before this was fixed the config defined
 # per_customer_year and the code never read it: financials() used
 # om_fraction_of_capex_per_year + staff_annual, which the config itself
 # labelled "fallback only". s3.7 of the manuscript describes the per-customer
 # basis, so that is what the code now does. Set basis="capex_fraction" to
 # reproduce the previously published numbers.
 "opex":{"basis":"per_customer",
         "per_customer_year":80.0,     # SEforALL range $8-263/customer/yr
         "escalation_rate":0.05,
         "fuel_cost_per_litre":None,   # set per country
         "fuel_escalation_rate":0.05,
         "om_fraction_of_capex_per_year":0.04, "staff_annual":6000},
 "finance":{"discount_rate_real":0.12,"tax_rate":0.0,"project_life_years":20,
            "target_irr":0.15},
 "tariff":{"flat_rate_per_kwh":0.146,"bands":None,"telescopic":False,
           "daytime_discount_per_kwh":0.0,"daytime_window_hours":[9,16],
           "collection_rate":0.90},
 # Every reported scenario ran with diesel_kw = 0.0, so all published results
 # are solar + storage only. Stated here rather than left to a default, because
 # s3.4 describes diesel last in merit order and the reference list cites RURA
 # and EPRA fuel communiques. Either set this non-zero and re-run, or cut the
 # diesel material from the method and the references.
 "diesel_kw":0.0,
 "reliability":{"max_unmet_demand_fraction":0.05},
 "demand":{"annual_growth_rate":0.05},
 "sizing":{"pv_range":[10,900],"battery_range":[0,3000]},
 "scenarios":{"penetration_sweep":[0.0,0.5,1.0],
              "shiftable_fraction_sweep":[0.0,0.3,0.5],
              "tariffs":["flat","tou"],
              "tou_daytime_discount_sweep":[0.0,0.02]},
}

# --------------------------------------------------------------- appliances
# appliance -> (ownership_rate, watts, daily_minutes, use_window)
#
# OPTION (a): both countries' ownership rates are derived from their own MTF
# microdata by src/mtf_appliances.py. Nothing here is hand-typed except the
# assumptions, which are shared.
#
# v3 BUG: BASE_CFG["appliances"] was set once from a hand-typed Kenyan dict and
# COUNTRY_OVERRIDES carried only tariff and opex, so Rwanda ran on the Kenyan
# appliance stock. s3.2's Rwanda paragraph and s5.1's "the prediction is not
# borne out" described an experiment that never ran.
#
# SYMMETRY. Rwanda's SECTION_EF1 records daily usage hours; Kenya's M3 asset
# file records ownership flags only. Using Rwanda's measured hours while Kenya
# uses assumed ones would make part of the cross-country difference an artefact
# of data richness, and s4's claim that the cases differ only in tariff regime
# would fail. So:
#   HEADLINE    durations assumed for both, identical. Only measured ownership,
#               solar resource and tariff differ.
#   ROBUSTNESS  Rwanda on its MTF-measured durations, reported separately.
# Wattages and use windows are assumed for both and held identical.
APPLIANCE_DURATIONS = "assumed"      # "assumed" (headline) | "measured"

# Produced by:
#   python src/mtf_appliances.py --rwanda <dir> --kenya <dir> \
#       --rwanda-access-var <var> --durations assumed
# Paste the emitted dicts over the two placeholders below.
#
# INTERIM: the Kenyan values are the v3 hand-typed set, retained only so the
# pipeline runs before the extractor has been executed. They are close to but
# not identical to the MTF rates and must be replaced.
# MTF KEN_2016-2018, M3_Asset flags, rural WITH grid access (n=521),
# weighted by pw_final, denominator = ALL households (absence from the
# M3 owner roster counts as non-ownership, which is Rwanda's basis).
# Durations, wattages and windows assumed and IDENTICAL to Rwanda's.
APPLIANCES_KENYA = {
    "tv_colour":          (0.0959, 60, 240, "18:00-23:00"),
    "incandescent_bulb":  (0.0829, 25, 300, "18:00-23:00"),
    "vcd_dvd":            (0.0733, 30, 120, "18:00-22:00"),
    "radio":              (0.0675, 15, 300, "06:00-22:00"),
    "fluorescent_tube":   (0.044, 20, 300, "18:00-23:00"),
    "tv_flat":            (0.0421, 40, 240, "18:00-23:00"),
    "mobile_charger":     (0.039, 5, 120, "18:00-23:00"),
    "electric_iron":      (0.0348, 1000, 30, "07:00-20:00"),
    "smartphone_charger": (0.0319, 10, 120, "18:00-23:00"),
    "torch_lantern":      (0.0252, 3, 120, "18:00-23:00"),
    "cfl_bulb":           (0.0202, 15, 300, "18:00-23:00"),
    "led_bulb":           (0.0182, 7, 300, "18:00-23:00"),
}
APPLIANCES_KENYA_PROVENANCE = "MTF M3_Asset, rural+grid, pw_final, all-household denominator"

# MTF RWA_2022 SECTION_EF1, rural (HI04=2) AND grid-connected (C002=1),
# non-refugee, weighted by HH_WT. n = 1,115 households.
# C002 reproduces the published 51% national grid share (0.5065).
APPLIANCES_RWANDA = {
    "mobile_charger":     (0.715, 5, 120, "18:00-23:00"),
    "cfl_bulb":           (0.5406, 15, 300, "18:00-23:00"),
    "incandescent_bulb":  (0.3814, 25, 300, "18:00-23:00"),
    "torch_lantern":      (0.2361, 3, 120, "18:00-23:00"),
    "radio_cd_system":    (0.1973, 40, 180, "12:00-22:00"),
    "smartphone_charger": (0.1685, 10, 120, "18:00-23:00"),
    "radio":              (0.1477, 15, 300, "06:00-22:00"),
    "led_bulb":           (0.1057, 7, 300, "18:00-23:00"),
    "tv_colour":          (0.0688, 60, 240, "18:00-23:00"),
    "electric_iron":      (0.068, 1000, 30, "07:00-20:00"),
    "tv_flat":            (0.0494, 40, 240, "18:00-23:00"),
    "vcd_dvd":            (0.0255, 30, 120, "18:00-22:00"),
    "tv_bw":              (0.0186, 40, 240, "18:00-23:00"),
    "computer":           (0.0155, 100, 120, "08:00-22:00"),
    "fluorescent_tube":   (0.0147, 20, 300, "18:00-23:00"),
    "kettle":             (0.0127, 1500, 20, "06:00-21:00"),
    "refrigerator":       (0.0061, 100, 900, "00:00-23:59"),
}
APPLIANCES_RWANDA_PROVENANCE = "MTF SECTION_EF1, rural+grid (C002), HH_WT"

# ROBUSTNESS ONLY. Same ownership, but daily durations from the MTF's own
# E**C variables. Kenya has no equivalent, so using this in the headline
# run would make part of the cross-country gap an artefact of data
# richness. Report it as a separate sensitivity.
APPLIANCES_RWANDA_MEASURED = {
    "mobile_charger":     (0.715, 5, 120, "18:00-23:00"),
    "cfl_bulb":           (0.5406, 15, 376, "18:00-23:00"),
    "incandescent_bulb":  (0.3814, 25, 325, "18:00-23:00"),
    "torch_lantern":      (0.2361, 3, 101, "18:00-23:00"),
    "radio_cd_system":    (0.1973, 40, 290, "12:00-22:00"),
    "smartphone_charger": (0.1685, 10, 120, "18:00-23:00"),
    "radio":              (0.1477, 15, 319, "06:00-22:00"),
    "led_bulb":           (0.1057, 7, 371, "18:00-23:00"),
    "tv_colour":          (0.0688, 60, 226, "18:00-23:00"),
    "electric_iron":      (0.068, 1000, 30, "07:00-20:00"),
    "tv_flat":            (0.0494, 40, 210, "18:00-23:00"),
    "vcd_dvd":            (0.0255, 30, 120, "18:00-22:00"),
    "tv_bw":              (0.0186, 40, 232, "18:00-23:00"),
    "computer":           (0.0155, 100, 120, "08:00-22:00"),
    "fluorescent_tube":   (0.0147, 20, 426, "18:00-23:00"),
    "kettle":             (0.0127, 1500, 20, "06:00-21:00"),
    "refrigerator":       (0.0061, 100, 432, "00:00-23:59"),
}

COUNTRY_OVERRIDES = {
 # RURA, effective 1 Oct 2025. Telescopic bands. Diesel Rwf2,927/L, 6 Jun 2026.
 "rwanda": {"tariff":{"flat_rate_per_kwh":214/RWF_USD,
                      "bands":[(20, 89/RWF_USD),(50, 310/RWF_USD),(10**9, 369/RWF_USD)],
                      "telescopic":True},
            "opex":{"fuel_cost_per_litre":2927/RWF_USD*ISLAND_PREMIUM},
            "appliances":APPLIANCES_RWANDA},
 # EPRA Schedule of Tariffs 2023 (2026-29 review withdrawn Jun 2026).
 # Non-telescopic since Apr 2023. Diesel KES217.86/L, Nairobi, 15 Aug 2026.
 "kenya":  {"tariff":{"flat_rate_per_kwh":16.45/KES_USD,
                      "bands":[(30, 12.23/KES_USD),(100, 16.45/KES_USD),(10**9, 19.08/KES_USD)],
                      "telescopic":False},
            "opex":{"fuel_cost_per_litre":217.86/KES_USD*ISLAND_PREMIUM},
            "appliances":APPLIANCES_KENYA},
}
DISCOUNT_RATES = [0.08, 0.12, 0.15, 0.20]   # no published benchmark exists - sweep it

def country_cfg(site):
    """BASE_CFG merged with the country override, with the traps closed.

    Fails loudly on the two conditions that previously passed silently:
    a missing appliance set (Rwanda inheriting Kenya's) and an unset OPEX basis.
    """
    cfg = {k: (v.copy() if isinstance(v, dict) else v) for k, v in BASE_CFG.items()}
    for k, v in COUNTRY_OVERRIDES[site].items():
        cfg[k] = {**cfg[k], **v} if isinstance(v, dict) and isinstance(cfg.get(k), dict) else v
    if cfg.get("appliances") is None:
        raise ValueError(
            f"no appliance set defined for {site!r}. Option (a) requires it to "
            f"come from that country's own MTF microdata: run\n"
            f"  python src/mtf_appliances.py --{site} <dir> --durations "
            f"{APPLIANCE_DURATIONS}\n"
            f"and paste the emitted APPLIANCES_{site.upper()} into final_cfg.py. "
            "It must never be inherited from another country.")
    other = {"rwanda": "kenya", "kenya": "rwanda"}[site]
    other_set = COUNTRY_OVERRIDES[other].get("appliances")
    if other_set is not None and cfg["appliances"] is other_set:
        raise ValueError(
            f"{site!r} and {other!r} are sharing one appliance object. This is "
            "the v3 bug. Give each country its own MTF-derived set.")
    if cfg["opex"].get("basis") is None:
        raise KeyError("cfg['opex']['basis'] must be set explicitly")
    return cfg
