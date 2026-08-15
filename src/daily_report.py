"""Daily job: fetch the latest observation, compare to climatology, plot, publish to WordPress."""

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from compute_climatology import anomaly, climatological_doy
from fetch_dwd import fetch_recent
from publish_wordpress import publish

STATION_ID = 1666
STATION_NAME = "Glücksburg-Meierwik"
REFERENCE_PERIOD = "1991–2020"
CLIMATOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "climatology_meierwik.csv"
PLOT_PATH = Path("daily_report.png")


def load_climatology() -> pd.Series:
    df = pd.read_csv(CLIMATOLOGY_PATH)
    return df.set_index("day_of_year")["tmk_normal"]


def latest_observation(df: pd.DataFrame) -> tuple[pd.Timestamp, float]:
    tmk = df["TMK"].replace(-999, pd.NA).dropna()
    if tmk.empty:
        raise RuntimeError("No valid TMK observations found in the 'recent' file")
    return tmk.index[-1], float(tmk.iloc[-1])


def render_plot(climatology: pd.Series, obs_date: pd.Timestamp, obs_value: float, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(climatology.index, climatology.values, color="#4472c4", label=f"Klimanormal {REFERENCE_PERIOD}")
    ax.scatter(
        [climatological_doy(obs_date)],
        [obs_value],
        color="#c00000",
        zorder=5,
        label=f"{obs_date:%d.%m.%Y}: {obs_value:.1f} °C",
    )
    ax.set_xlabel("Tag des Jahres")
    ax.set_ylabel("Tagesmitteltemperatur (°C)")
    ax.set_title(f"{STATION_NAME} — Temperatur vs. Klimanormal")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def format_diff(diff: float) -> str:
    return f"{'+' if diff >= 0 else ''}{diff:.1f} °C"


def build_html(obs_date: pd.Timestamp, obs_value: float, diff: float) -> str:
    return (
        f"<p>Stand {obs_date:%d.%m.%Y}: Tagesmitteltemperatur in {STATION_NAME} "
        f"{obs_value:.1f} °C ({format_diff(diff)} ggü. dem Klimanormal {REFERENCE_PERIOD}).</p>"
        f'<img src="{{{{IMAGE_URL}}}}" alt="Temperaturverlauf {STATION_NAME}" />'
    )


def main() -> None:
    climatology = load_climatology()
    recent = fetch_recent(STATION_ID)
    obs_date, obs_value = latest_observation(recent)

    doy = climatological_doy(obs_date)
    try:
        diff = anomaly(obs_value, doy, climatology)
    except KeyError as exc:
        raise RuntimeError(f"No climatology entry for day-of-year {doy} (from {obs_date:%Y-%m-%d})") from exc

    render_plot(climatology, obs_date, obs_value, PLOT_PATH)
    html = build_html(obs_date, obs_value, diff)

    publish(
        image_path=str(PLOT_PATH),
        page_id=int(os.environ["WP_PAGE_ID"]),
        html_content=html,
        wp_base_url=os.environ["WP_BASE_URL"].rstrip("/"),
        wp_user=os.environ["WP_USER"],
        wp_app_password=os.environ["WP_APP_PASSWORD"],
    )
    print(f"Published report for {obs_date:%Y-%m-%d}: {obs_value:.1f} °C ({format_diff(diff)} vs. normal)")


if __name__ == "__main__":
    main()
