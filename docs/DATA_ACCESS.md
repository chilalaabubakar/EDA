# Data access

Nothing in `data/raw/` is in the repository. This page is the documented
route to every input, replacing the manual Colab upload step.

## 1. Solar resource — NASA POWER (open, scripted)

    python src/pipeline.py resource

Fetches hourly `ALLSKY_SFC_SW_DWN`, `T2M`, `WS2M` for 2005–2024 at both sites
in **local solar time** (`time-standard=LST`), writes a SHA-256 manifest
(`data/raw/power_manifest.json`) and the processed hourly files
`data/processed/resource_{rwanda,kenya}.csv`. Needs outbound HTTPS to
`power.larc.nasa.gov`. `load_resource.py` fails loudly if the diurnal peak is
not at hour 11–13 (the UTC/LST trap).

## 2. Kenya MTF 2016–2018 (open, CC-BY 4.0, scripted)

    python src/fetch_mtf.py kenya --out data/raw

From energydata.info (ESMAP CKAN), DOI 10.48529/230v-e158. The CSV
distribution (`KEN_2016-2018_MTF_v02_M_CSV`) can also be downloaded by hand
from the World Bank Microdata Library and unzipped into `data/raw/`.

## 3. Rwanda MTF 2022 (licensed, manual)

Not openly redistributable — which is why it is not, and must never be,
committed here.

1. https://microdata.worldbank.org/index.php/catalog/6429 (DOI 10.48529/x75v-fm71)
2. Register, submit the short use statement, accept the licence
3. Download `RWA_2022_MTF_v01_M_CSV.zip`
4. Unzip into `data/raw/` (it creates `household_survey_data/` and
   `community_and_public_institutions_surveys_data/`)

## 4. Derived inputs (committed)

`python src/pipeline.py mtf` (needs 2 and 3) regenerates, from the microdata:

| File | Used for |
|---|---|
| `data/processed/appliance_ownership_both.csv` | RAMP appliance sets in `src/final_cfg.py` |
| `data/processed/appliance_ownership_kenya_sources.csv` | Kenya M3 vs core multi-select check |
| `data/processed/cooking_dayparts_kenya.csv` | measured daypart split (s3.2) |
| `data/processed/fuel_use_rwanda.csv` | firewood statistics (s6.6) |
| `data/processed/mtf_checks.md` | human-readable summary |

These are aggregate statistics and may be published. The appliance sets are
also committed in `src/final_cfg.py`, so the model runs without the microdata.

## Data availability statement (draft for the manuscript)

> All code, parameters, tests and derived input tables are openly available at
> https://github.com/chilalaabubakar/EDA and archived at Zenodo
> (doi:10.5281/zenodo.XXXXXXX). Solar resource data are from NASA POWER and are
> retrieved by the published scripts. Household survey inputs derive from the
> World Bank Multi-Tier Framework surveys for Kenya 2016–2018
> (doi:10.48529/230v-e158; CC-BY 4.0) and Rwanda 2022
> (doi:10.48529/x75v-fm71), the latter available from the World Bank
> Microdata Library under its licence terms; the aggregate statistics derived
> from them are included in the repository. Load profiles use RAMP
> (doi:10.1016/j.energy.2019.04.097, EUPL-1.2).
