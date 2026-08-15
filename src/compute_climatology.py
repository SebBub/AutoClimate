"""Smoothed day-of-year climatology for a DWD station's daily mean temperature (TMK)."""

import argparse

import pandas as pd

from fetch_dwd import fetch_historical


def day_of_year_climatology(
    temp: pd.Series,
    start_year: int = 1991,
    end_year: int = 2020,
    smooth_radius_days: int = 15,
) -> pd.Series:
    """Smoothed mean daily temperature by day-of-year (1..366), circularly padded
    so the Dec 31 / Jan 1 boundary is smoothed correctly rather than truncated.

    Indexed 1..366 using leap-year-style day-of-year numbering (Feb 29 always
    present as day 60); use climatological_doy() to map a real date onto it.
    """
    temp = temp.replace(-999, pd.NA).dropna()
    ref = temp.loc[f"{start_year}-01-01":f"{end_year}-12-31"]
    doy_mean = ref.groupby([ref.index.month, ref.index.day]).mean()
    doy_mean.index = range(1, len(doy_mean) + 1)

    pad = smooth_radius_days
    padded = pd.concat([doy_mean.tail(pad), doy_mean, doy_mean.head(pad)])
    window = 2 * pad + 1
    smoothed = padded.rolling(window=window, center=True, min_periods=1).mean()
    return smoothed.iloc[pad:-pad].set_axis(doy_mean.index)


def climatological_doy(date: pd.Timestamp) -> int:
    """Map a real calendar date onto the climatology's leap-style 1..366 index,
    independent of whether `date`'s own year is a leap year."""
    return pd.Timestamp(year=2000, month=date.month, day=date.day).dayofyear


def anomaly(today_value: float, day_of_year: int, climatology: pd.Series) -> float:
    return today_value - climatology.loc[day_of_year]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station", type=int, required=True, help="DWD Stations_ID, e.g. 1666")
    parser.add_argument("--out", required=True, help="Output CSV path")
    parser.add_argument("--start-year", type=int, default=1991)
    parser.add_argument("--end-year", type=int, default=2020)
    parser.add_argument("--smooth-radius-days", type=int, default=15)
    args = parser.parse_args()

    df = fetch_historical(args.station)
    climatology = day_of_year_climatology(
        df["TMK"],
        start_year=args.start_year,
        end_year=args.end_year,
        smooth_radius_days=args.smooth_radius_days,
    )
    out = climatology.rename("tmk_normal").rename_axis("day_of_year").reset_index()
    out.to_csv(args.out, index=False)
    print(f"Wrote {len(out)} day-of-year climatology rows to {args.out}")


if __name__ == "__main__":
    main()
