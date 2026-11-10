from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from index_app import change, weekly_results, eprx_quality, trend
from test_eprx_index import frame
from test_jepx_index import day_frame

ROOT = Path(__file__).resolve().parents[1]


def test_jepx_chart_display_units_preserve_values_and_eprx_axes():
    start = pd.Timestamp("2026-11-02")
    history, _ = weekly_results(day_frame(), "JEPX", "Tokyo", start, start + pd.Timedelta(days=14))
    original = history.copy(deep=True)
    with patch("index_app.st.altair_chart") as render, patch("index_app.st.caption"):
        trend(history, start, "JEPX_trend")
        chart = render.call_args.args[0]
        spec = chart.to_dict()
        encoding = spec["layer"][0]["encoding"]
        assert spec["title"] == "주차별 차익거래 수익기회"
        assert encoding["y"]["field"] == "value"
        assert encoding["y"]["title"] == "만 엔/MW/년"
        assert encoding["y"]["axis"]["labelExpr"] == "format(datum.value / 10000, ',.0f')"
        assert encoding["x"]["axis"]["format"] == "%-m/%-d"
        assert "2시간형 (TB2)" in encoding["color"]["legend"]["labelExpr"]
        assert encoding["detail"]["field"] == "segment"
        assert any(t["field"] == "value" and t["title"] == "엔/MW/년" for t in encoding["tooltip"])
        assert chart.layer[0].data.value.isna().sum() == history.value.isna().sum()
        trend(history, start, "EPRX_trend")
        eprx = render.call_args.args[0].to_dict()["layer"][0]["encoding"]
        assert eprx["y"]["title"] == "엔/MW/년"
        assert eprx["y"]["axis"] == {"format": ","}
        assert "axis" not in eprx["x"]
        assert "legend" not in eprx["color"]
    pd.testing.assert_frame_equal(history, original)


def test_weekly_gaps_and_delta():
    start = pd.Timestamp("2026-11-02")
    history, _ = weekly_results(day_frame(), "JEPX", "Tokyo", start, start + pd.Timedelta(days=7))
    assert history.loc[history.week.eq(start), "valid_days"].eq(1).all()
    assert history.loc[history.week.gt(start), "value"].isna().all()
    assert change(110, 100) == "+10.0% 전주 대비"
    assert change(100, float("nan")) is None
    assert change(100, 0) is None
    data = frame()
    data.loc[0, "awarded_volume"] = 0
    data.loc[1, "max_price"] = 0
    data.loc[2, "max_price"] = float("nan")
    quality = eprx_quality(data, start, "Tokyo").iloc[0]
    assert quality["고유 코마 수"] == 48
    assert quality["낙찰량 0"] == quality["낙찰량 양수·0엔"] == quality["가격 결측"] == 1


def test_actual_dashboard_navigation_and_missing_week():
    app = AppTest.from_file(str(ROOT / "index_app.py")).run(timeout=180)
    assert not app.exception
    assert app.title[0].value == "Japan BESS Market Opportunity Index"
    assert len(app.get("vega_lite_chart")) == 3
    for area in ("Tokyo", "Chubu", "Kyushu"):
        app.selectbox[1].select(area)
        app.selectbox[0].select(pd.Timestamp("2026-11-02")).run(timeout=60)
        assert not app.exception
        assert len(app.metric) == 6
        assert app.metric[0].value != "계산 불가"
    app.multiselect[0].set_value(["12코마"]).run(timeout=60)
    assert not app.exception
    app.multiselect[0].set_value([]).run(timeout=60)
    assert not app.exception
    # Backfilled JEPX is available; legacy EPRX remains excluded.
    app.selectbox[0].select(pd.Timestamp("2026-01-05")).run(timeout=60)
    assert not app.exception
    assert all(m.value != "계산 불가" for m in app.metric[:2])
    assert all(m.value == "계산 불가" for m in app.metric[2:])
    assert app.warning


def test_no_source_screen():
    with patch("utils.jepx_loader.find_jepx_files", return_value=pd.DataFrame()), patch("utils.eprx_loader.find_eprx_files", return_value=[]):
        app = AppTest.from_file(str(ROOT / "index_app.py")).run(timeout=20)
    assert not app.exception
    assert not app.metric
    assert any("분석 가능한 원자료가 없습니다" in w.value for w in app.warning)
