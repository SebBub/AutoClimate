# AutoClimate

A small, fully automated pipeline that reports how today's weather compares to the
long-term climate normal for **Glücksburg-Meierwik**, Schleswig-Holstein — published daily
with no server or manual steps.

## What it does

1. **Fetch** the latest hourly temperature readings for DWD station 01666 from the [DWD
   Climate Data Center](https://opendata.dwd.de/climate_environment/CDC/) open data feed.
2. **Compare** the most recent complete day's mean temperature against a smoothed
   day-of-year climate normal (reference period 1991–2020).
3. **Render** an interactive Plotly chart showing the year so far against that normal.
4. **Publish** the chart to GitHub Pages, which is embedded via `<iframe>` on
   [abs-gruene.de](https://abs-gruene.de/).

Everything runs on a schedule via GitHub Actions — there's no server, database, or manual
publishing step involved.

## How it's built

| Workflow | Trigger | What it does |
|---|---|---|
| `daily-report.yml` | Daily cron (09:00 UTC) | Fetches the latest observation, renders the chart, deploys it to GitHub Pages |
| `update-climatology.yml` | Manual, roughly yearly | Recomputes the climate normal from full station history and commits it to the repo |

The climate normal is the only thing that needs to persist between runs, so it's committed
to the repo as [`data/climatology_meierwik.csv`](data/climatology_meierwik.csv) rather than
recomputed on every run.

```
src/
├── fetch_dwd.py           # downloads DWD station data
├── compute_climatology.py # builds the smoothed day-of-year normal
└── daily_report.py        # ties it together and renders the chart
```

## Running locally

```
pip install -r requirements.txt
python src/daily_report.py
```

This writes `_site/chart.html`, the same file the GitHub Actions workflow publishes.

## Data source

[DWD Climate Data Center](https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/)
open data — public, no authentication required.
