# eCooking mini-grid model

Code for *Cheaper kilowatt-hours, unviable projects: electric cooking, tariff
structure and the mini-grid viability gap in Rwanda and Kenya* (African
Energy Futures, Nairobi, October 2026).

A stochastic household demand model (RAMP appliances from Multi-Tier
Framework microdata, plus calibrated discrete cooking events), an hourly
PV–battery dispatch over a 20-year life, a least-cost sizing search under a
worst-year reliability constraint, and a project financial model with three
inverse solvers: capital grant, cost-reflective tariff and operating subsidy.
Nkombo Island (Rwanda) and Ringiti Island (Kenya), 300-household archetypes.

**Revision status, findings and the manuscript changes they require:
[`docs/REVISIONS.md`](docs/REVISIONS.md).**

## Quick start

```bash
pip install -r requirements.txt            # pinned: RAMP 0.5.0 needs numpy<2
python -m pytest -q                        # ~1 min
python src/pipeline.py all --synthetic --quick   # smoke run, no network
```

Real results (needs outbound HTTPS to power.larc.nasa.gov):

```bash
python src/pipeline.py resource            # NASA POWER 2005-2024, local solar time
python src/pipeline.py all                 # every result, table and figure -> results/
python src/manuscript_tables.py --abstract # abstract rendered from results
python src/manuscript_check.py manuscript/private/<draft>.docx   # 0 mismatches before submission
                                           # uses manuscript/private/claims.yaml if present
```

Or run `notebooks/eCooking_AEF_Colab_v5.ipynb` in Colab.

## Pipeline

`python src/pipeline.py <step | phase1 | phase2 | phase3 | phase4 | all>`

| Phase | Step | Output (`results/`) |
|---|---|---|
| data | `resource`, `mtf` | `data/processed/` |
| 1 | `sweep` | `scenarios_*.csv`, `frontier_both.csv` |
| 1 | `bands` | `tariff_band_recomputed.csv` (Table 5, by project year) |
| 1 | `validation` | `cooking_validation_summary.csv` (Table 2) |
| 1 | `viability` | `viability.csv`, `discount_sweep.csv` (Table 6) |
| 1 | `tables` | `tables/table{1..7}.csv`, `tables.md`, `headline_numbers.csv` |
| 2 | `expansion` | design-year 5/10/20 and staged expansion |
| 2 | `sizing_check` | search vs exhaustive grid |
| 2 | `interannual` | 20 weather years, chronological, P10 sizing |
| 2 | `ensemble` | 24-seed CIs |
| 2 | `tou_sweep` | discount sweep, break-even discount |
| 2 | `esmap` | LCOE waterfall and components |
| 3 | `operating_subsidy` | $/connection, $/village, NPV, $/tCO₂ |
| 3 | `peaks` | curtailment, peak effect of shifting |
| 3 | `household_bands` | household vs mean-household billing |
| 3 | `ringiti` | benchmark against the installed plant |
| 3 | `household_cost` | EPC + bill vs firewood |
| 4 | `figures` | `figures/fig{1..6}*.{png,pdf}`, `fig_esmap`, `fig_tou_operator` |

`--synthetic` writes to `results/synthetic/` and must never be quoted.

## Layout

```
src/            model, demand, sizing, analyses, pipeline (flat modules)
tests/          regression tests, one file per phase plus core physics
data/processed/ aggregate MTF-derived inputs (committed)
data/raw/       survey microdata - NOT committed (docs/DATA_ACCESS.md)
manuscript/     claims.yaml, abstract template, nomenclature;
                private/ (gitignored) holds drafts for the number check
figures/        self-sufficient captions
notebooks/      v4 (historical) and v5 (driver)
docs/           REVISIONS.md, DATA_ACCESS.md
```

## Data

Survey microdata are not redistributed: Rwanda MTF 2022 is licensed by the
World Bank. See [`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md) for the access
route to every input and a draft data-availability statement.

## Licence and citation

MIT (see `LICENSE`); cite via `CITATION.cff`. RAMP is EUPL-1.2 and is used
as a dependency, not redistributed.
