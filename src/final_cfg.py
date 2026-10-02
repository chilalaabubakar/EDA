"""Sourced configuration. Every value has a provenance comment."""
KES_USD, RWF_USD = 129.0, 1460.0    # RWF confirmed: RWF2,205/L = USD1.51 (RURA via GPP, 25 May 2026)

# CAPEX components: SEforALL 2024 benchmark shares applied to the AMDA
# all-in figure of $6,824/kWp (SSA 2020-24 average).
BASE_CFG = {
 "pv":{"temp_coeff_per_c":-0.004,"noct_c":45,"derate_factor":0.85,"degradation_rate":0.008},
 "battery":{"round_trip_efficiency":0.90,"depth_of_discharge":0.80,"cycle_life":3000,
            "replacement_year":10,"max_c_rate":0.5},
 # inverter_sizing (Phase 2): "load" = one hybrid inverter rated to the
 # design-year peak load x 1.25 headroom, capping total AC output (PV and
 # battery). "pv" = v4 convention, pv_kw / dc_ac_ratio, which over-sized the
 # inverter as PV grew with cooking load and never limited battery output.
 "bos":{"inverter_eff":0.97,"dc_ac_ratio":1.2,"inverter_sizing":"load",
        "inverter_headroom":1.25,"inverter_step_kw":5.0},
 "capex":{"pv_per_kw":1228,            # SEforALL solar share 18% x $6,824
          "battery_per_kwh":300,       # ESMAP mini-grid range $100-300/kWh, upper bound
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
         "om_fraction_of_capex_per_year":0.04, "staff_annual":6000},
 "finance":{"discount_rate_real":0.12,"tax_rate":0.0,"project_life_years":20,
            "target_irr":0.15},
 "tariff":{"flat_rate_per_kwh":0.146,"bands":None,"telescopic":False,
           "daytime_discount_per_kwh":0.0,"daytime_window_hours":[9,16],
           "collection_rate":0.90},
 # DIESEL CUT (Phase 1). Every reported scenario ran with diesel_kw = 0, so
 # the generator, fuel prices and fuel escalation were removed from the model.
 # s3.4 ("diesel backup last") and the RURA/EPRA fuel-price sources go too.
 # Enforced on the WORST project year of the full simulation (s3.5), not on
 # the lifetime average. See sizing.py.
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

# ALTERNATIVE KENYAN SOURCE - Phase 1 data check (src/mtf_checks.py).
# Same households (rural, grid-connected, n=521), same weights and
# denominator, but ownership read from the CORE file's multi-select
# m_m_3_group (questionnaire items M.15-M.40) instead of the M3 asset flags.
# M3 "Yes" is close to a strict subset of the multi-select (mobile charger:
# 271 of 712 multi-select owners flagged in M3), and the two disagree by
# 3-10x. Which one measures ownership must be settled against Section M of
# the questionnaire. The headline uses M3 (what v4 and s3.2 used) until then;
# switch KENYA_OWNERSHIP_SOURCE to "core" to run the alternative.
APPLIANCES_KENYA_CORE = {
    "radio":              (0.3931, 15, 300, "06:00-22:00"),
    "tv_colour":          (0.348, 60, 240, "18:00-23:00"),
    "incandescent_bulb":  (0.2557, 25, 300, "18:00-23:00"),
    "vcd_dvd":            (0.2025, 30, 120, "18:00-22:00"),
    "mobile_charger":     (0.1956, 5, 120, "18:00-23:00"),
    "fluorescent_tube":   (0.1722, 20, 300, "18:00-23:00"),
    "tv_flat":            (0.1619, 40, 240, "18:00-23:00"),
    "smartphone_charger": (0.1579, 10, 120, "18:00-23:00"),
    "electric_iron":      (0.1201, 1000, 30, "07:00-20:00"),
    "cfl_bulb":           (0.116, 15, 300, "18:00-23:00"),
    "led_bulb":           (0.1062, 7, 300, "18:00-23:00"),
    "refrigerator":       (0.0755, 100, 900, "00:00-23:59"),
    "torch_lantern":      (0.0746, 3, 120, "18:00-23:00"),
    "computer":           (0.0351, 100, 120, "08:00-22:00"),
    "fan":                (0.0199, 50, 300, "11:00-22:00"),
    "kettle":             (0.0134, 1500, 20, "06:00-21:00"),
    "tv_bw":              (0.0083, 40, 240, "18:00-23:00"),
}
APPLIANCES_KENYA_CORE_PROVENANCE = "MTF core m_m_3_group, rural+grid, pw_final, all-household denominator"
KENYA_OWNERSHIP_SOURCE = "m3"        # "m3" (headline, as published) | "core"

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
 # RURA, effective 1 Oct 2025. Telescopic bands.
 "rwanda": {"tariff":{"flat_rate_per_kwh":214/RWF_USD,
                      "bands":[(20, 89/RWF_USD),(50, 310/RWF_USD),(10**9, 369/RWF_USD)],
                      "telescopic":True},
            "appliances":APPLIANCES_RWANDA},
 # EPRA Schedule of Tariffs 2023 (2026-29 review withdrawn Jun 2026).
 # Non-telescopic since Apr 2023.
 "kenya":  {"tariff":{"flat_rate_per_kwh":16.45/KES_USD,
                      "bands":[(30, 12.23/KES_USD),(100, 16.45/KES_USD),(10**9, 19.08/KES_USD)],
                      "telescopic":False},
            "appliances":APPLIANCES_KENYA},
}
DISCOUNT_RATES = [0.08, 0.12, 0.15, 0.20]   # no published benchmark exists - sweep it

def country_cfg(site, kenya_source=None):
    """BASE_CFG merged with the country override, with the traps closed.

    kenya_source: "m3" | "core" | None (-> KENYA_OWNERSHIP_SOURCE), resolved at
    call time so the switch cannot be silently ignored.

    Fails loudly on the two conditions that previously passed silently:
    a missing appliance set (Rwanda inheriting Kenya's) and an unset OPEX basis.
    """
    cfg = {k: (v.copy() if isinstance(v, dict) else v) for k, v in BASE_CFG.items()}
    for k, v in COUNTRY_OVERRIDES[site].items():
        cfg[k] = {**cfg[k], **v} if isinstance(v, dict) and isinstance(cfg.get(k), dict) else v
    src = kenya_source or KENYA_OWNERSHIP_SOURCE
    if site == "kenya" and src == "core":
        cfg["appliances"] = APPLIANCES_KENYA_CORE
    elif site == "kenya" and src != "m3":
        raise ValueError(f"unknown kenya_source {src!r}")
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
