# Energy Access Explorer layers: Uganda

Downloaded 2026-11-06 from Energy Access Explorer (World Resources Institute), https://www.energyaccessexplorer.org/, with `download_eae_layers.py`.

- `rasters/`: GeoTIFF on EAE's 1 km grid, EPSG:3857. Band 1 = value EAE maps, band 2 = area-weighted sum, band 3 = area-weighted average. Layers built from points or lines hold distance (km) to the nearest feature.
- `vectors/`: GeoJSON in lon/lat (CRS84).
- `csv/`: point and line layers as tables, and one summary table per admin level.
- `catalogue.csv`: source, date, licence, suggested citation and original download link for every layer.

## Licences

Each layer keeps its own licence (column `licence` in `catalogue.csv`). Cite each layer you use with its suggested citation, plus Energy Access Explorer.

- **non-commercial use only, with attribution**: Crops Irrigated, Crops Rainfed, Relative Wealth Index
- **open, with attribution**: region, subregion, county, district, subcounty, Distribution Lines, Distribution Lines Planned, Transformers, Financial Services, Global Horizontal Irradiation, Health facilities, Crop Cover (%), Forest Cover (%), Urban Cover (%), Inland Water Cover (%), Wetlands Cover (%), Rangelands Cover (%), Minigrids, Nighttime Lights, Outline, Population Count, Power plants, Investment Prospectus PURE Projects, Education facilities, Operating Transmission Lines, Planned Transmission Lines, Windspeed at 200 meters, Wind speed at 150 meters, Windspeed at 100 meters, Windspeed at 50 meters, Windspeed at 10 meters
- **restricted: WDPA terms, do not redistribute**: Protected Areas
- **unknown: check the source before sharing**: Landforms
