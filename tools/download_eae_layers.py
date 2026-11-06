"""Download every Energy Access Explorer layer for a country and save CSV versions.

EAE's catalogue is a public API (api.energyaccessexplorer.org) and its processed layers are public
files on WRI's storage. This script saves, for one geography:

  rasters/   every gridded layer as GeoTIFF on EAE's 1 km grid (EPSG:3857). Band 1 is the value
             EAE maps, band 2 the area-weighted sum, band 3 the area-weighted average.
             Layers built from points or lines hold the distance (km) to the nearest feature.
  vectors/   every point, line and boundary layer as GeoJSON (lon/lat, CRS84)
  csv/       points_<layer>.csv   one row per point, lon/lat plus all attributes
             lines_<layer>.csv    one row per line, attributes plus length in km
             admin_<tier>.csv     one row per region/district/... with every raster layer
                                  summarised (sums for counts of people, averages otherwise,
                                  mean distance for proximity layers) and point counts
  catalogue.csv                   every layer: EAE path, source, date, licence, citation, files
  README.md                       licences and how to cite

Usage (Python 3.10+; needs requests, numpy, pandas, geopandas, rasterio):
  python tools/download_eae_layers.py                      # Uganda -> eae_data/
  python tools/download_eae_layers.py --geography Kenya --out eae_kenya
  python tools/download_eae_layers.py --zip                # also write eae_data.zip
"""
import argparse
import json
import re
import shutil
import time
import warnings
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests

API = "https://api.energyaccessexplorer.org"
warnings.filterwarnings("ignore", message=".*Geometry is in a geographic CRS.*")


def api(path, **params):
    r = requests.get(f"{API}/{path}", params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def fetch(url, dest, tries=4):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    for i in range(tries):
        try:
            r = requests.get(url, timeout=600)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return dest
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def licence_class(licence, source_url):
    """Can this layer be shared further? A rough reading of the licence text EAE stores."""
    text = (licence or "").lower()
    if "protectedplanet" in (source_url or ""):
        return "restricted: WDPA terms, do not redistribute"
    if not text:
        return "unknown: check the source before sharing"
    if "noncommercial" in text.replace("-", "").replace(" ", "") or "by-nc" in text:
        return "non-commercial use only, with attribution"
    if "attribution" in text or "cc by" in text or "census" in text:
        return "open, with attribution"
    return "check the source"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geography", default="Uganda", help="EAE country name (default Uganda)")
    ap.add_argument("--out", default="eae_data", help="output folder (default eae_data)")
    ap.add_argument("--zip", action="store_true", help="also write <out>.zip")
    args = ap.parse_args()

    out = Path(args.out)
    for sub in ("rasters", "vectors", "csv"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    geo = api("geographies", name=f"eq.{args.geography}", adm="eq.0", select="*")[0]
    datasets = api("datasets", geography_id=f"eq.{geo['id']}",
                   select="id,name,name_long,category_id,processed_files,metadata,category_overrides")
    categories = {c["id"]: c for c in api("categories", select="*")}
    print(f"{geo['name']}: {len(datasets)} datasets")

    rows, rasters, points = [], {}, {}
    used = set()
    for ds in sorted(datasets, key=lambda d: categories[d["category_id"]]["name"]):
        cat = categories[ds["category_id"]]
        md = ds.get("metadata") or {}
        files = {f["func"]: f["endpoint"] for f in ds.get("processed_files") or []}
        if not files:
            continue
        name = ds.get("name_long") or ds.get("name") or cat.get("name_long") or cat["name"]
        key = slug(name)
        if key in used:
            key = f"{key}_{slug(cat['name'])}"
        used.add(key)
        saved = []
        if "raster" in files:
            p = fetch(files["raster"], out / "rasters" / f"{key}.tif")
            saved.append(str(p.relative_to(out)))
            rasters[key] = {"path": p, "category": cat, "has_vectors": "vectors" in files, "name": name}
        if "vectors" in files:
            p = fetch(files["vectors"], out / "vectors" / f"{key}.geojson")
            saved.append(str(p.relative_to(out)))
            gdf = gpd.read_file(p)
            geom = set(gdf.geom_type.dropna().unique())
            if geom <= {"Point", "MultiPoint"} and len(gdf):
                pts = gdf.explode(index_parts=False) if "MultiPoint" in geom else gdf
                df = pd.DataFrame(pts.drop(columns="geometry"))
                df.insert(0, "lat", pts.geometry.y.round(6).values)
                df.insert(0, "lon", pts.geometry.x.round(6).values)
                df.to_csv(out / "csv" / f"points_{key}.csv", index=False)
                saved.append(f"csv/points_{key}.csv")
                points[key] = pts
            elif geom <= {"LineString", "MultiLineString"} and len(gdf):
                df = pd.DataFrame(gdf.drop(columns="geometry"))
                df["length_km"] = (gdf.to_crs(gdf.estimate_utm_crs()).length / 1000).round(3)
                df.to_csv(out / "csv" / f"lines_{key}.csv", index=False)
                saved.append(f"csv/lines_{key}.csv")
        rows.append({
            "layer": name, "file_key": key, "eae_category": cat["name"],
            "eae_path": " > ".join((cat.get("controls") or {}).get("path") or []),
            "unit": cat.get("unit"), "content_date": md.get("content_date"),
            "source": (md.get("sources") or "").strip().replace("\n", "; "),
            "licence": (md.get("license") or "").strip().replace("\n", " "),
            "can_share": licence_class(md.get("license"), md.get("download_original_url")),
            "citation": (md.get("suggested_citation") or "").strip(),
            "original_download": md.get("download_original_url"),
            "eae_dataset_id": ds["id"], "files": "; ".join(saved),
            "retrieved": date.today().isoformat(),
        })
        print(f"  {name}: {', '.join(saved)}")

    catalogue = pd.DataFrame(rows)
    catalogue.to_csv(out / "catalogue.csv", index=False)

    # ---------------------------------------------------------- admin-area summaries
    divisions = (geo.get("configuration") or {}).get("divisions") or []
    by_id = {d["id"]: d for d in datasets}
    # Summaries skip boundaries, categorical rasters (class codes cannot be averaged) and layers whose
    # licence does not allow sharing derived data.
    restricted = set(catalogue.loc[catalogue["can_share"].str.startswith(("restricted", "unknown")), "file_key"])
    value_layers = {k: v for k, v in rasters.items()
                    if v["category"]["name"] not in ("boundaries", "outline", "raster-valued")
                    and not (v["category"].get("csv") or {}).get("key") and k not in restricted}
    loaded = {}
    for k, v in value_layers.items():
        with rasterio.open(v["path"]) as r:
            b = r.read().astype("float64")
            nodata = r.nodata
        b[np.isnan(b)] = nodata
        loaded[k] = (b, nodata)
    for div in divisions:
        ds = by_id.get(div.get("dataset_id"))
        if not ds or div["name"].lower() == "outline":
            continue
        tier = slug(div["name"])
        cat = categories[ds["category_id"]]
        key = slug(ds.get("name_long") or ds.get("name") or cat["name"])
        rpath, vpath = out / "rasters" / f"{key}.tif", out / "vectors" / f"{key}.geojson"
        if not (rpath.exists() and vpath.exists()):
            continue
        polys = gpd.read_file(vpath)
        label = next((c for c in polys.columns if c not in ("fid", "id", "geometry")
                      and pd.api.types.is_string_dtype(polys[c])), None)
        with rasterio.open(rpath) as r:
            area = r.read(1).ravel().astype(int)
        n = len(polys)
        if area.max() >= n:
            print(f"  skipping {tier}: raster ids do not match the {n} boundary features")
            continue
        table = pd.DataFrame({div["name"].lower(): polys[label] if label else polys.index})
        table["area_km2"] = (polys.to_crs(6933).area / 1e6).round(1).values
        inside = area >= 0
        for k, (b, nodata) in loaded.items():
            v = value_layers[k]
            agg = ((v["category"].get("analysis") or {}).get("aggregation") or "AVG").upper()
            if v["has_vectors"]:
                band, stat, col = b[0].ravel(), "mean", f"{k}_mean_distance_km"
            elif agg == "SUM":
                band, stat, col = (b[1] if len(b) >= 3 else b[0]).ravel(), "sum", f"{k}_sum"
            else:
                band, stat, col = (b[2] if len(b) >= 3 else b[0]).ravel(), "mean", f"{k}_mean"
            ok = inside & (band != nodata) & np.isfinite(band)
            s = np.bincount(area[ok], weights=band[ok], minlength=n)
            c = np.bincount(area[ok], minlength=n)
            with np.errstate(invalid="ignore", divide="ignore"):
                table[col] = s if stat == "sum" else np.where(c > 0, s / c, np.nan)
        poly84 = polys.to_crs(4326)
        for k, pts in ((k, p) for k, p in points.items() if k not in restricted):
            j = gpd.sjoin(pts[["geometry"] + (["ELECTRIFIC"] if "ELECTRIFIC" in pts.columns else [])].to_crs(4326),
                          poly84[["geometry"]], how="inner", predicate="within")
            table[f"{k}_count"] = j.groupby("index_right").size().reindex(range(n)).fillna(0).astype(int).values
            if "ELECTRIFIC" in j.columns:     # health facilities: electrification status per area
                for status, grp in j.groupby("ELECTRIFIC"):
                    table[f"{k}_{slug(status)}_count"] = grp.groupby("index_right").size().reindex(range(n)).fillna(0).astype(int).values
        table.round(4).to_csv(out / "csv" / f"admin_{tier}.csv", index=False)
        print(f"  admin summary: csv/admin_{tier}.csv ({n} areas, {table.shape[1]} columns)")

    # ---------------------------------------------------------- README
    lines = [f"# Energy Access Explorer layers: {geo['name']}", "",
             f"Downloaded {date.today().isoformat()} from Energy Access Explorer (World Resources Institute), "
             "https://www.energyaccessexplorer.org/, with `download_eae_layers.py`.", "",
             "- `rasters/`: GeoTIFF on EAE's 1 km grid, EPSG:3857. Band 1 = value EAE maps, band 2 = area-weighted "
             "sum, band 3 = area-weighted average. Layers built from points or lines hold distance (km) to the "
             "nearest feature.",
             "- `vectors/`: GeoJSON in lon/lat (CRS84).",
             "- `csv/`: point and line layers as tables, and one summary table per admin level.",
             "- `catalogue.csv`: source, date, licence, suggested citation and original download link for every layer.",
             "", "## Licences", "",
             "Each layer keeps its own licence (column `licence` in `catalogue.csv`). Cite each layer you use "
             "with its suggested citation, plus Energy Access Explorer.", ""]
    for cls, grp in catalogue.groupby("can_share"):
        lines.append(f"- **{cls}**: {', '.join(grp['layer'])}")
    (out / "README.md").write_text("\n".join(lines) + "\n")

    if args.zip:
        z = shutil.make_archive(str(out), "zip", root_dir=out.parent, base_dir=out.name)
        print(f"zip: {z} ({Path(z).stat().st_size / 1e6:.1f} MB)")
    print(f"done: {out}/")


if __name__ == "__main__":
    main()
