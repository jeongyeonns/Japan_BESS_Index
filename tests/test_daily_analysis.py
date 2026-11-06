import numpy as np
import pandas as pd
import pytest

from utils.daily_analysis import (available_dates, select_day, day_quality, comparable_days,
                                 eprx_daily_kpis, jepx_daily_kpis, change_rate, daily_chart)
from utils.eprx_area_groups import AGGREGATE_REGION_GROUPS
from utils.eprx_areas import EPRX_AREA_DISPLAY
from utils.sample_data import generate_sample_data
from utils.jepx_spread import calculate_all_daily_spreads


@pytest.fixture
def eprx():
    return generate_sample_data("2026-10-26")


def test_dates_latest_missing_and_future(eprx):
    data = eprx.loc[pd.to_datetime(eprx.delivery_date).ne(pd.Timestamp("2026-10-18"))]
    dates = available_dates(data, "2026-10-19")
    assert pd.Timestamp(dates[0]) == pd.Timestamp("2026-10-19")
    assert pd.Timestamp("2026-10-18") not in dates
    assert not comparable_days(data, "2026-10-19", ["Tokyo"], "eprx")


@pytest.mark.parametrize("selection", ["Tokyo", *AGGREGATE_REGION_GROUPS])
def test_eprx_kpis_and_constituent_actual_charts(eprx, selection):
    day = "2026-10-19"
    areas = list(AGGREGATE_REGION_GROUPS.get(selection, [selection]))
    raw = select_day(eprx, day)
    raw = raw.loc[raw.area.isin(areas)]
    result = eprx_daily_kpis(eprx, day, selection)
    assert result["입찰 대비 낙찰률 (%)"] == pytest.approx(raw.awarded_volume.sum() / raw.bid_volume.sum())
    for label, column in [("평균 모집량 (MW)", "procurement_volume"), ("평균 입찰량 (MW)", "bid_volume"), ("평균 낙찰량 (MW)", "awarded_volume")]:
        assert result[label] == pytest.approx(raw.groupby("period_no")[column].sum().mean())
    for column in ["max_price", "award_rate"]:
        chart = daily_chart(eprx, day, areas, EPRX_AREA_DISPLAY, column, "unit", "eprx")
        assert len(chart.data) == len(areas)
        assert list(chart.data[0].x)[::47] == ["00:00", "23:30"]
        for trace, area in zip(chart.data, areas):
            source = raw.loc[raw.area.eq(area)].sort_values("period_no")
            expected = source.max_price if column == "max_price" else source.awarded_volume / source.bid_volume * 100
            np.testing.assert_allclose(trace.y, expected)


def test_incomplete_duplicates_nulls_and_zero(eprx):
    day = pd.Timestamp("2026-10-19")
    raw = select_day(eprx, day)
    assert day_quality(raw, day, ["Tokyo"], "eprx").complete.all()
    damaged = raw.loc[~(raw.area.eq("Tokyo") & raw.period_no.eq(1))]
    assert day_quality(damaged, day, ["Tokyo"], "eprx").observed.iloc[0] == 47
    chart = daily_chart(damaged, day, ["Tokyo"], {}, "max_price", "unit", "eprx")
    assert np.isnan(chart.data[0].y[0])
    assert not comparable_days(pd.concat([eprx.loc[eprx.delivery_date.ne(day)], damaged]), day, ["Tokyo"], "eprx")
    duplicate = pd.concat([raw, raw.loc[raw.area.eq("Tokyo")].iloc[:1]])
    assert not day_quality(duplicate, day, ["Tokyo"], "eprx").complete.all()
    raw.loc[raw.area.eq("Tokyo"), "max_price"] = np.nan
    assert not day_quality(raw, day, ["Tokyo"], "eprx").complete.all()
    assert np.isnan(change_rate(1, 0))
    assert change_rate(12, 10) == pytest.approx(.2)


def test_complete_previous_day_and_missing_constituent(eprx):
    assert comparable_days(eprx, "2026-10-19", ["Tokyo"], "eprx")
    raw = eprx.loc[eprx.area.ne("Tohoku")]
    assert not comparable_days(raw, "2026-10-19", ["Tokyo", "Tohoku"], "eprx")
    assert np.isnan(eprx_daily_kpis(raw, "2026-10-19", "도쿄+도호쿠")["평균 입찰량 (MW)"])


def jepx_data():
    return pd.DataFrame([dict(delivery_date=pd.Timestamp(day), area="Tokyo", period_no=n,
                              price=float(n + offset))
                         for day, offset in [("2026-10-18", 0), ("2026-10-19", 10)] for n in range(1, 49)])


def test_jepx_actual_kpis_chart_and_incomplete():
    data = jepx_data()
    spreads = calculate_all_daily_spreads(data, [2], "nem_best_case")
    result = jepx_daily_kpis(data, spreads, "2026-10-19", "Tokyo", 2, "nem_best_case")
    assert result.average_market_price == 34.5
    assert result.minimum_market_price == 11
    assert result.maximum_market_price == 58
    assert result.average_charge_price == 12.5
    assert result.average_discharge_price == 56.5
    assert result.average_spread == 44
    assert comparable_days(data, "2026-10-19", ["Tokyo"], "jepx")
    chart = daily_chart(data, "2026-10-19", ["Tokyo"], {}, "price", "엔/kWh", "jepx")
    np.testing.assert_allclose(chart.data[0].y, range(11, 59))
    damaged = data.iloc[:-1]
    spreads = calculate_all_daily_spreads(damaged, [2], "nem_best_case")
    result = jepx_daily_kpis(damaged, spreads, "2026-10-19", "Tokyo", 2, "nem_best_case")
    assert np.isnan(result.average_spread)
    assert not comparable_days(damaged, "2026-10-19", ["Tokyo"], "jepx")


def test_legacy_eprx_eight_blocks(eprx):
    raw = select_day(eprx, "2026-10-19")
    raw = raw.loc[raw.period_no.le(8)].assign(delivery_date=pd.Timestamp("2026-03-13"))
    assert day_quality(raw, "2026-03-13", ["Tokyo"], "eprx").complete.all()
    chart = daily_chart(raw, "2026-03-13", ["Tokyo"], {}, "max_price", "unit", "eprx")
    assert list(chart.data[0].x) == [f"{n:02d}:00" for n in range(0, 24, 3)]
