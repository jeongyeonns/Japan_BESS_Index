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
    monkeypatch.setattr(index_app.st, "plotly_chart", lambda f, **k: charts.append(f))
    index_app.eprx_market_panel(data, "Tokyo", pd.Timestamp("2026-04-06"), pd.Timestamp("2026-04-06"))
    assert any("TSO 조달지역별" in t and "전원 소재지역별" in t for t in texts)
    assert any("https://www.eprx.or.jp/information/results.php" in t for t in texts)
    assert all("?" not in t and "\ufffd" not in t for t in texts)
    assert len(charts) == 1
