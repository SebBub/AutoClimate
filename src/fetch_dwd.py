"""Download climate observations from the DWD Climate Data Center."""

import io
import re
import zipfile

import pandas as pd
import requests

BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl"
HOURLY_TU_BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/air_temperature/recent"


def _read_kl_zip(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        data_file = next(n for n in zf.namelist() if n.startswith("produkt_klima_tag_"))
        with zf.open(data_file) as f:
            df = pd.read_csv(f, sep=";", parse_dates=["MESS_DATUM"], index_col="MESS_DATUM")
    df.columns = df.columns.str.strip()
    return df


def fetch_hourly_recent(station_id: int) -> pd.DataFrame:
    """Latest hourly air temperature ("TU" product), indexed by observation timestamp.
    Filename is deterministic — no directory listing needed."""
    sid = f"{station_id:05d}"
    url = f"{HOURLY_TU_BASE}/stundenwerte_TU_{sid}_akt.zip"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        data_file = next(n for n in zf.namelist() if n.startswith("produkt_tu_stunde_"))
        with zf.open(data_file) as f:
            df = pd.read_csv(f, sep=";")
    df.columns = df.columns.str.strip()
    df["MESS_DATUM"] = pd.to_datetime(df["MESS_DATUM"], format="%Y%m%d%H")
    return df.set_index("MESS_DATUM")


def fetch_daily_kl_recent(station_id: int) -> pd.DataFrame:
    """Recent daily climate ("kl") observations, including RSK precipitation, indexed by date.
    Filename is deterministic — no directory listing needed."""
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
