"""Daily job: fetch the latest observation, compare to climatology, and render an interactive
Plotly chart to _site/chart.html for GitHub Pages. The WordPress page embeds that URL in an
<iframe> (inserted once, by hand, in the block editor) — this script never touches WordPress;
publishing means updating the GitHub Pages artifact, which the iframe picks up automatically."""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from compute_climatology import anomaly, climatological_doy
from fetch_dwd import fetch_hourly_recent

STATION_ID = 1666
STATION_NAME = "Glücksburg-Meierwik"
REFERENCE_PERIOD = "1991–2020"
CLIMATOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "climatology_meierwik.csv"
SITE_DIR = Path("_site")
CHART_PATH = SITE_DIR / "chart.html"

MONTH_LABELS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONTH_TICKS = [pd.Timestamp(2000, m, 1).dayofyear for m in range(1, 13)]


def load_climatology() -> pd.Series:
    df = pd.read_csv(CLIMATOLOGY_PATH)
    return df.set_index("day_of_year")["tmk_normal"]


def previous_day_mean(hourly: pd.DataFrame) -> tuple[pd.Timestamp, float]:
    """Mean TT_TU over the full previous calendar day (hours 00-23) — not just the last
    24 rows, since a run early in DWD's publishing window could otherwise average a
    partial day. Raises if the previous day isn't fully published yet."""
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    target_date = today - pd.Timedelta(days=1)

    day_obs = hourly.loc[hourly.index.normalize() == target_date, "TT_TU"].replace(-999, pd.NA)
    valid = day_obs.dropna()
    if len(day_obs) != 24 or len(valid) != 24:
        raise RuntimeError(
            f"Incomplete hourly data for {target_date:%Y-%m-%d}: "
            f"{len(valid)}/24 valid readings — DWD likely hasn't published the full day yet"
        )
    return target_date, float(valid.mean())


def year_to_date_daily_means(hourly: pd.DataFrame, obs_date: pd.Timestamp) -> pd.Series:
    """Daily mean TT_TU from Jan 1 of obs_date's year through obs_date, for the year-so-far
    line. Days with no valid readings are dropped rather than requiring full 24/24 coverage —
    this is a background trend line, not the headline anomaly figure."""
    year_start = pd.Timestamp(year=obs_date.year, month=1, day=1)
    window = hourly.loc[f"{year_start:%Y-%m-%d}":f"{obs_date:%Y-%m-%d}", "TT_TU"].replace(-999, pd.NA)
    return window.resample("D").mean().dropna()


def format_diff(diff: float) -> str:
    return f"{'+' if diff >= 0 else ''}{diff:.1f} °C"


def render_chart_html(
    climatology: pd.Series,
    ytd_daily: pd.Series,
    obs_date: pd.Timestamp,
    obs_value: float,
) -> str:
    ytd_x = [climatological_doy(d) for d in ytd_daily.index]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(climatology.index),
            y=list(climatology.values),
            mode="lines",
            name=f"Klimanormal {REFERENCE_PERIOD}",
            line=dict(color="#4472c4", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ytd_x,
            y=list(ytd_daily.values),
            mode="lines",
            name=f"{obs_date.year} bisher",
            line=dict(color="#c00000", width=2),
            customdata=[d.strftime("%d.%m.%Y") for d in ytd_daily.index],
            hovertemplate="%{customdata}: %{y:.1f} °C<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[climatological_doy(obs_date)],
            y=[obs_value],
            mode="markers",
            name=f"{obs_date:%d.%m.%Y}: {obs_value:.1f} °C",
            marker=dict(color="#c00000", size=11, line=dict(color="white", width=1.5)),
            hovertemplate=f"{obs_date:%d.%m.%Y}: {obs_value:.1f} °C<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(text=f"{STATION_NAME} — Temperatur vs. Klimanormal", y=0.98, yanchor="top"),
        template="plotly_white",
        autosize=True,
        height=440,
        xaxis=dict(
            title="Monat",
            tickmode="array",
            tickvals=MONTH_TICKS,
            ticktext=MONTH_LABELS,
            range=[1, 366],
            showgrid=True,
            gridcolor="#e2e2e2",
        ),
        yaxis=dict(title="Tagesmitteltemperatur (°C)", showgrid=True, gridcolor="#e2e2e2"),
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
        margin=dict(l=55, r=20, t=45, b=80),
        hovermode="x unified",
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn", config={"responsive": True})


def build_page_html(chart_snippet: str, obs_date: pd.Timestamp, obs_value: float, diff: float) -> str:
    summary = (
        f"<p>Stand {obs_date:%d.%m.%Y}: Tagesmitteltemperatur in {STATION_NAME} "
        f"{obs_value:.1f} °C ({format_diff(diff)} ggü. dem Klimanormal {REFERENCE_PERIOD}).</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{STATION_NAME} — Temperaturbericht</title>
<style>
  html, body {{ background: transparent; }}
  body {{
    margin: 0;
    padding: 0.75rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 1rem;
    line-height: 1.6;
    color: #222;
  }}
  p {{ margin: 0 0 0.5rem 0; }}
</style>
</head>
<body>
{summary}
{chart_snippet}
</body>
</html>"""


def main() -> None:
    climatology = load_climatology()
    hourly = fetch_hourly_recent(STATION_ID)
    obs_date, obs_value = previous_day_mean(hourly)

    doy = climatological_doy(obs_date)
    try:
        diff = anomaly(obs_value, doy, climatology)
    except KeyError as exc:
        raise RuntimeError(f"No climatology entry for day-of-year {doy} (from {obs_date:%Y-%m-%d})") from exc

    ytd_daily = year_to_date_daily_means(hourly, obs_date)
    chart_snippet = render_chart_html(climatology, ytd_daily, obs_date, obs_value)
    page_html = build_page_html(chart_snippet, obs_date, obs_value, diff)

    SITE_DIR.mkdir(exist_ok=True)
    CHART_PATH.write_text(page_html, encoding="utf-8")

    print(f"Rendered report for {obs_date:%Y-%m-%d}: {obs_value:.1f} °C ({format_diff(diff)} vs. normal) to {CHART_PATH}")


if __name__ == "__main__":
    main()
