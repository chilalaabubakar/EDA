# eCooking mini-grid model

Code and results for *Electric cooking, tariff design and subsidy needs for
solar mini-grids in Rwanda and Kenya*, by Abubakar Chilala.

The model asks what happens to a solar mini-grid when village households
start cooking with electricity. It covers two island villages, Nkombo (Rwanda)
and Ringiti (Kenya), each modelled as 300 households. For each case it works
out the least-cost solar and battery system, the cost of each unit of
electricity, what households pay under each country's tariff, and the subsidy
the operator would need. One command rebuilds every table, figure and number
in the paper from public data.

## What the model does

1. **Household demand** (`src/load_builder.py`, `src/mtf_appliances.py`):
   appliance loads from the World Bank Multi-Tier Framework surveys, simulated
   with RAMP, plus electric cooking as separate meals (`src/validate_cooking.py`
   checks them against metered data).
2. **Hourly operation** (`src/model.py`): solar, battery and load for every
   hour of a 20-year project, with battery ageing and replacement.
3. **Least-cost sizing** (`src/sizing.py`, `src/run_scenarios.py`): the cheapest
   solar and battery size that leaves at most 5% of demand unserved in every
   year.
4. **Finance and tariffs** (`src/model.py`, `src/viability.py`,
   `src/operating_subsidy.py`): levelised cost, net present value, Rwanda's and
   Kenya's banded tariffs, and the capital grant, flat tariff or operating
   subsidy needed to close the funding gap.

`src/pipeline.py` runs everything in order. Settings are in `params.yaml` and
`src/final_cfg.py`.

## Quick start

Python 3.11 is required, because RAMP 0.5.0 needs numpy 1.26. With
[uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.11 .venv && . .venv/bin/activate
uv pip install -r requirements.txt
python -m pytest -q                      # 127 tests, about 1 minute
python src/pipeline.py all --synthetic --quick   # smoke run, no internet
```

Full results (needs internet access to power.larc.nasa.gov):

```bash
python src/pipeline.py resource          # NASA POWER weather 2005-2024 (~2 min)
python src/pipeline.py all               # every result -> results/ (~20 min)
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
| phase1 | `tables` | `tables/table1..7.csv`, `tables.md`, `headline_numbers.csv` |
| phase2 | `expansion` | `expansion.csv` (design years and staged expansion) |
| phase2 | `sizing_check` | `sizing_check*.csv` (search against the full grid) |
| phase2 | `interannual` | `interannual_*.csv` (20 weather years) |
| phase2 | `ensemble` | `ensemble_*.csv` (24 random seeds) |
| phase2 | `tou_sweep` | `tou_sweep.csv`, `tou_break_even.csv` |
| phase2 | `esmap` | `esmap_waterfall.csv`, `lcoe_components.csv` |
| phase3 | `operating_subsidy` | `operating_subsidy.csv` |
| phase3 | `peaks` | `peak_and_curtailment.csv`, `curtailment.csv` |
| phase3 | `household_bands` | `household_bands.csv` |
| phase3 | `ringiti` | `ringiti_benchmark.csv` |
| phase3 | `household_cost` | `household_cost.csv` |
| phase4 | `final_tables` | tables again, once every analysis has run |
| phase4 | `figures` | `figures/*.png`, `figures/*.pdf` |

## Where each result in the paper comes from

| In the paper | File in `results/` |
|---|---|
| Table 1, tariffs | `tables/table1.csv` |
| Table 2, cooking load check | `tables/table2.csv` |
| Table 3, system size and cost | `tables/table3.csv` |
| Table 4, price paid by households | `tables/table5.csv` |
| Table 5, cost-reflective tariff | `tables/table6.csv` |
| Table 6, operating subsidy | `tables/table7.csv` |
| Fig. 1, model structure | `figures/fig1_model_structure.*` |
| Fig. 2, cost compared with ESMAP | `figures/fig_esmap.*` |
| Fig. 3, daytime discount | `figures/fig_tou_operator.*` |
| Fig. 4, price per unit by use | `figures/fig5_blended_tariff.*` |
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
  (`data/processed/resource_summary.csv`).
- **Household surveys:** World Bank Multi-Tier Framework surveys for Kenya
  2016 to 2018 (doi:10.48529/230v-e158, CC-BY 4.0) and Rwanda 2022
  (doi:10.48529/x75v-fm71). The Rwanda survey is licensed and is never
  committed (`data/raw/` is ignored). Only aggregate statistics are in
  `data/processed/`, and they are enough to run the model.

[`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md) explains how to get every input.
[`docs/REVISIONS.md`](docs/REVISIONS.md) records how the model was revised.

## Layout

```
src/            model, demand, sizing, finance, analyses, figures, pipeline
tests/          127 automated tests (physics, finance, sizing, reproducibility)
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
