"""Fetch MTF survey data from World Bank sources, where that is possible.

WHAT CAN AND CANNOT BE FETCHED
------------------------------
Probed 2026-09-22.

  Kenya MTF 2016-2018     energydata.info (ESMAP's CKAN platform)
                          OPEN, CC-BY 4.0, no login. Microdata (5 MB of .dta),
                          the household questionnaire PDF and the codebook
                          XLSX all download from a plain URL.
                          -> fully automatable. This module does it.

  Rwanda MTF 2022         microdata.worldbank.org catalog 6429
                          NOT open. The NADA download endpoints need an
                          authenticated session, and the study is not
                          mirrored on energydata.info (package_show -> 404).
                          -> manual download, then upload. Cannot be scripted
                             without embedding credentials, which should not
                             go in a notebook.

So the notebook can fetch half of it. The Rwandan half stays a manual step,
which is one more reason the derived appliance sets are committed to
final_cfg.py rather than rebuilt on every run.

energydata.info returns intermittent 502s on the larger resources. Every
request here retries; the raw-data zip failed once and succeeded on the
second attempt during testing.
"""
import argparse
import json
import ssl
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

CKAN = "https://energydata.info/api/3/action"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Accept": "*/*"}

# Rwanda is listed so the failure is explicit rather than a silent omission.
PACKAGES = {
    "kenya": "kenya-multi-tier-framework-mtf-survey",
    "rwanda": None,
}

MANUAL = {
    "rwanda": (
        "Rwanda MTF 2022 is not openly distributed.\n"
        "  1. https://microdata.worldbank.org/index.php/catalog/6429\n"
        "  2. free account, then submit the one-paragraph use statement\n"
        "  3. download RWA_2022_MTF_v01_M_CSV.zip\n"
        "  4. put it in Drive/mtf or upload it in section 5\n"
        "  DOI 10.48529/x75v-fm71"),
}

_CTX = ssl.create_default_context()


def _get(url, binary=False, retries=4, backoff=6, timeout=420):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=UA),
                    timeout=timeout, context=_CTX) as r:
                return r.read() if binary else json.load(r)
        except Exception as e:                       # 502s are routine here
            last = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"failed after {retries} attempts: {url[:80]} ({last})")


def list_resources(country):
    pkg = PACKAGES.get(country)
    if not pkg:
        raise LookupError(MANUAL.get(country, f"{country}: no open source"))
    r = _get(f"{CKAN}/package_show?id={urllib.parse.quote(pkg)}")["result"]
    return r.get("license_title"), [
        {"name": x.get("name", ""), "format": x.get("format", ""),
         "url": x.get("url", "")} for x in r["resources"]]


def fetch(country, out="data/raw", want=("ZIP", "PDF", "XLSX"),
          extract=True, to_csv=True):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    lic, res = list_resources(country)
    print(f"{country}: {len(res)} resources, licence: {lic}")
    got = []
    for r in res:
        if r["format"] not in want:
            continue
        name = r["name"] or f"{country}.{r['format'].lower()}"
        dest = out / name
        try:
            dest.write_bytes(_get(r["url"], binary=True))
            print(f"  OK   [{r['format']:<4}] {name[:48]:<48} "
                  f"{dest.stat().st_size/1e6:>7.2f} MB")
            got.append(dest)
        except RuntimeError as e:
            print(f"  FAIL [{r['format']:<4}] {name[:48]:<48} {e}")

    if extract:
        for z in [g for g in got if g.suffix.lower() == ".zip"]:
            with zipfile.ZipFile(z) as f:
                members = [m for m in f.namelist()
                           if not m.startswith("__MACOSX")
                           and not m.endswith(".DS_Store")]
                f.extractall(out, members=members)
            print(f"  extracted {z.name}: {len(members)} members")

    if to_csv:
        stata_to_csv(out)
    return got


def stata_to_csv(root, convert_categoricals=True):
    """.dta -> .csv, matching what the rest of the pipeline reads.

    KEEP convert_categoricals=True. Turning it off looks safer - it stops
    coded columns becoming strings - but it strips Stata's value labels, and
    the pipeline filters on one of those:

        grid_loc, labels ON   "Rural with grid access"   <- what the code wants
        grid_loc, labels OFF  3.0

    With labels off, `grid_loc == "Rural with grid access"` matches nothing,
    kenya_ownership() returns an empty frame, and every ownership rate comes
    back NaN through a silent divide-by-zero. Verified: the two settings give
    different files from identical .dta input.

    PARENT_KEY is unaffected either way (it is a plain uuid string).
    """
    import pandas as pd
    n = 0
    for f in Path(root).rglob("*.dta"):
        csv = f.with_suffix(".csv")
        if csv.exists():
            continue
        try:
            df = pd.read_stata(f, convert_categoricals=convert_categoricals)
        except ValueError:
            # a few MTF files carry duplicate value labels and refuse to
            # convert; fall back rather than skip the file entirely
            df = pd.read_stata(f, convert_categoricals=False)
            print(f"  WARNING {f.name}: value labels unusable, wrote codes")
        df.to_csv(csv, index=False)
        print(f"  converted {f.name} -> {csv.name}")
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("country", choices=sorted(PACKAGES))
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    try:
        if a.list:
            lic, res = list_resources(a.country)
            print(f"licence: {lic}")
            for r in res:
                print(f"  [{r['format']:<5}] {r['name']}")
        else:
            fetch(a.country, out=a.out)
    except LookupError as e:
        print(e)


if __name__ == "__main__":
    main()
