from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from index_app import weekly_results, LEGACY_LABEL, MODERN_LABEL
from utils.eprx_index import calculate_eprx_legacy_week_index, calculate_eprx_week_index
from utils.eprx_loader import read_eprx_file, normalize_eprx_data
from test_eprx_index import frame

ROOT = Path(__file__).resolve().parents[1]


def legacy(data):
    return calculate_eprx_legacy_week_index(data, "2026-01-12", "Tokyo")


def test_legacy_whole_blocks_and_units():
    _, summary = legacy(frame("2026-01-12", [5] * 8))
    assert summary.iloc[0].annual_index == 21_900_000
    assert summary.used_periods.tolist() == [2, 4, 6, 8]
    daily, summary = legacy(frame("2026-01-12", list(range(8))))
    for row in summary.itertuples():
        count = row.scenario // 6
        assert row.annual_index == sum(range(8 - count, 8)) * 6 * 1000 * 365
    assert daily.iloc[0].selected_periods == 2


def test_legacy_invalid_missing_no_award_zero_and_regime():
    data = frame("2026-01-12", [5] * 8)
    data.loc[0, "max_price"] = np.nan
    data.loc[1, "awarded_volume"] = 0
    data.loc[2, "max_price"] = 0
    daily, summary = legacy(data)
    assert daily.iloc[0].valid_periods == 6
    assert summary.valid_days.tolist() == [1, 1, 1, 0]
    assert pd.isna(summary.iloc[-1].annual_index)
    assert legacy(frame("2026-01-12", [0] * 8))[1].annual_index.eq(0).all()
    for column, value in (("price_unit", "円/kWh"), ("original_product", "other"), ("period_no", 9)):
        bad = frame("2026-01-12", [5] * 8)
        bad.loc[0, column] = value
        assert legacy(bad)[1].annual_index.isna().all()
    assert legacy(pd.concat([data, data.iloc[:1]]))[1].annual_index.isna().all()
    assert calculate_eprx_legacy_week_index(frame(), "2026-11-02", "Tokyo")[1].annual_index.isna().all()


def test_transition_week_is_split_not_averaged():
    data = pd.concat([frame(str(d.date()), [5] * 8) for d in pd.date_range("2026-03-09", periods=5)] +
                     [frame(str(d.date()), [10] * 48) for d in pd.date_range("2026-03-14", periods=2)], ignore_index=True)
    start = pd.Timestamp("2026-03-09")
    history, daily = weekly_results(data, "EPRX", "Tokyo", start, start)
    assert len(history) == 8
    old = history.loc[history.regime.eq(LEGACY_LABEL)]
    new = history.loc[history.regime.eq(MODERN_LABEL)]
    assert old.valid_days.eq(5).all() and old.expected_days.eq(5).all()
    assert new.valid_days.eq(2).all() and new.expected_days.eq(2).all()
    assert old.iloc[0].value == 21_900_000
    assert new.iloc[0].value == 43_800_000
    assert not daily.duplicated(["date", "scenario"]).any()


def test_actual_q1_sources_and_independent_legacy_calculation():
    parts = []
    for name in ("202601_1-0_prompt.csv", "202602_1-0_prompt.csv", "202603_1-0_0301-0313_prompt.csv", "202603_1-0_0314-0331_prompt.csv"):
        path = ROOT / "data/eprx" / name
        parts.append(normalize_eprx_data(read_eprx_file(path), path))
    data = pd.concat(parts, ignore_index=True)
    assert data.delivery_date.nunique() == 90
    assert data.area.nunique() == 9
    assert not data.duplicated(["delivery_date", "area", "period_no"]).any()
    old = data.loc[data.delivery_date.lt("2026-03-14")]
    new = data.loc[data.delivery_date.ge("2026-03-14")]
    assert old.groupby(["delivery_date", "area"]).period_no.nunique().eq(8).all()
    assert new.groupby(["delivery_date", "area"]).period_no.nunique().eq(48).all()
    for area in data.area.unique():
        for week, calculate, factor in (("2026-01-12", calculate_eprx_legacy_week_index, 6), ("2026-03-16", calculate_eprx_week_index, 1)):
            _, summary = calculate(data, week, area)
            selected = data.loc[data.area.eq(area) & data.delivery_date.between(week, pd.Timestamp(week) + pd.Timedelta(days=6))]
            for row in summary.itertuples():
                amounts = []
                count = row.scenario // factor
                for _, group in selected.groupby("delivery_date"):
                    prices = sorted(group.loc[group.awarded_volume.gt(0), "max_price"].dropna(), reverse=True)
                    if len(prices) >= count:
                        amounts.append(sum(prices[:count]) * factor * 1000)
                assert row.valid_days == len(amounts)
                assert row.annual_index == pytest.approx(np.mean(amounts) * 365)
