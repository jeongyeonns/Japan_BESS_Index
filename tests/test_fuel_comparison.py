import pandas as pd
from index_app import load_fuel_prices, load_jkm_prices, monthly_jepx_spreads, build_fuel_comparison_figure


def test_fuel_figure_has_three_visible_traces_and_secondary_axis():
    import index_app
    jepx = pd.DataFrame({"month": pd.to_datetime(["2026-01-01", "2026-02-01"]), "tb2": [2.0, 3.0], "tb4": [3.0, 4.0]})
    fuel = pd.DataFrame({"month": pd.to_datetime(["2026-01-01", "2026-02-01"]), "japan_lng_usd_mmbtu": [10.0, 11.0], "australia_coal_usd_ton": [100.0, 101.0]})
    jkm = pd.DataFrame({"comparison_month": pd.to_datetime(["2026-01-01", "2026-02-01"]), "settlement_price_yen_mmbtu": [1500.0, 1600.0]})
    yen = "\uc5d4"
    label = bytes.fromhex("ec97b0eb8f99eab080eab2a9").decode()
    fig = build_fuel_comparison_figure(jepx, fuel, jkm, "settlement_price_yen_mmbtu", f"JKM {label}(JPX)", f"{yen}/MMBtu")
    assert len(fig.data) == 3
    assert [trace.name for trace in fig.data] == [f"JEPX TB2 ({yen}/kWh)", f"JEPX TB4 ({yen}/kWh)", f"JKM {label}(JPX) ({yen}/MMBtu)"]
    assert list(fig.data[2].y) == [1500.0, 1600.0]
    assert fig.data[2].yaxis == "y2"
    assert all(trace.showlegend is not False for trace in fig.data)
    assert pd.Timestamp(list(fig.data[0].x)[0]).year == 2026


def test_rendered_fuel_labels_sources_and_plotly_text(monkeypatch):
    import json
    from pathlib import Path
    import index_app
    texts, figures = [], []
    monkeypatch.setattr(index_app.st, "markdown", lambda text: texts.append(text))
    monkeypatch.setattr(index_app.st, "caption", lambda text: texts.append(text))
    monkeypatch.setattr(index_app.st, "plotly_chart", lambda fig, **kwargs: figures.append(fig))
    fuel = load_fuel_prices(("labels", 1))
    jkm = load_jkm_prices(("labels", 1))
    raw, *_ = index_app.load_all_jepx_data(index_app.DATA_DIRECTORY)
    dates = raw.delivery_date
    first = dates.min() - pd.Timedelta(days=dates.min().weekday())
    last = dates.max() - pd.Timedelta(days=dates.max().weekday())
    _, daily = index_app.weekly_results(raw, "JEPX", "Tokyo", first, last)
    jepx = index_app.comparison_jepx_periods(daily)
    monkeypatch.setattr(index_app.st, "selectbox", lambda *args, **kwargs: "\uc8fc\ubcc4")
    index_app.fuel_comparison_charts(daily, fuel, jkm)
    assert texts[0] == "### JEPX 스프레드와 발전연료 가격 추이 비교"
    assert texts[1] == '\u203b JKM \uc5f0\ub3d9\uac00\uaca9\uacfc \uc77c\ubcf8 LNG \uc218\uc785\uac00\uaca9\uc740 \ud604\uc7ac \uc6d4\ubcc4 \uc790\ub8cc\ub9cc \ud655\ubcf4\ub418\uc5b4 \uc788\uc2b5\ub2c8\ub2e4.  \n\ub530\ub77c\uc11c JEPX \uc2a4\ud504\ub808\ub4dc\ub9cc \uc120\ud0dd\ud55c \uc8fc\uae30\uc5d0 \ub530\ub77c \ud45c\uc2dc\ud558\uba70, \uc5f0\ub8cc\uac00\uaca9\uc740 \uc6d4\ubcc4 \uae30\uc900\uc73c\ub85c \uc81c\uacf5\ud569\ub2c8\ub2e4.'
    labels = ["JKM 연동가격(JPX)", "일본 LNG 수입가격"]
    units = ["엔/MMBtu", "USD/MMBtu"]
    assert len(figures) == 2
    for fig, label, unit in zip(figures, labels, units):
        assert f"#### {label}" in texts
        assert [trace.name for trace in fig.data] == ["JEPX TB2 (엔/kWh)", "JEPX TB4 (엔/kWh)", f"{label} ({unit})"]
        assert fig.layout.xaxis.title.text == "\uc8fc\ucc28 \uc2dc\uc791\uc77c (\uc6d4\uc694\uc77c)"
        assert fig.layout.yaxis.title.text == "JEPX 스프레드 (엔/kWh)"
        assert fig.layout.yaxis2.title.text == unit
        assert fig.data[2].yaxis == "y2"
        # Includes trace names, axis/legend titles and any hover text/templates.
        payload = fig.to_json()
        assert "?" not in payload and "\ufffd" not in payload
    sources = [text for text in texts if text.startswith("출처:")]
    assert len(sources) == 2
    assert all("[JEPX 스폿시장 가격](https://www.jepx.jp/electricpower/market-data/spot/)" in text for text in sources)
    assert "[JPX LNG (Platts JKM) 선물 최종정산가격](https://www.jpx.co.jp/markets/derivatives/special-quotation/)" in sources[0]
    assert "[World Bank Pink Sheet (LNG Japan)](https://www.worldbank.org/en/research/commodity-markets)" in sources[1]
    assert any("평가기간 종료월을 기준으로 표시한 값입니다." in text for text in texts)
    assert len([text for text in texts if "  \n" in text]) == 3
    assert all("최신 확보월" in text and "2026-10" in text for text in sources)
    assert all(fig.layout.yaxis.range == figures[0].layout.yaxis.range for fig in figures)
    columns = ["settlement_price_yen_mmbtu", "japan_lng_usd_mmbtu"]
    for fig, column, color, unit in zip(figures, columns, ["#DC2626", "#7C3AED"], units):
        prices = jkm.rename(columns={"comparison_month": "month"}) if column == columns[0] else fuel
        expected = prices.loc[prices.month.ge("2026-01-01") & prices[column].notna()].sort_values("month")
        import numpy as np
        for trace, field in zip(fig.data[:2], ["tb2", "tb4"]):
            np.testing.assert_allclose(trace.y, jepx[field], equal_nan=True)
            assert list(pd.to_datetime(trace.x)) == jepx.month.tolist()
        assert list(fig.data[2].y) == expected[column].tolist()
        assert list(pd.to_datetime(fig.data[2].x)) == expected.month.tolist()
        assert len(fig.layout.shapes) == (1 if column == columns[0] else 0)
        if column == columns[0]:
            assert fig.layout.shapes[0].x0 == "2026-02-28"
            assert fig.layout.shapes[0].x1 == "2026-02-28"
        assert [t.yaxis for t in fig.data] == ["y", "y", "y2"]
        assert [t.line.color for t in fig.data] == ["#2563EB", "#0F766E", color]
        assert [t.line.dash for t in fig.data] == ["solid", "solid", "dot"]
        assert fig.data[2].line.width == 3 and fig.data[2].marker.size == 7
        assert unit in fig.data[2].hovertemplate
        lower, upper = fig.layout.yaxis2.range
        assert 0 < lower < min(fig.data[2].y) < max(fig.data[2].y) < upper
    assert sum("오른쪽 Y축 범위를 조정했습니다." in text for text in texts) == 2
    assert all("?" not in text and "\ufffd" not in text and "{label}" not in text for text in texts)
    Path(index_app.__file__).read_bytes().decode("utf-8", errors="strict")


def test_jpx_jkm_contract_period_and_unit():
    prices = load_jkm_prices(("data/jkm_prices_jpx_2026.csv", 1))
    row = prices.loc[prices.contract_month.eq("2026-04")].iloc[0]
    assert row.evaluation_start == pd.Timestamp("2026-02-16")
    assert row.evaluation_end == pd.Timestamp("2026-03-15")
    assert row.comparison_month == pd.Timestamp("2026-03-01")
    assert row.settlement_price_yen_mmbtu == 2530.8

def test_fuel_prices_source_columns_and_missing_jkm():
    prices = load_fuel_prices(("data/fuel_prices_2026.csv", 1))
    assert prices.month.min() == pd.Timestamp("2026-01-01")
    assert prices.japan_lng_usd_mmbtu.notna().all()
    assert prices.australia_coal_usd_ton.notna().all()
    assert prices.jkm_usd_mmbtu.isna().all()

def test_monthly_jepx_spreads_average():
    import index_app
    daily = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "tb2": [2.0, 4.0], "tb4": [3.0, 5.0], "valid": [True, True]})
    original = index_app.weekly_results
    index_app.weekly_results = lambda *args: (pd.DataFrame(), daily)
    try:
        out = monthly_jepx_spreads(pd.DataFrame({"delivery_date": pd.to_datetime(["2026-01-01"]), "area": ["Tokyo"]}), "Tokyo")
    finally:
        index_app.weekly_results = original
    assert out.iloc[0].tb2 == 3 and out.iloc[0].tb4 == 4

def test_fuel_choice_has_distinct_unit_and_no_relative_series():
    import index_app
    assert index_app.fuel_comparison_charts.__name__ == "fuel_comparison_charts"
    source = open("index_app.py", encoding="utf-8").read()
    assert "상대적 변화 추이" not in source
    assert "USD/MMBtu" in source and "fuel_comparison_charts" in source
    assert "호주 발전용 석탄가격" not in source[source.index("def fuel_comparison_charts"):source.index("def money")]
