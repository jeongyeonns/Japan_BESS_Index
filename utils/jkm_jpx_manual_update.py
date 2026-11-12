"""Validate and merge authorised manual JPX JKM settlement-price updates.

This module deliberately never downloads or parses JPX content. JPX's terms
require permission for collection, secondary use and redistribution. It is for
data supplied under a separate, authorised process only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PRICE_COLUMNS = [
    "contract_month", "evaluation_start", "evaluation_end", "comparison_month",
    "settlement_price_yen_mmbtu",
]
METADATA_COLUMNS = ["contract_month", "source_url", "verified_at"]
CORRECTION_COLUMNS = [
    "contract_month", "previous_price_yen_mmbtu", "corrected_price_yen_mmbtu",
    "source_url", "verified_at",
]


def read_prices(path: Path | str) -> pd.DataFrame:
    prices = pd.read_csv(path, dtype={"contract_month": "string"})
    if list(prices.columns) != PRICE_COLUMNS:
        raise ValueError(f"Unexpected JKM columns in {path}")
    for column in ("evaluation_start", "evaluation_end", "comparison_month"):
        prices[column] = pd.to_datetime(prices[column], errors="raise")
    prices["settlement_price_yen_mmbtu"] = pd.to_numeric(prices["settlement_price_yen_mmbtu"], errors="raise")
    validate_prices(prices)
    return prices


def expected_dates(contract_month: str) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    month = pd.Period(contract_month, freq="M").to_timestamp()
    evaluation_start = (month - pd.DateOffset(months=2)).replace(day=16)
    evaluation_end = (month - pd.DateOffset(months=1)).replace(day=15)
    return evaluation_start, evaluation_end, evaluation_end.to_period("M").to_timestamp()


def validate_prices(prices: pd.DataFrame) -> None:
    if prices.empty:
        return
    if prices.contract_month.isna().any() or not prices.contract_month.str.fullmatch(r"\d{4}-\d{2}").all():
        raise ValueError("contract_month must use YYYY-MM")
    if prices.contract_month.duplicated().any():
        raise ValueError("contract_month must be unique")
    if prices.settlement_price_yen_mmbtu.isna().any() or (prices.settlement_price_yen_mmbtu <= 0).any():
        raise ValueError("settlement_price_yen_mmbtu must be positive")
    for row in prices.itertuples(index=False):
        expected = expected_dates(row.contract_month)
        if (row.evaluation_start, row.evaluation_end, row.comparison_month) != expected:
            raise ValueError(f"Invalid evaluation period for {row.contract_month}")


def merge_prices(existing, incoming, source_url, verified_at, *, allow_corrections=False):
    """Return merged prices, source metadata and correction audit entries."""
    if not source_url.startswith("https://"):
        raise ValueError("source_url must be an https URL")
    verified = pd.Timestamp(verified_at).strftime("%Y-%m-%d")
    validate_prices(existing)
    validate_prices(incoming)
    current = existing.set_index("contract_month", drop=False)
    merged = existing.copy()
    metadata, corrections = [], []
    for row in incoming.itertuples(index=False):
        if row.contract_month not in current.index:
            merged = pd.concat([merged, pd.DataFrame([row._asdict()])], ignore_index=True)
            metadata.append({"contract_month": row.contract_month, "source_url": source_url, "verified_at": verified})
            continue
        old = current.loc[row.contract_month]
        if old.settlement_price_yen_mmbtu == row.settlement_price_yen_mmbtu:
            continue
        if not allow_corrections:
            raise ValueError(f"Price correction detected for {row.contract_month}; rerun with --allow-corrections")
        metadata.append({"contract_month": row.contract_month, "source_url": source_url, "verified_at": verified})
        corrections.append({
            "contract_month": row.contract_month,
            "previous_price_yen_mmbtu": old.settlement_price_yen_mmbtu,
            "corrected_price_yen_mmbtu": row.settlement_price_yen_mmbtu,
            "source_url": source_url,
            "verified_at": verified,
        })
        merged.loc[merged.contract_month.eq(row.contract_month), PRICE_COLUMNS] = list(row)
    return (merged.sort_values("contract_month").reset_index(drop=True),
            pd.DataFrame(metadata, columns=METADATA_COLUMNS),
            pd.DataFrame(corrections, columns=CORRECTION_COLUMNS))


def append_unique(path, rows, columns):
    if rows.empty:
        return False
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=columns)
    combined = pd.concat([existing, rows], ignore_index=True).drop_duplicates()
    if combined.equals(existing):
        return False
    combined.to_csv(path, index=False)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--source-url")
    parser.add_argument("--verified-at")
    parser.add_argument("--allow-corrections", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--prices", type=Path, default=ROOT / "data/jkm_prices_jpx_2026.csv")
    parser.add_argument("--metadata", type=Path, default=ROOT / "data/jkm_prices_jpx_metadata.csv")
    parser.add_argument("--corrections", type=Path, default=ROOT / "data/jkm_prices_jpx_corrections.csv")
    args = parser.parse_args()
    existing = read_prices(args.prices)
    if args.status:
        latest = existing.iloc[-1]
        print(f"Latest stored contract: {latest.contract_month}; price: {latest.settlement_price_yen_mmbtu}")
        return
    if not (args.input and args.source_url and args.verified_at):
        parser.error("--input, --source-url and --verified-at are required unless --status is used")
    incoming = read_prices(args.input)
    merged, metadata, corrections = merge_prices(existing, incoming, args.source_url, args.verified_at,
                                                  allow_corrections=args.allow_corrections)
    changed = not merged.equals(existing)
    if changed:
        serialised = merged.copy()
        for column in ("evaluation_start", "evaluation_end", "comparison_month"):
            serialised[column] = serialised[column].dt.strftime("%Y-%m-%d")
        serialised.to_csv(args.prices, index=False)
    metadata_changed = append_unique(args.metadata, metadata, METADATA_COLUMNS)
    corrections_changed = append_unique(args.corrections, corrections, CORRECTION_COLUMNS)
    print("JKM data updated" if changed or metadata_changed or corrections_changed else "JKM data unchanged")


if __name__ == "__main__":
    main()
