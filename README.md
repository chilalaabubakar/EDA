# Case Study 4: healthcare electrification in Uganda

Where should Uganda's Ministry of Health spend US$1,000,000 to electrify health facilities?
This notebook answers that with [Energy Access Explorer](https://www.energyaccessexplorer.org/) (EAE) data.

**Notebook:** [`Uganda_Healthcare_Electrification_EAE.ipynb`](Uganda_Healthcare_Electrification_EAE.ipynb)

## What it does

1. **Gets the layers from EAE.** It reads EAE's open catalogue API (`api.energyaccessexplorer.org`) and
   downloads each layer from WRI's public storage. Every layer comes on EAE's own 1 km grid.
2. **Describes the facilities.** It uses the 4,938 health facilities in EAE (WRI and Ministry of Health,
   2023), with electrification status, modelled electricity demand and catchment population for each.
3. **Reproduces EAE's prioritisation.** It reproduces the Demand, Supply, Energy Access Potential and
   Assistance Need indexes, and the district ranking, line by line from the web tool's code.
   `tools/eae_check.js` runs the live tool with the same settings and the notebook compares the two.
   They match: all 146 districts are in the same class and the top 20 ranks are identical.
4. **Ranks districts and tests the ranking.** It ranks districts on the Assistance Need Index, then checks
   the ranking under other indexes, filters and 500 random weightings.
5. **Costs and allocates the budget.** Each facility is costed for solar PV with batteries, using sourced
   costs. The US$1,000,000 is allocated four ways: need first, value for money, high-need cheapest first,
   and a recommended plan that powers maternity wards first.
6. **Tests sensitivity.** It varies costs, compares need with value for money, and asks what changes if
   UEDCL connects the facilities nearest the grid.

## Run it

Locally (Python 3.10+):

```bash
pip install -r requirements.txt
```

```bash
jupyter nbconvert --to notebook --execute --inplace Uganda_Healthcare_Electrification_EAE.ipynb
```

Colab: open the notebook from GitHub and run all cells. The first cell installs anything missing.
A full run takes about a minute; the layers (about 10 MB) are cached in `data/eae/`, which git ignores.

To re-check against the live EAE tool (needs Node and Playwright with Chromium):

```bash
node tools/eae_check.js
```

All assumptions (EAE layers, ranges and weights, costs, eligibility) are in the notebook's first code cells.

## All EAE layers for Uganda, saved

`tools/download_eae_layers.py` downloads every Uganda layer in EAE (38 datasets) into `eae_data/`:

- `rasters/`: GeoTIFF on EAE's 1 km grid, EPSG:3857.
- `vectors/`: GeoJSON.
- `csv/`: every point layer as a table (lon/lat plus attributes) and every line layer with its length.
  Also one summary table per admin level (region, subregion, district, county, subcounty), with population,
  wealth, solar, wind, land cover, grid distance and facility counts by electrification status.
- `catalogue.csv`: source, date, licence and citation for each layer.

The CSVs and catalogue are committed. The rasters and GeoJSON (about 100 MB) are not: rebuild them with

```bash
python tools/download_eae_layers.py
```

It works for other EAE countries too (`--geography Kenya --out eae_kenya`). Check each layer's licence in
`catalogue.csv` before sharing. Most are CC BY 4.0; the Relative Wealth Index and crop layers are
non-commercial; Protected Areas (WDPA) must not be redistributed.

## Outputs

- `outputs/figures/`: a screenshot of the live EAE tool and seven report-ready figures (facility map, index maps, top-district drivers,
  robustness, plan map, cost sensitivity, need vs value for money).
- `outputs/tables/`: every table behind them as CSV. `key_numbers.json` holds the headline numbers.
  `eae_settings.csv` lists the exact settings to enter in the EAE web tool.
- `outputs/validation/`: the live EAE tool's district scores and the settings used to get them.

## Sources

- Sinclair-Lecaros, S., Mentis, D., Mulepo C.S., E., Falchetta, G. and Stevanato, N. (2023). *A GIS-based
  demand assessment methodology to estimate electricity requirements for health care facilities: a case
  study for Uganda.* World Resources Institute. doi:10.46830/writn.21.00093
- Energy Access Explorer, World Resources Institute: health facilities (Ministry of Health and WRI, 2023),
  distribution lines (Energy Sector GIS Working Group, 2024), population (WorldPop), Relative Wealth Index
  (Meta), GHI (Global Solar Atlas), boundaries (UBOS). Full list with citations in
  `outputs/tables/data_manifest.csv`.
- WHO, World Bank, IRENA and SEforALL (2023). *Energizing Health: Accelerating Electricity Access in
  Health-Care Facilities.* Table 3 (system design), Box 4.1 (IRENA and SELCO costs and O&M), Table 4.1.
- Green Empowerment, Medical Teams International and Mandulis Energy (2023). *Energizing Healthcare in
  Uganda: 2023 Impact Report.* Equipment and installation costs for three Ugandan health-centre systems.
