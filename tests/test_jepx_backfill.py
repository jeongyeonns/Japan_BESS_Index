from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from utils.jepx_areas import JEPX_DETAIL_AREAS
from utils.jepx_loader import load_all_jepx_data, read_jepx_file, normalize_jepx_data
from utils.jepx_index import calculate_week_index
from index_app import weekly_results

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def data():
    combined, _, errors, warnings, _ = load_all_jepx_data(ROOT / "data/jepx/raw")
    assert errors.empty and warnings.empty
    return combined


def test_q1_coverage_and_no_duplicate_keys(data):
    q1 = data.loc[data.delivery_date.between("2026-01-01", "2026-03-31")]
    assert set(JEPX_DETAIL_AREAS).issubset(set(q1.area))
    for area in JEPX_DETAIL_AREAS:
        region = q1.loc[q1.area.eq(area)]
        assert len(region) == 4320
        assert region.delivery_date.nunique() == 90
        assert region.groupby("delivery_date").period_no.nunique().eq(48).all()
        assert np.isfinite(region.price.to_numpy()).all()
    assert not data.duplicated(["delivery_date", "period_no", "area"]).any()


def test_january_manual_calculation_and_boundary_week(data):
    daily, summary = calculate_week_index(data, "2026-01-12", "Tokyo")
    assert summary["valid_days"] == 7
    prices = data.loc[data.area.eq("Tokyo") & data.delivery_date.between("2026-01-12", "2026-01-18")]
    hourly = prices.sort_values(["delivery_date", "period_no"]).price.to_numpy().reshape(7, 24, 2).mean(axis=2)
    ordered = np.sort(hourly, axis=1)
    for h in (2, 4):
        spreads = ordered[:, -h:].mean(axis=1) - ordered[:, :h].mean(axis=1)
        np.testing.assert_allclose(daily[f"tb{h}"], spreads)
        assert summary[f"tb{h}_index"] == pytest.approx(spreads.mean() * 1000 * h * 365)
    for area in JEPX_DETAIL_AREAS:
        assert calculate_week_index(data, "2026-03-30", area)[1]["valid_days"] == 7
    history, _ = weekly_results(data, "JEPX", "Tokyo", pd.Timestamp("2026-01-05"), pd.Timestamp("2026-03-30"))
    assert history.value.notna().all()
    assert history.valid_days.eq(7).all()


def test_existing_april_data_and_weekly_results_unchanged(data):
    path = ROOT / "data/jepx/raw/spot_summary_2026.csv"
    _, before = normalize_jepx_data(read_jepx_file(path), path)
    columns = ["delivery_date", "area", "period_no", "price"]
    after = data.loc[data.delivery_date.ge("2026-04-01"), columns]
    pd.testing.assert_frame_equal(before[columns].sort_values(columns[:3]).reset_index(drop=True),
                                  after.sort_values(columns[:3]).reset_index(drop=True))
    # Boundary week intentionally gains March 30–31; subsequent weeks are identical.
    last = before.delivery_date.max()
    last -= pd.Timedelta(days=last.weekday())
    for week in pd.date_range("2026-04-06", last, freq="W-MON"):
        assert calculate_week_index(data, week, "Tokyo")[1] == calculate_week_index(before, week, "Tokyo")[1]
