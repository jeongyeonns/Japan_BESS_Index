import numpy as np
import pandas as pd
from utils.eprx_market_trend import weekly_market_trend, market_trend_figure
from utils.eprx_loader import load_all_eprx_data
from test_eprx_index import frame


def test_boundary_duration_region_product_and_missing():
    old = frame("2026-03-13", [2] * 8).assign(procurement_volume=100, volume_unit="MW")
    new = frame("2026-03-14").assign(procurement_volume=200, volume_unit="MW")
    unrelated = new.assign(area="Kyushu", procurement_volume=999)
    other = new.assign(original_product="other", procurement_volume=999)
    data = pd.concat([old, new, unrelated, other], ignore_index=True)
    rows = weekly_market_trend(data, "Tokyo", "2026-03-09", "2026-03-16")
    assert rows.procurement.iloc[:2].tolist() == [100, 200]
    assert rows.max_price.iloc[:2].tolist() == [2, 5]
    assert rows.expected_periods.tolist() == [40, 96, 336]
    assert rows.procurement_hours.tolist() == [24, 24, 0]
    assert pd.isna(rows.procurement.iloc[2])
    assert rows.incomplete.all()
    fig = market_trend_figure(rows)
    assert fig.data[0].type == "bar" and fig.data[1].yaxis == "y2"
    assert fig.data[1].connectgaps is False
    assert sum(t.showlegend for t in fig.data) == 2
    assert "?" not in fig.to_json() and "\ufffd" not in fig.to_json()


def test_duplicates_no_award_zero_and_time_mean():
    data = frame(prices=[0, 5, 10, 15]).assign(procurement_volume=[0, 100, np.nan, 300], volume_unit="MW")
    data.loc[1, "awarded_volume"] = 0
    data = pd.concat([data, data.iloc[[3]]], ignore_index=True)
    row = weekly_market_trend(data, "Tokyo", "2026-11-02", "2026-11-02").iloc[0]
    assert row.procurement == 50  # zero MW is observed, missing and duplicates excluded
    assert row.max_price == 5  # true zero price retained, no-award excluded
    assert row.duplicate_rows == 2
    assert row.procurement_periods == row.price_periods == 2


def test_actual_csv_tso_column_and_panel(monkeypatch):
    import index_app
    data, *_ = load_all_eprx_data(index_app.EPRX_DIRECTORY)
    rows = weekly_market_trend(data, "Tokyo", "2026-04-06", "2026-04-06")
    raw = data.loc[data.area.eq("Tokyo") & data.delivery_date.between("2026-04-06", "2026-04-12")]
    assert len(raw) == 336
    assert rows.procurement.iloc[0] == raw.procurement_volume.mean()
    assert rows.max_price.iloc[0] == raw.loc[raw.awarded_volume.gt(0), "max_price"].mean()
    texts, charts = [], []
    monkeypatch.setattr(index_app.st, "markdown", lambda t: texts.append(t))
    monkeypatch.setattr(index_app.st, "caption", lambda t: texts.append(t))
    monkeypatch.setattr(index_app.st, "altair_chart", lambda f, **k: charts.append(f))
    history, _ = index_app.weekly_results(data, "EPRX", "Tokyo", pd.Timestamp("2026-04-06"), pd.Timestamp("2026-04-06"))
    index_app.trend(history, pd.Timestamp("2026-04-06"), "EPRX_trend", rows)
    assert any("TSO 조달지역 기준" in t and "전원 소재지역별" in t for t in texts)
    assert all("?" not in t and "\ufffd" not in t for t in texts)
    assert len(charts) == 1
    chart = charts[0]
    spec = chart.to_dict()
    assert spec["resolve"]["scale"]["y"] == "independent"
    left = spec["layer"][0]["layer"][0]
    right = spec["layer"][1]
    assert right["encoding"]["y"]["axis"]["orient"] == "right"
    assert right["encoding"]["y"]["title"] == "주간 평균 모집량 (MW)"
    assert right["mark"]["strokeDash"] == [4, 4]
    assert right["mark"]["point"]["shape"] == "circle"
    assert left["encoding"]["color"] == right["encoding"]["color"]
    assert len(right["encoding"]["color"]["scale"]["domain"]) == 5
    assert right["encoding"]["color"]["scale"]["range"][-1] == "#808080"
    assert chart.layer[1].data.procurement.tolist() == rows.procurement.tolist()
    assert sorted(chart.layer[0].layer[0].data.value) == sorted(history.value)


def test_combined_regime_and_missing_segments(monkeypatch):
    import index_app
    data = pd.concat([frame("2026-03-13", [2] * 8), frame("2026-03-14")], ignore_index=True).assign(procurement_volume=100, volume_unit="MW")
    first, last = pd.Timestamp("2026-03-09"), pd.Timestamp("2026-03-23")
    rows = weekly_market_trend(data, "Tokyo", first, last)
    history, _ = index_app.weekly_results(data, "EPRX", "Tokyo", first, last)
    charts = []
    monkeypatch.setattr(index_app.st, "altair_chart", lambda chart, **k: charts.append(chart))
    index_app.trend(history, first, "EPRX_trend", rows)
    volume = charts[0].layer[1].data
    assert volume.loc[volume.week.eq(first), "segment"].nunique() == 2
    assert volume.loc[volume.week.gt(first), "procurement"].isna().all()
    assert "EPRX 1차 조정력 주차별 시장 동향" not in open(index_app.__file__, encoding="utf-8").read()
