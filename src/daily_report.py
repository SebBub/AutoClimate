"""Daily job: fetch the latest observations, compare to climatology, and render interactive
Plotly charts to _site/chart.html for GitHub Pages. The WordPress page embeds that URL in an
<iframe> (inserted once, by hand, in the block editor) — this script never touches WordPress;
publishing means updating the GitHub Pages artifact, which the iframe picks up automatically."""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from compute_climatology import anomaly, climatological_doy
from fetch_dwd import fetch_daily_kl_recent, fetch_hourly_recent

STATION_ID = 1666
STATION_NAME = "Glücksburg-Meierwik"
REFERENCE_PERIOD = "1991–2020"
CLIMATOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "climatology_meierwik.csv"
PRECIP_CLIMATOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "precip_climatology_meierwik.csv"
SITE_DIR = Path("_site")
CHART_PATH = SITE_DIR / "chart.html"

MONTH_LABELS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONTH_TICKS = [pd.Timestamp(2000, m, 1).dayofyear for m in range(1, 13)]


def load_climatology() -> pd.Series:
    df = pd.read_csv(CLIMATOLOGY_PATH)
    return df.set_index("day_of_year")["tmk_normal"]


def load_precip_climatology() -> pd.Series:
    df = pd.read_csv(PRECIP_CLIMATOLOGY_PATH)
    return df.set_index("month")["rsk_normal"]


MIN_VALID_HOURS = 20


def _day_mean(hourly: pd.DataFrame, date: pd.Timestamp) -> float | None:
    """Mean TT_TU over a calendar day's available hourly readings, or None if fewer than
    MIN_VALID_HOURS of the 24 are present and valid. DWD's station feed regularly drops a
    handful of hours (transmission gaps that never get backfilled), so a day is accepted
    once most of it is there rather than requiring a strict 24/24."""
    day_obs = hourly.loc[hourly.index.normalize() == date, "TT_TU"].replace(-999, pd.NA)
    valid = day_obs.dropna()
    if len(valid) < MIN_VALID_HOURS:
        return None
    return float(valid.mean())


def last_complete_day_mean(hourly: pd.DataFrame) -> tuple[pd.Timestamp, float, bool]:
    """Mean TT_TU for the most recent calendar day with at least MIN_VALID_HOURS valid
    hourly readings, scanning backward from yesterday. DWD's 'recent' feed can lag or have
    transmission gaps for individual hours, so we fall back to the last good-enough day
    rather than failing. Returns (date, mean, is_fallback) where is_fallback is True when
    yesterday itself didn't meet the threshold and we had to go further back."""
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    expected_date = today - pd.Timedelta(days=1)
    earliest = hourly.index.normalize().min()

    candidate = expected_date
    while candidate >= earliest:
        mean = _day_mean(hourly, candidate)
        if mean is not None:
            return candidate, mean, candidate < expected_date
        candidate -= pd.Timedelta(days=1)

    raise RuntimeError("No complete day found in hourly data — DWD feed may be broken")


def year_to_date_daily_means(hourly: pd.DataFrame, obs_date: pd.Timestamp) -> pd.Series:
    """Daily mean TT_TU from Jan 1 of obs_date's year through obs_date, for the year-so-far
    line. Days with no valid readings are dropped rather than requiring full 24/24 coverage —
    this is a background trend line, not the headline anomaly figure."""
    year_start = pd.Timestamp(year=obs_date.year, month=1, day=1)
    window = hourly.loc[f"{year_start:%Y-%m-%d}":f"{obs_date:%Y-%m-%d}", "TT_TU"].replace(-999, pd.NA)
    return window.resample("D").mean().dropna()


def monthly_precip_actual(daily_kl: pd.DataFrame, year: int) -> pd.Series:
    """Accumulated precipitation (mm) by calendar month for `year`, from daily RSK readings.
    The current month is included as-is (partial total), so it's only ever compared to the
    full monthly normal as a running, not final, figure."""
    precip = daily_kl.loc[f"{year}-01-01":f"{year}-12-31", "RSK"].replace(-999, pd.NA).dropna()
    return precip.groupby(precip.index.month).sum()


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


def render_precip_chart_html(
    precip_climatology: pd.Series,
    precip_actual: pd.Series,
    year: int,
) -> str:
    months = list(precip_actual.index)
    labels = [MONTH_LABELS[m - 1] for m in months]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[precip_climatology.loc[m] for m in months],
            name=f"Klimanormal {REFERENCE_PERIOD}",
            marker_color="#4472c4",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=[precip_actual.loc[m] for m in months],
            name=str(year),
            marker_color="#c00000",
        )
    )

    fig.update_layout(
        title=dict(text=f"{STATION_NAME} — Monatsniederschlag vs. Klimanormal", y=0.98, yanchor="top"),
        template="plotly_white",
        autosize=True,
        height=440,
        barmode="group",
        xaxis=dict(title="Monat"),
        yaxis=dict(title="Niederschlag (mm)", showgrid=True, gridcolor="#e2e2e2"),
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5),
        margin=dict(l=55, r=20, t=45, b=80),
        hovermode="x unified",
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})


def build_page_html(
    chart_snippet: str,
    precip_chart_snippet: str,
    obs_date: pd.Timestamp,
    obs_value: float,
    diff: float,
    incomplete_fallback: bool = False,
) -> str:
    summary = (
        f"<p>Stand {obs_date:%d.%m.%Y}: Tagesmitteltemperatur in {STATION_NAME} "
        f"{obs_value:.1f} °C ({format_diff(diff)} ggü. dem Klimanormal {REFERENCE_PERIOD}).</p>"
    )
    note = ""
    if incomplete_fallback:
        note = (
            f'<p style="color:#666; font-size:0.9em;">'
            f"Letzter Tag mit vollständigem Datensatz: {obs_date:%d.%m.%Y}</p>"
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
{note}
{chart_snippet}
{precip_chart_snippet}
</body>
</html>"""


def main() -> None:
    climatology = load_climatology()
    precip_climatology = load_precip_climatology()
    hourly = fetch_hourly_recent(STATION_ID)
    daily_kl = fetch_daily_kl_recent(STATION_ID)
    obs_date, obs_value, incomplete_fallback = last_complete_day_mean(hourly)

    doy = climatological_doy(obs_date)
    try:
        diff = anomaly(obs_value, doy, climatology)
    except KeyError as exc:
        raise RuntimeError(f"No climatology entry for day-of-year {doy} (from {obs_date:%Y-%m-%d})") from exc

    ytd_daily = year_to_date_daily_means(hourly, obs_date)
    chart_snippet = render_chart_html(climatology, ytd_daily, obs_date, obs_value)

    precip_actual = monthly_precip_actual(daily_kl, obs_date.year)
    precip_chart_snippet = render_precip_chart_html(precip_climatology, precip_actual, obs_date.year)

    page_html = build_page_html(chart_snippet, precip_chart_snippet, obs_date, obs_value, diff, incomplete_fallback)

    SITE_DIR.mkdir(exist_ok=True)
    CHART_PATH.write_text(page_html, encoding="utf-8")

    if incomplete_fallback:
        print(f"Note: yesterday's hourly data was incomplete; fell back to last complete day {obs_date:%Y-%m-%d}")
    print(f"Rendered report for {obs_date:%Y-%m-%d}: {obs_value:.1f} °C ({format_diff(diff)} vs. normal) to {CHART_PATH}")


if __name__ == "__main__":
    main()
