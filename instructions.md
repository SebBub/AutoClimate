# AutoKlima — Project Brief

Self-contained. No dependency on the `SYDRO_Skripte` repo — everything needed is inlined below.
Drop this file into the new project folder (as `CLAUDE.md`, or paste it as the opening message of a new session) to bootstrap work with full context.

## Goal

Build a small, fully automated pipeline that:
1. Fetches the daily temperature observation for DWD station **Glücksburg-Meierwik** (Stations_ID **01666**).
2. Compares it against a precomputed climatology (a smoothed day-of-year normal).
3. Renders a plot.
4. Publishes text + plot to **https://abs-gruene.de/** (WordPress, hosted on IONOS) via the WordPress REST API.
5. Runs entirely on **GitHub Actions**, on a schedule, with no laptop or server of the user's own involved.

## Confirmed station facts (verified against DWD's own station index)

- **Name:** Glücksburg-Meierwik
- **DWD Stations_ID:** `01666` (5-digit, zero-padded — this is DWD's own internal ID, *not* the WMO ID; do not confuse the two)
- **Coordinates:** 54.8273° N, 9.5058° E, elevation 12 m
- **State:** Schleswig-Holstein
- **Record starts:** 1971-01-01, station still active as of the most recent DWD index update
- **Data source:** DWD Climate Data Center (CDC) open data — `https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/` — served over both FTP and plain HTTPS at the same path structure. Public, no authentication needed to *read*.
- Relevant column in the daily "kl" product: `TMK` (Tagesmittel der Temperatur, °C — daily mean temperature). Missing-value sentinel is `-999`.

## Architecture decisions made during planning

**Runtime — GitHub Actions.**
- Prefer a **public repo**: free and unlimited Actions minutes, and a beefier `ubuntu-latest` runner (4-core CPU, 16 GB RAM, 14 GB SSD) vs. a private repo on the free plan (2-core, 8 GB RAM, 2,000 free minutes/month). Nothing in this pipeline is sensitive — credentials live in Secrets either way, never in the repo.
- Either tier has enormous headroom: decades of daily data for one station is tens of MB; the whole job (fetch → compute → plot → publish) will finish in well under a minute against a 6-hour per-job hard limit.
- **Statelessness is the real design constraint, not compute.** Every run gets a fresh VM; nothing persists automatically. The one thing that *must* persist between runs — the climatology — is committed to the repo as a small file.

**Two separate workflows, different clocks:**
1. `update-climatology.yml` — triggered manually (`workflow_dispatch`), run once and then roughly yearly. Fetches the full historical record, computes a smoothed day-of-year climatology over a reference period, commits the result.
2. `daily-report.yml` — scheduled (`cron: '0 6 * * *'`, 06:00 UTC). Fetches only the latest observation, reads the already-committed climatology (no recomputation), computes the comparison, plots, publishes.

**Climatology method:**
- Reference period: WMO-style normal, e.g. **1991–2020** (or a trailing 30-year window if preferred).
- Group by day-of-year, then **smooth** — a raw per-calendar-day mean over ~30 samples is noisy. Use a rolling window (±10–15 days) that **wraps around the Dec→Jan boundary** (a plain `.rolling()` without circular padding will under-smooth the days near Jan 1 / Dec 31 — handle this explicitly).
- Refresh cadence: manual/yearly, not automated on its own trigger — climate normals don't need daily updating.

**Publishing — WordPress REST API:**
- Built into WordPress core since 4.7; reading public content needs no auth. Writing needs auth.
- **Application Passwords** are built into core since WP 5.6 (`Users → Profile → Application Passwords`), require the site to be served over HTTPS (IONOS provides this by default).
- Use a **dedicated, low-privilege WordPress user** for this automation — not the main Administrator account — so a leaked credential has limited blast radius.
- Store the application password (and WP username, base URL, target page ID) only in **GitHub Actions Secrets**, never in the repo.
- Flow: `POST /wp-json/wp/v2/media` (upload the plot PNG, HTTP Basic Auth with the application password) → then update the target page/post's content via `POST /wp-json/wp/v2/pages/<id>` (or `/posts/<id>`) referencing the uploaded media's URL.

## A note on code reuse (why nothing here is copy-pasted from SYDRO_Skripte)

The old repo has two files that are close matches for this task — a DWD FTP downloader (`lib/dwd_daily.py`) and a day-of-year climatology helper (`precipitation_statistics.py`) — but both carry a `Copyright (C) SYDRO Consult GmbH... may not be copied, modified and/or distributed without express permission` header. Per your call, none of their code is reproduced below. Everything here is written fresh against DWD's public data spec, which also let two bugs spotted in the original get fixed rather than carried forward: passing a bare `Path.glob()` generator into `zipfile.ZipFile` instead of a resolved path, and matching station IDs without zero-padding (silently fails for any station ID under 10000 — which is most of them, including 01666).

## Repo layout (target)

```
repo/
├── .github/workflows/
│   ├── daily-report.yml
│   └── update-climatology.yml
├── data/
│   └── climatology_meierwik.csv       ← the one file that must persist between runs
├── src/
│   ├── fetch_dwd.py
│   ├── compute_climatology.py
│   ├── daily_report.py
│   └── publish_wordpress.py
└── requirements.txt                     ← pandas, requests, matplotlib
```

## Reference implementations (fresh, not from the old repo)

### `src/fetch_dwd.py`

```python
import io
import re
import zipfile

import pandas as pd
import requests

BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl"


def _read_kl_zip(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        data_file = next(n for n in zf.namelist() if n.startswith("produkt_klima_tag_"))
        with zf.open(data_file) as f:
            df = pd.read_csv(f, sep=";", parse_dates=["MESS_DATUM"], index_col="MESS_DATUM")
    df.columns = df.columns.str.strip()
    return df


def fetch_recent(station_id: int) -> pd.DataFrame:
    """Latest observations. Filename is deterministic — no directory listing needed."""
    sid = f"{station_id:05d}"
    url = f"{BASE}/recent/tageswerte_KL_{sid}_akt.zip"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return _read_kl_zip(resp.content)


def fetch_historical(station_id: int) -> pd.DataFrame:
    """Full history. Date range in the filename varies per station, so list the directory first."""
    sid = f"{station_id:05d}"
    index = requests.get(f"{BASE}/historical/", timeout=30)
    index.raise_for_status()
    match = re.search(rf'href="(tageswerte_KL_{sid}_\d{{8}}_\d{{8}}_hist\.zip)"', index.text)
    if not match:
        raise ValueError(f"No historical file found for station {station_id}")
    resp = requests.get(f"{BASE}/historical/{match.group(1)}", timeout=60)
    resp.raise_for_status()
    return _read_kl_zip(resp.content)
```

### `src/compute_climatology.py`

```python
import pandas as pd

def day_of_year_climatology(
    temp: pd.Series,
    start_year: int = 1991,
    end_year: int = 2020,
    smooth_window_days: int = 15,
) -> pd.Series:
    """Smoothed mean daily temperature by day-of-year (1..366), circularly padded
    so the Dec 31 / Jan 1 boundary is smoothed correctly rather than truncated."""
    temp = temp.replace(-999, pd.NA).dropna()
    ref = temp.loc[f"{start_year}-01-01":f"{end_year}-12-31"]
    doy_mean = ref.groupby([ref.index.month, ref.index.day]).mean()
    doy_mean.index = range(1, len(doy_mean) + 1)

    pad = smooth_window_days
    padded = pd.concat([doy_mean.tail(pad), doy_mean, doy_mean.head(pad)])
    smoothed = padded.rolling(window=pad, center=True, min_periods=1).mean()
    return smoothed.iloc[pad:-pad].set_axis(doy_mean.index)


def anomaly(today_value: float, day_of_year: int, climatology: pd.Series) -> float:
    return today_value - climatology.loc[day_of_year]
```

### `src/publish_wordpress.py`

```python
from pathlib import Path

import requests


def publish(
    image_path: str,
    page_id: int,
    html_content: str,
    wp_base_url: str,
    wp_user: str,
    wp_app_password: str,
) -> None:
    auth = (wp_user, wp_app_password)

    with open(image_path, "rb") as f:
        media_resp = requests.post(
            f"{wp_base_url}/wp-json/wp/v2/media",
            auth=auth,
            headers={"Content-Disposition": f'attachment; filename="{Path(image_path).name}"'},
            data=f.read(),
            timeout=30,
        )
    media_resp.raise_for_status()
    media_url = media_resp.json()["source_url"]

    page_resp = requests.post(
        f"{wp_base_url}/wp-json/wp/v2/pages/{page_id}",
        auth=auth,
        json={"content": html_content.replace("{{IMAGE_URL}}", media_url)},
        timeout=30,
    )
    page_resp.raise_for_status()
```

### `.github/workflows/daily-report.yml` (sketch)

```yaml
name: Daily temperature report
on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch: {}
jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python src/daily_report.py
        env:
          WP_BASE_URL: ${{ secrets.WP_BASE_URL }}
          WP_USER: ${{ secrets.WP_USER }}
          WP_APP_PASSWORD: ${{ secrets.WP_APP_PASSWORD }}
          WP_PAGE_ID: ${{ secrets.WP_PAGE_ID }}
```

### `.github/workflows/update-climatology.yml` (sketch)

```yaml
name: Update climatology
on:
  workflow_dispatch: {}
jobs:
  update:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python src/compute_climatology.py --station 1666 --out data/climatology_meierwik.csv
      - run: |
          git config user.name "github-actions"
          git config user.email "github-actions@users.noreply.github.com"
          git add data/climatology_meierwik.csv
          git commit -m "Update climatology" || echo "no changes"
          git push
```

## Open items for the new session

- [ ] `src/daily_report.py` doesn't exist yet — it's the glue script: call `fetch_dwd.fetch_recent`, load `data/climatology_meierwik.csv`, compute the anomaly, render the matplotlib plot, call `publish_wordpress.publish`.
- [ ] Decide and create the target WordPress page/post to update; note its numeric ID.
- [ ] Create a dedicated low-privilege WordPress user, generate its Application Password, register `WP_BASE_URL`, `WP_USER`, `WP_APP_PASSWORD`, `WP_PAGE_ID` as GitHub Actions Secrets.
- [ ] Confirm public vs. private for the new repo (public recommended, see above).
- [ ] `requirements.txt`: `pandas`, `requests`, `matplotlib`.
- [ ] Run `update-climatology.yml` once manually before the first `daily-report.yml` run — the daily job assumes `data/climatology_meierwik.csv` already exists.
