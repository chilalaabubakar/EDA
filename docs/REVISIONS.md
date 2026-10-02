# Revision plan: status, findings, and manuscript changes

## Real results — first full run (NASA POWER 2005–2024, 2 Oct 2026)

`python src/pipeline.py all`, headline Kenya ownership source = M3 (as
published). All tables: `results/tables/tables.md`. Against the current
draft, `manuscript_check.py` reports **64 mismatches**
(`results/manuscript_mismatches_current_draft.txt`) — that list is the edit
list for the manuscript.

| Claim | Draft | Now | Note |
|---|---|---|---|
| Resource: median GHI, spread | 1,744 / 2,076; 7.4% / 8.0% | **same** | reproduced exactly |
| LCOE 0 → 100% eCooking, Rwanda | $2.99 → $1.25 (−58%) | **$2.64 → $1.05 (−60%)** | 24-seed CI 59.9–60.0% |
| LCOE 0 → 100% eCooking, Kenya | $2.90 → $1.16 (−60%) | **$6.08 → $1.04 (−83%)** | 🔶 driven by M3 ownership: 2 kWh/month without cooking |
| Storage at 100%, Rwanda / Kenya | 640 / 600 kWh | **780 / 660 kWh** | worst-year constraint now enforced |
| Avoided storage, φ = 0.5 (24 seeds) | 28% / 27% | **21% (20–22) / 33% (32–34)** | single seed 42 gives 18% / 27% — quote the ensemble |
| ToU LCOE reduction (24 seeds) | 8–9% | **5.0% (4.8–5.2) / 6.8% (6.6–6.9)** | |
| Cooking peak with shifting, φ = 0.5 | — | **+32% (29–35)** | new: §2.1 transformer point |
| Cost-reflective multiple at 12% | 10.9× / 11.6× | **9.4× / 10.6×** | per-customer OPEX |
| … at 20% | 15.2× / 16.2× | **13.7× / 15.3×** | |
| Band penalty, Rwanda | 2.8× (15 → 60 kWh) | **2.1× yr 1 → 3.3× yr 20** | household p10–p90 yr 1: 1.9–2.3× |
| Band penalty, Kenya | 1.3× | **1.3× throughout** | |
| Operating subsidy, no grant | — | **$485 / $430 per connection·yr** | $145k / $129k per village·yr; with 95% grant $64 / $73 |
| $ per tCO₂ vs collected wood | — | **$780–6,200 / t** (fNRB 0.8–0.1) | vs ~$3–15 credits (indicative) |
| Staged expansion multiple | — | **7.2× / 8.3×** (vs 9.4× / 10.6×) | every year ≤ 5% unmet |
| Search vs full grid | — | **identical optimum** both cases | worst year 4.9%, lifetime 0.8% |
| Interannual (median-year design) | single year | LCOE p5–p95 within ±0.2%; **9 / 5 of 20 weather years breach 5%** (max 6.5%) | P10 sizing: same LCOE |
| Curtailment, 100% eCooking | not reported | **48% / 51%** of PV output | the case for a daytime discount |
| ToU break-even discount | "90 kWh per ¢" | **operator still gains at 12.5 ¢** (≈ free daytime power) | avoided storage is a step in d |
| ESMAP waterfall shares | — | discount rate 25%, growth reserve 31% / 23%, demand/connection 44% / 52% | load factor 30% (> ESMAP 22%) |

Reading the run:

* The core story holds and is now defensible: large utilisation gain,
  modest ToU gain, an order-of-magnitude viability gap that a capital grant
  cannot close, a regime-specific household penalty that grows over time.
* **Kenya's numbers hinge on the open ownership decision.** With M3 flags a
  Kenyan grid household uses ~2 kWh/month before cooking, so the zero-cooking
  LCOE is $6.08 and the reduction 83%. Run with `KENYA_OWNERSHIP_SOURCE =
  "core"` before finalising any cross-country comparison.
* Single-seed results can mislead (Rwanda φ = 0.3 and 0.5 tie at seed 42 on
  the 20 kWh grid); quote ensemble means with CIs in text.


Every item from the four-phase revision plan, what the code now does, what it
found, and the text the manuscript needs. Numbers marked **[run]** must come
from `python src/pipeline.py all` on real NASA POWER data — the development
environment could not reach power.larc.nasa.gov, so only synthetic smoke runs
were possible there. Never quote `results/synthetic/`.

Legend: ✅ done in code · ✍️ manuscript text to change · 🔶 your decision /
external input needed

---

## Phase 1 — Integrity

**Exit test** — `pytest` passes; the sweep reruns clean; identical scenarios
return identical LCOE to four decimals: ✅
`tests/test_reproducibility.py` (`test_sweep_reruns_clean` writes the sweep twice and
compares bytes; `test_identical_scenarios_identical_lcoe_to_four_decimals`).

| Item | Status |
|---|---|
| Thread a seed through RAMP; bit-identical test; re-run everything | ✅ seeded via stdlib `random` with state save/restore; memoised; `pipeline.py all` reruns everything |
| Map Rwandan MTF appliance codes; build a Rwandan vector | ✅ option (a), SECTION_EF1, rural + C002 grid-connected, HH_WT; reproduced exactly from microdata |
| One OPEX basis; grant on CAPEX only | ✅ per-customer; OPEX and **LCOE** both on gross CAPEX |
| Table 5 and abstract blended rates from simulated consumption, by year | ✅ `bands.py`; Table 5 restructured |
| Cut diesel, or run it | ✅ cut from dispatch, CAPEX, OPEX, config |
| Regression test: every manuscript number matches results | ✅ `manuscript_check.py` + `claims.yaml` + `tests/test_manuscript_numbers.py` |

### Findings beyond the plan (all fixed in code)

1. **The cooking model in v4 was not the one §3.8 describes.** v4 drew meal
   start hours *uniformly* within dayparts — the "flat load plateau" §3.8 says
   was replaced. Measured: DF 15.0, 67 W/household. Now normal about mealtime
   centres, calibrated by bisection to the MECS Kenya DF: **DF 9.76, peak
   20:00, 102 W/household, 1.00 kWh/day, worst-hour DF 7.41** (paper: 9.60 /
   20:00 / 104 W / 7.10). Table 2 regenerates from `cooking_validation_summary.csv`.
2. **The reliability constraint was not enforced as §3.5 states.** v4 screened
   year 20 against a *fresh* battery, then accepted on *lifetime-average*
   unmet. With an aged battery, final-year unmet ran at 7–12%. Now the worst
   project year must be ≤ 5% in the full simulation. Storage grows (synthetic
   example: Rwanda 640 → 740 kWh). **This is also the answer to "1–2% achieved
   against 5% suggests the search stops early"**: lifetime unmet is ~0.4% when
   the worst year binds at ~4.5%, because demand grows 5%/yr.
3. **Kenyan appliance ownership — two MTF sources disagree 3–10×.** 🔶 The M3
   asset flags (what v4 and §3.2 use) are nearly a strict subset of the core
   file's multi-select `m_m_3_group` (items M.15–M.40): of 712 households
   listing a mobile charger in the multi-select, 271 are "Yes" in M3. Rural
   grid-connected, weighted: colour TV 34.8% vs 9.6%, radio 39.3% vs 6.8%,
   bulb 25.6% vs 8.3%. Check Section M of the questionnaire to decide which is
   *ownership*. Switch: `final_cfg.KENYA_OWNERSHIP_SOURCE = "core"`. Until
   then the headline keeps M3 (as published) — and v4's claim that Rwanda's
   appliance stock is 2.9× Kenya's may be an artefact of M3.
   Detail: `data/processed/appliance_ownership_kenya_sources.csv`.
4. **§6.6 firewood sentence is probably right after all.** v4 concluded fuel
   codes 2 and 3 were different fuels. The microdata say otherwise: code 3 has
   **no quantity or price recorded for any of its 3,007 users** (the skip
   pattern of a collected fuel); code 2 carries prices (mean RWF 1,925). So
   2 = purchased, 3 = collected firewood. 🔶 Confirm labels in the
   questionnaire. ✍️ The 70.7% / 37.9% are **national**; for **rural**
   households (the relevant population) they are **82.5% / 44.8%**.
5. **The test-suite claim**: the manuscript says 28 tests; there are now 120+.

### ✍️ Manuscript text

- **§3.2** — replace the appliance paragraphs: ownership *measured* for both
  countries from their own MTF (Rwanda SECTION_EF1, n = 1,115 rural
  grid-connected; Kenya M3 or core multi-select, n = 521), weighted; wattages
  and use windows assumed and **identical** across countries; durations
  assumed and identical in the headline, Rwanda's measured hours a
  robustness case. Delete "daily use durations are not recorded in the MTF"
  (Rwanda records them). Report the cross-country comparison from
  `appliance_ownership_both.csv` [run].
- **§3.4** — delete "and diesel backup last"; add: "A single hybrid inverter
  is rated at 1.25 times the design-year peak load and caps total AC output."
  Delete the RURA/EPRA fuel-price sources.
- **§3.5** — "…meeting an unmet-demand constraint of 5% **in every project
  year**, evaluated on the full 20-year simulation with battery fade and
  replacement… Candidates are ranked on full-life LCOE; an exhaustive grid
  search on two scenarios returns the same optimum (§3.8)."
- **§3.8** — regenerate Table 2. Replace "Seed robustness" with the ensemble
  (Phase 2).
- **§5.1** — the "prediction not borne out" paragraph described a run in which
  Rwanda used Kenya's appliances. Rewrite against the real result [run].
- **Table 5** — paste `results/tables/table5.csv` (rows by project year).
  Synthetic illustration of the shape: Rwanda 2.1× in year 1 rising to 3.3×
  by year 20; Kenya 1.3× throughout. The abstract's "2.8-fold, $0.061 →
  $0.169" was the hand-picked 15 → 60 kWh case.
- **Reproducibility** — "covered by a 28-test suite" → the current count.
- **Figure 6 caption** says "tariff required for a 15% return", but the sweep
  targets *discount rate + 3 points*. Align one or the other
  (`viability.discount_sweep(hurdle_premium=…)`).

---

## Phase 2 — Defensibility

| Item | Status / output |
|---|---|
| Staged expansion or design-year 5/10 sensitivity; how the viability multiple moves | ✅ both — `expansion.csv` |
| Inverter sized to load | ✅ headline default |
| ESMAP reconciliation paragraph | ✅ `esmap_waterfall.csv`, `lcoe_components.csv`; ✍️ text below |
| Full grid vs two-stage search on two scenarios | ✅ `sizing_check.csv` — **identical optimum** in both (synthetic: 66–95 vs 5,467 evaluations) |
| Interannual resource variability | ✅ `interannual_summary.csv`, `interannual_by_year.csv` |
| 20+ seeds, CIs on the 8–9% and avoided-storage claims | ✅ 24 seeds, paired — `ensemble_summary.csv` |
| More ToU levels, or drop "90 kWh per US cent" | ✅ swept 0–12.5 ¢ — **drop it** (below) |
| Reframe §3.3 | ✍️ text below |

**Staged expansion (synthetic illustration).** Sizing to year 20 in one go
gives LCOE $0.92 and a 8.2× multiple; two stages (years 1–10, expanded at the
year-10 battery replacement) give $0.74 and 6.4×, with every year still
≤ 5% unmet. Single-stage designs for year 5 or 10 are cheaper still but
breach reliability badly later (40–48% worst-year unmet). The conclusion —
an order-of-magnitude gap — survives every sizing convention [run].

**The ToU slope cannot stand.** Under the modelled response, households shift
the full φ for *any* positive discount, so avoided storage is a step
function: 0.5 ¢ displaces exactly what 12.5 ¢ does (`tou_sweep.csv`,
`test_avoided_storage_is_a_step_function_of_discount`). "90 kWh per cent" is
a slope through two points of a step. ✍️ Replace §5.2's sentence and §6.5's
first "number" with: *avoided storage per unit φ* and the **break-even
discount** — the largest discount at which the operator's NPV still gains
(`tou_break_even.csv`) — which is a defensible regulatory parameter. The
elastic-response rows (`response = elastic`) are illustrative only.

**✍️ §3.3 reframed (draft).**
> φ is not estimated; we sweep it across 0, 0.3 and 0.5. Households shift
> only under a time-of-use tariff with a positive daytime discount; under a
> flat tariff φ is set to zero. This specification determines the *sign* of
> the substitution result by construction: the model cannot show that a
> discount causes shifting. What it shows is the *magnitude* of storage that
> shifting would displace if households responded as assumed, and what the
> discount would cost the operator in revenue. Because the response is
> modelled as a step, avoided storage does not depend on the size of the
> discount; we therefore report results per unit of φ and the largest
> discount at which the operator still gains, rather than a response per
> cent of discount. Establishing φ, and its dependence on the discount,
> requires a pilot.

**✍️ ESMAP reconciliation (draft, to sit in §5.1 after Table 3).**
> Our levelised costs sit well above ESMAP's reference of about $0.55/kWh at
> a 22% load factor [3]. Load factor is not the reason: the modelled systems
> run at roughly [run]% in year one. Three conventions account for most of
> the difference (Table Sx): the discount rate (12% real here against [run]),
> sizing for the worst year of a 20-year life with 5% annual demand growth —
> a growth reserve the plant carries for a decade — and demand per
> connection, which at [run] kWh/yr spreads per-connection costs
> (connection, its soft cost and per-customer O&M, together $[run]/kWh)
> thinly. Moving these one at a time towards benchmark conventions lowers
> LCOE by [run], [run] and [run]$/kWh respectively.
> 🔶 Confirm the ESMAP discount rate (`esmap.ESMAP_DISCOUNT_RATE`, set to 10%
> provisionally) and the load-factor anchors against the report.

**Interannual.** Report the 5–95% LCOE range over the 20 weather years, how
many weather years would breach the 5% constraint with the median-year
design, and what sizing to the P10 year costs [run]. ✍️ Update §4's
limitation and drop "single median year" as an unaddressed simplification.

**Ensemble.** ✍️ Every stochastic headline becomes "mean (95% CI)" over 24
paired seeds (`ensemble_summary.csv`); also report the 2.5–97.5 percentile
range — what a single realisation could have shown.

---

## Phase 3 — Contribution

| Item | Status / output |
|---|---|
| Size the operating subsidy: $/connection/yr, $/village, $/tCO₂ vs credits and RBF | ✅ third inverse solver; `operating_subsidy.csv`; 🔶 RBF level and credit prices need dated sources |
| Benchmark against Ringiti | ✅ code; 🔶 installed capacity/tariff must be filled from a citable source (`src/ringiti.py: RINGITI_ACTUAL`) |
| Report curtailment | ✅ every scenario row; `curtailment.csv`, `peak_and_curtailment.csv` |
| Peak effect of shifting | ✅ `peak_and_curtailment.csv` (cooking and system peak, flat vs ToU) |
| Household check on band assignment | ✅ `household_bands.csv`, `adoption_penalty_households.csv` |
| Optional: EPC in a household cost comparison | ✅ `household_cost.csv`; 🔶 purchased-wood spend, collection time, shadow wage |

**Operating subsidy (synthetic illustration of the outputs).** ~$415 per
connection per year (Rwanda), ~$125k per 300-household village per year,
falling to ~$59 per connection with a 95% capital grant — so capital grants
*reduce* but never remove the recurring commitment. Against collected
firewood, that is $600–5,300/tCO₂ depending on fNRB, two orders of magnitude
above indicative clean-cooking credit prices: carbon finance cannot close the
gap. ✍️ This turns §6.3's "the arithmetic points to operating subsidy" into a
costed recommendation [run]. 🔶 All emission factors are IPCC defaults or
useful-energy parity assumptions flagged in `operating_subsidy.CARBON`; the
credit-price range is indicative and must be replaced with a dated source.

**Peak effect (in the model already).** At φ = 0.5 the cooking peak rises
(v4: 30.0 → 39.0 kW; calibrated model: synthetic +28%) while storage falls.
✍️ Add to §5.2/§6.4 and tie to §2.1's transformer-overload concern: shifting
trades storage for coincident peak — relevant to distribution sizing.

**Household band check.** Under Rwanda's convex telescopic schedule, billing
the mean household *understates* revenue (Jensen) — strongly at low
penetration (synthetic: −12% to −41%), negligibly once every household cooks
electrically and sits above the lifeline. ✍️ Report the distribution of
household adoption penalties (p10–p90) alongside the mean-household factor.

---

## Phase 4 — Manuscript and submission package

| Item | Status |
|---|---|
| Author, affiliation, funding, COI, CRediT | 🔶 placeholders in `CITATION.cff`, `.zenodo.json`; manuscript front matter is yours |
| Public repository with DOI; data-availability statement; data-access path | ✅ `docs/DATA_ACCESS.md` (incl. draft statement); 🔶 enable the Zenodo–GitHub integration and tag a release to mint the DOI |
| Four reference placeholders | 🔶 see below |
| Figures: resolution, captions, colour-blind safety | ✅ `src/figures.py` (300 dpi PNG + PDF, validated CVD-safe palette, markers + direct labels, no twin axes); `figures/captions.md` |
| Cut to venue limit | ✅ `src/word_count.py`: body **5,760** words (+ 466 refs, 235 in tables); 🔶 confirm the AEF limit |
| Nomenclature table | ✅ `manuscript/nomenclature.md` |
| Abstract around corrected numbers | ✅ `manuscript/abstract_template.md`, rendered from results by `manuscript_tables.py --abstract` |

**Reference placeholders to resolve** (could not be verified from the
development environment — no access to Crossref):

- [5] Ramos-Galdo et al. (2025), *Energy for Sustainable Development*,
  S0973082625000419 — volume, article number/pages, DOI.
- [7] Bondo (Malawi) EPC study (2026), *Energy for Sustainable Development*,
  S0973082626000967 — authors, volume, pages, DOI.
- [15] SEforALL (2024) mini-grid CAPEX/OPEX benchmarking — exact title.
- [16] Sizing isolated mini-grids in Kenya (2024), S2667095X24000023 —
  authors, journal, DOI.

Also remove the diesel fuel-price sources from "Additional sources", and add
IPCC (2006) if the CO₂ figures are reported.

---

## Open decisions (🔶), in priority order

1. Kenyan ownership source: M3 flags vs core multi-select (questionnaire §M).
2. Run `pipeline.py all` on real NASA POWER data and paste the regenerated
   tables; then `manuscript_check.py` must report 0 mismatches.
3. Ringiti installed-system figures and source.
4. Dated sources: Rwanda RBF per-connection grant; clean-cooking credit prices;
   ESMAP discount rate.
5. Figure 6 target-IRR convention.
6. Venue word limit; author metadata; licence (MIT chosen provisionally).
