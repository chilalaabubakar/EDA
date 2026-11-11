# eCooking mini-grid model

Code and results for *Electric cooking, tariff design and subsidy needs for
solar mini-grids in Rwanda and Kenya*, by Abubakar Chilala.

The model asks what happens to a solar mini-grid when village households
start cooking with electricity. It covers two model villages of 300
households, placed on Nkombo Island (Rwanda) and Ringiti Island (Kenya). For
each share of households cooking it works out the least-cost solar and battery
system, the cost of each unit of electricity, what households pay under a
tariff, and the subsidy the operator would need. Tariffs are scenarios: each
country's national tariff, site-specific tariffs of the kind private
mini-grids charge, and the break-even tariff. The share of households cooking
is an input and does not respond to price. One command rebuilds every table,
figure and number in the paper from public data.

The main measure of what cooking costs whoever funds the operator is the
**extra operating subsidy per cooking household**: the subsidy with cooking
minus the subsidy without, divided by the number of cooking households. The
levelised cost is not that measure. It falls with cooking mostly because
per-connection costs are divided by more kilowatt-hours, while the operator's
loss grows.

## What the model does

1. **Household demand** (`src/load_builder.py`, `src/mtf_appliances.py`):
   appliance loads from the World Bank Multi-Tier Framework surveys, simulated
   with RAMP, plus electric cooking as separate meals (`src/validate_cooking.py`
   checks them against metered data).
2. **Hourly operation** (`src/model.py`): solar, battery and load for every
   hour of a 20-year project, with battery ageing and replacement.
3. **Least-cost sizing** (`src/sizing.py`, `src/expansion.py`,
   `src/run_scenarios.py`): the cheapest solar and battery system that leaves
   at most 5% of demand unserved in every year. It is built in two stages:
   for years 1 to 10, then enlarged when the battery is replaced.
4. **Finance and tariffs** (`src/model.py`, `src/viability.py`,
   `src/operating_subsidy.py`): levelised cost, net present value, the
   break-even tariff, the operating subsidy that closes the gap, and the part
   of that subsidy due to cooking, under each tariff scenario.
5. **Sensitivity** (`src/sensitivity.py`): the system re-sized for a low and a
   high value of each main input, three alternative designs (single stage,
   commercial anchor load, backup diesel generator), and a bridge from the
   base case of the first submission to the current one.

### Base case

| Choice | Value |
|---|---|
| Build | two stages (years 1 to 10, 11 to 20); single stage tested |
| Cooking energy per household | 1.0 kWh a day, no growth (0.87 and 2.0 tested) |
| Appliance demand | grows 2% a year (0 and 5% tested) |
| Operating cost | US$60 per customer per year + 2% a year of installed plant cost, constant in real terms |
| Discount rate | 12% real (8, 15, 20% tested); target return equal to the discount rate |
| Money | constant 2025 US$ |
| Operating subsidy | the same amount every year in real terms; its present value equals the operator's loss |

`src/pipeline.py` runs everything in order. Settings are in `params.yaml` and
`src/final_cfg.py`.

## Quick start

Python 3.11 is required, because RAMP 0.5.0 needs numpy 1.26. With
[uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.11 .venv && . .venv/bin/activate
uv pip install -r requirements.txt
python -m pytest -q                      # 158 tests, about 2 minutes
python src/pipeline.py all --synthetic --quick   # smoke run, no internet
```

Full results (needs internet access to power.larc.nasa.gov):

```bash
python src/pipeline.py resource          # NASA POWER weather 2005-2024 (~2 min)
python src/pipeline.py all               # every result -> results/ (~25 min)
python src/pipeline.py all --resume      # carry on after an interruption
python src/manuscript_tables.py --abstract   # abstract numbers from results/
```

`--synthetic` writes test outputs to `results/synthetic/`. They are for
checking the code only and must never be quoted.

### Google Colab

Open `notebooks/eCooking_AEF_Colab_v5.ipynb` and run the cells in order. It
sets up Python 3.11 with uv (Colab's own Python is 3.13), keeps results and
weather data on Google Drive, and resumes where it stopped if the runtime
resets. On a standard Colab machine the full run takes about 25 minutes.

## Pipeline steps

`python src/pipeline.py <step | phase1 | phase2 | phase3 | phase4 | all>`

| Group | Step | Output (`results/`) |
|---|---|---|
| data | `resource`, `mtf` | `data/processed/` |
| phase1 | `sweep` | `scenarios_*.csv`, `frontier_both.csv` |
| phase1 | `bands` | `tariff_band_recomputed.csv` |
| phase1 | `validation` | `cooking_validation_summary.csv` |
| phase1 | `viability` | `viability.csv`, `discount_sweep.csv` |
| phase1 | `tables` | `tables/table*.csv`, `tables.md`, `headline_numbers.csv` |
| phase2 | `expansion` | `expansion.csv` (single-stage designs against the two-stage build) |
| phase2 | `sizing_check` | `sizing_check*.csv` (search against the full grid, both stages) |
| phase2 | `interannual` | `interannual_*.csv` (20 weather years; the median-year design as comparison) |
| phase2 | `ensemble` | `ensemble_*.csv` (24 random seeds, share of supper cooking moved 0.1 to 0.5) |
| phase2 | `tou_sweep` | `tou_sweep.csv`, `tou_break_even.csv` |
| phase2 | `components` | `lcoe_components.csv` (levelised cost by cost line) |
| phase2 | `sensitivity` | `sensitivity.csv`, `structural.csv`, `bridge.csv` (inputs, alternative designs, bridge from the first submission) |
| phase3 | `operating_subsidy` | `operating_subsidy.csv`, `burden.csv` (subsidy by share cooking and the extra per cooking household), `carbon.csv` |
| phase3 | `tariff_scenarios` | `tariff_scenarios.csv` (operator's result and household bill under each tariff) |
| phase3 | `peaks` | `peak_and_curtailment.csv`, `curtailment.csv` |
| phase3 | `household_bands` | `household_bands.csv` |
| phase3 | `cost_vs_price` | `cost_vs_price.csv`, `bill_example.csv` (why cost per kWh falls while the price paid per kWh rises) |
| phase3 | `ringiti` | `ringiti_benchmark.csv` (model against the installed Ringiti plant) |
| phase3 | `household_cost` | `household_cost.csv` |
| phase3 | `daytime_share` | `cooking_daytime_share.csv` (cooking in the discount window, by φ) |
| phase3 | `site_check` | `site_ownership_check.csv` (ownership scaled to the islands' census areas) |
| phase3 | `kenya_check` | `kenya_ownership_check.csv` (Kenya under both survey ownership questions, and five more years of growth) |
| phase4 | `final_tables` | tables again, once every analysis has run |
| phase4 | `figures` | `figures/*.png`, `figures/*.pdf` |

## Where each result in the paper comes from

| In the paper | File in `results/` |
|---|---|
| Table 1, tariffs | `tables/table1.csv` |
| Table 2, calibration targets and independent checks | `tables/table2.csv` |
| Table 3, system size and cost | `tables/table3.csv` |
| Table 4, loss, subsidy and extra subsidy per cooking household | `tables/table5.csv` |
| Table 5, tariff scenarios | `tables/table6.csv` |
| Fig. 1, model structure | `figures/fig1_model_structure.*` |
| Fig. 2, cost and price per kWh by share cooking | `figures/fig_cost_vs_price.*` |
| Fig. 3, price per unit by use | `figures/fig5_blended_tariff.*` |
| Fig. 4, daytime discount | `figures/fig_daytime.*` |
| Fig. 5, sensitivity to inputs | `figures/fig_sensitivity.*` |
| Table S2, sensitivity to inputs | `tables/tableS2.csv` |
| Table S3, alternative designs | `tables/tableS3.csv` |
| Table S4, grants; break-even tariff by discount rate | `tables/tableS4a.csv`, `tables/tableS4b.csv` |
| Table S5, daytime discount by share moved | `tables/tableS5.csv` |
| Table S6, subsidy per tonne of CO2 | `tables/tableS6.csv` |
| Table S7, price paid by year | `tables/table4.csv` |
| Table S8, further checks | `sizing_check.csv`, `interannual_summary.csv`, `expansion.csv`, `site_ownership_check.csv`, `kenya_ownership_check.csv`, `adoption_penalty_households.csv`, `cooking_daytime_share.csv`, `ringiti_benchmark.csv` |
| Bridge from the first submission | `tables/tableR1.csv`, `bridge.csv` |
| Abstract and text numbers | `tables/headline_numbers.csv` and the CSVs above |

Captions for every figure file are in `figures/captions.md`.

## Checking a manuscript against the results

```bash
python src/manuscript_check.py manuscript/private/<draft>.docx
```

This compares every table cell and headline number in a draft with
`results/` and lists each mismatch. Drafts stay in `manuscript/private/`,
which git ignores, so unpublished text never reaches this public repository.
A draft can carry its own `manuscript/private/claims.yaml` (text patterns and
table order), which is used in place of `manuscript/claims.yaml`.

## Data

- **Weather:** NASA POWER hourly data for 2005 to 2024, in local solar time,
  downloaded by `src/fetch_power.py`. Only a yearly summary is committed
  (`data/processed/resource_summary.csv`). Systems are sized and costed on
  each site's design weather year (`design_year` in `params.yaml`: the year
  hardest for the full-cooking system), so they meet the 5% unserved-demand
  limit under all 20 weather years. Sizing on the median year instead is the
  comparison in `interannual_summary.csv`.
- **Census checks:** Rwanda 2022 census (NISR) and Kenya 2019 census (KNBS)
  appliance ownership for the islands' own areas, and the Kenya 2022 DHS,
  are used only in the robustness checks (`src/site_ownership_check.py`,
  `src/kenya_ownership_check.py`). The figures are typed into those files
  with their table references.
- **Household surveys:** World Bank Multi-Tier Framework surveys for Kenya
  2016 to 2018 (doi:10.48529/230v-e158, CC-BY 4.0) and Rwanda 2022
  (doi:10.48529/x75v-fm71). The Rwanda survey is licensed and is never
  committed (`data/raw/` is ignored). Only aggregate statistics are in
  `data/processed/`, and they are enough to run the model.

[`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md) explains how to get every input.
[`docs/REVISIONS.md`](docs/REVISIONS.md) records how the model was revised,
including the changes made in response to peer review.

## Layout

```
src/            model, demand, sizing, finance, analyses, figures, pipeline
tests/          158 automated tests (physics, finance, sizing, reproducibility,
                one per review point in test_review_revision.py)
params.yaml     run settings, sites, weather years
data/processed/ aggregate survey statistics and the weather summary
data/raw/       survey microdata and raw downloads (not committed)
results/        every result, table and figure
notebooks/      v5 Colab notebook (current) and v4 (historical)
manuscript/     claims.yaml, abstract template, nomenclature;
                private/ (not committed) holds drafts
figures/        figure captions
docs/           data access, revision record
```

## Licence and citation

Code: MIT licence, copyright Abubakar Chilala (`LICENSE`). Please cite with
`CITATION.cff`. RAMP (EUPL-1.2) is installed as a dependency and is not
included here.
