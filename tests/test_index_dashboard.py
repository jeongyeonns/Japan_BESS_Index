from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from index_app import change, weekly_results, eprx_quality
from test_eprx_index import frame
from test_jepx_index import day_frame

ROOT = Path(__file__).resolve().parents[1]


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
    # Real legacy EPRX week; JEPX has no source observations here.
    app.selectbox[0].select(pd.Timestamp("2026-01-05")).run(timeout=60)
    assert not app.exception
    assert all(m.value == "계산 불가" for m in app.metric)
    assert app.warning


def test_no_source_screen():
    with patch("utils.jepx_loader.find_jepx_files", return_value=pd.DataFrame()), patch("utils.eprx_loader.find_eprx_files", return_value=[]):
        app = AppTest.from_file(str(ROOT / "index_app.py")).run(timeout=20)
    assert not app.exception
    assert not app.metric
    assert any("분석 가능한 원자료가 없습니다" in w.value for w in app.warning)
