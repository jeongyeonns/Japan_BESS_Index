import pandas as pd
import pytest

from utils.jkm_jpx_manual_update import expected_dates, merge_prices, read_prices


SOURCE = "https://www.jpx.co.jp/markets/derivatives/special-quotation/"


def prices(rows):
    return pd.DataFrame(rows, columns=[
        "contract_month", "evaluation_start", "evaluation_end", "comparison_month", "settlement_price_yen_mmbtu"
    ]).assign(
        evaluation_start=lambda frame: pd.to_datetime(frame.evaluation_start),
        evaluation_end=lambda frame: pd.to_datetime(frame.evaluation_end),
        comparison_month=lambda frame: pd.to_datetime(frame.comparison_month),
    )


def test_existing_2026_jpx_prices_and_periods_are_valid():
    data = read_prices("data/jkm_prices_jpx_2026.csv")
    assert data.contract_month.tolist() == [f"2026-{month:02d}" for month in range(1, 12)]
    assert data.iloc[-1].settlement_price_yen_mmbtu == 4184.4
    assert expected_dates("2026-04") == (
        pd.Timestamp("2026-02-16"), pd.Timestamp("2026-03-15"), pd.Timestamp("2026-03-01")
    )


def test_merge_adds_only_new_contract_and_records_provenance():
    existing = prices([["2026-04", "2026-02-16", "2026-03-15", "2026-03-01", 2530.8]])
    incoming = prices([["2026-05", "2026-03-16", "2026-04-15", "2026-04-01", 3058.8]])
    merged, metadata, corrections = merge_prices(existing, incoming, SOURCE, "2026-04-20")
    assert merged.contract_month.tolist() == ["2026-04", "2026-05"]
    assert metadata.to_dict("records") == [{"contract_month": "2026-05", "source_url": SOURCE, "verified_at": "2026-04-20"}]
    assert corrections.empty


def test_merge_rejects_duplicate_correction_without_explicit_permission():
    existing = prices([["2026-04", "2026-02-16", "2026-03-15", "2026-03-01", 2530.8]])
    incoming = prices([["2026-04", "2026-02-16", "2026-03-15", "2026-03-01", 2500.0]])
    with pytest.raises(ValueError, match="--allow-corrections"):
        merge_prices(existing, incoming, SOURCE, "2026-04-20")
    merged, _, corrections = merge_prices(existing, incoming, SOURCE, "2026-04-20", allow_corrections=True)
    assert merged.iloc[0].settlement_price_yen_mmbtu == 2500.0
    assert corrections.iloc[0].previous_price_yen_mmbtu == 2530.8


def test_merge_does_not_change_data_when_price_already_exists():
    existing = prices([["2026-04", "2026-02-16", "2026-03-15", "2026-03-01", 2530.8]])
    merged, metadata, corrections = merge_prices(existing, existing.copy(), SOURCE, "2026-04-20")
    assert merged.equals(existing)
    assert metadata.empty
    assert corrections.empty


def test_invalid_evaluation_period_is_rejected():
    bad = prices([["2026-04", "2026-02-15", "2026-03-15", "2026-03-01", 2530.8]])
    with pytest.raises(ValueError, match="Invalid evaluation period"):
        merge_prices(bad.iloc[:0], bad, SOURCE, "2026-04-20")
