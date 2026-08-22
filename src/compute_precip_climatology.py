"""Long-term monthly precipitation normal for a DWD station's daily rainfall (RSK)."""

import argparse

import pandas as pd

from fetch_dwd import fetch_historical


def monthly_precip_climatology(
    precip: pd.Series,
    start_year: int = 1991,
    end_year: int = 2020,
) -> pd.Series:
    """Average accumulated precipitation (mm) by calendar month (1..12), from each reference
    year's monthly total rather than a single pooled sum — so one unusually wet or dry year
    doesn't get weighted by how many days of data it happened to have."""
    precip = precip.replace(-999, pd.NA).dropna()
    ref = precip.loc[f"{start_year}-01-01":f"{end_year}-12-31"]
    monthly_sums = ref.groupby([ref.index.year, ref.index.month]).sum()
    monthly_sums.index = monthly_sums.index.set_names(["year", "month"])
    return monthly_sums.groupby("month").mean()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station", type=int, required=True, help="DWD Stations_ID, e.g. 1666")
    parser.add_argument("--out", required=True, help="Output CSV path")
    parser.add_argument("--start-year", type=int, default=1991)
    parser.add_argument("--end-year", type=int, default=2020)
    args = parser.parse_args()

    df = fetch_historical(args.station)
    climatology = monthly_precip_climatology(
        df["RSK"],
        start_year=args.start_year,
        end_year=args.end_year,
    )
    out = climatology.rename("rsk_normal").rename_axis("month").reset_index()
    out.to_csv(args.out, index=False)
    print(f"Wrote {len(out)} monthly precipitation climatology rows to {args.out}")


if __name__ == "__main__":
    main()
