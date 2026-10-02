"""Fetch NASA POWER hourly resource data for each case site.

Run locally - NASA POWER is not reachable from every environment.
    python src/fetch_power.py --params params.yaml --start 2005 --end 2024

Writes one JSON per site-year to data/raw/power/, plus a provenance manifest.
Re-running skips files already present, so an interrupted pull resumes cheaply.
"""
import argparse, json, hashlib, time, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

import yaml

BASE = "https://power.larc.nasa.gov/api/temporal/hourly/point"
RAW = Path("data/raw/power")

# LST = local solar time. Do NOT change to UTC: the analysis is time-of-day
# specific and the two sites are in different time zones.
TIME_STANDARD = "LST"


def build_url(lat, lon, year, parameters):
    return BASE + "?" + urlencode({
        "parameters": ",".join(parameters),
        "community": "RE",
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start": f"{year}0101",
        "end": f"{year}1231",
        "format": "JSON",
        "time-standard": TIME_STANDARD,
    })


def fetch(url, retries=4, backoff=5):
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode())
        except (HTTPError, URLError, TimeoutError) as e:
            if attempt == retries - 1:
                raise
            wait = backoff * (2 ** attempt)
            print(f"    retry {attempt + 1} in {wait}s ({e})", file=sys.stderr)
            time.sleep(wait)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--start", type=int, default=2005)
    ap.add_argument("--end", type=int, default=2024)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.params))
    parameters = cfg["shared"]["resource"]["variables"]
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []

    for name, site in cfg["countries"].items():
        lat, lon = site["latitude"], site["longitude"]
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            sys.exit(f"{name}: coordinates not set in {args.params} (got {lat!r}, {lon!r})")
        print(f"{name}: {site['site_name']}  ({lat}, {lon})")

        for year in range(args.start, args.end + 1):
            out = RAW / f"{name}_{year}.json"
            if out.exists():
                print(f"  {year} cached")
            else:
                url = build_url(lat, lon, year, parameters)
                print(f"  {year} fetching")
                payload = fetch(url)
                out.write_text(json.dumps(payload))
                time.sleep(1)          # be polite to the API
            manifest.append({
                "site": name,
                "year": year,
                "file": str(out),
                "sha256": hashlib.sha256(out.read_bytes()).hexdigest()[:16],
                "latitude": lat,
                "longitude": lon,
                "time_standard": TIME_STANDARD,
                "parameters": parameters,
            })

    meta = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": BASE,
        "note": "NASA POWER. Solar from CERES/SYN1deg, meteorology from MERRA-2. "
                "Grid resolution is coarse (~0.5-1 degree) - island-scale "
                "microclimate is not resolved. Cite this as a limitation.",
        "files": manifest,
    }
    Path("data/raw/power_manifest.json").write_text(json.dumps(meta, indent=2))
    print(f"\n{len(manifest)} site-years. Manifest: data/raw/power_manifest.json")


if __name__ == "__main__":
    main()
