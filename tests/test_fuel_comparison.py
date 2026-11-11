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
    jepx = pd.DataFrame({"month": fuel.month, "tb2": 2.0, "tb4": 3.0})
    index_app.fuel_comparison_charts(jepx, fuel, jkm)
    assert texts[0] == "#### JEPX 스프레드와 발전연료 가격 비교"
    assert texts[1] == "JEPX의 월평균 스프레드와 LNG·석탄 가격의 추이를 비교합니다."
    labels = ["JKM 연동가격(JPX)", "일본 LNG 수입가격", "호주 발전용 석탄가격"]
    units = ["엔/MMBtu", "USD/MMBtu", "USD/톤"]
    assert len(figures) == 3
    for fig, label, unit in zip(figures, labels, units):
        assert f"##### JEPX 스프레드와 {label}" in texts
        assert [trace.name for trace in fig.data] == ["JEPX TB2 (엔/kWh)", "JEPX TB4 (엔/kWh)", f"{label} ({unit})"]
        assert fig.layout.xaxis.title.text == "월"
        assert fig.layout.yaxis.title.text == "JEPX 스프레드 (엔/kWh)"
        assert fig.layout.yaxis2.title.text == unit
        assert fig.data[2].yaxis == "y2"
        # Includes trace names, axis/legend titles and any hover text/templates.
        payload = fig.to_json()
        assert "?" not in payload and "\ufffd" not in payload
    sources = [text for text in texts if text.startswith("출처:")]
    assert len(sources) == 3
    assert all("[JEPX 스폿시장 가격](https://www.jepx.jp/electricpower/market-data/spot/)" in text for text in sources)
    assert "[JPX LNG (Platts JKM) 선물 최종정산가격](https://www.jpx.co.jp/markets/derivatives/special-quotation/)" in sources[0]
    for text, label in zip(sources[1:], labels[1:]):
        assert f"[World Bank Pink Sheet ({label})](https://www.worldbank.org/en/research/commodity-markets)" in text
    assert "평가기간 종료월을 기준으로 표시합니다." in sources[0]
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
