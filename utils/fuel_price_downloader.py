"""Update World Bank Pink Sheet fuel prices without touching JKM."""

from pathlib import Path
from io import BytesIO

import pandas as pd
import requests

URL = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/fuel_prices_2026.csv"


def download() -> pd.DataFrame:
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    sheet = pd.read_excel(BytesIO(response.content), sheet_name="Monthly Prices", header=None)
    rows = sheet[sheet[0].astype(str).str.match(r"2026M\d\d")].copy()
    return pd.DataFrame({
        "month": pd.to_datetime(rows[0].str.replace("M", "-") + "-01"),
        "jkm_usd_mmbtu": float("nan"),
        "japan_lng_usd_mmbtu": pd.to_numeric(rows[9], errors="coerce"),
        "australia_coal_usd_ton": pd.to_numeric(rows[5], errors="coerce"),
    })


def main() -> None:
    fresh = download()
    old = pd.read_csv(OUTPUT, parse_dates=["month"]) if OUTPUT.exists() else None
    if old is not None and fresh.equals(old):
        print("Fuel prices unchanged")
        return
    fresh.to_csv(OUTPUT, index=False)
    print(f"Updated {OUTPUT} through {fresh.month.max():%Y-%m}")


if __name__ == "__main__":
    main()
