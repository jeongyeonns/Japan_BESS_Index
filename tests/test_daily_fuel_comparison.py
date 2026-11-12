import pandas as pd
import pytest
from utils.daily_fuel_comparison import load_daily_jkm, comparison_rows, comparison_figure
from utils.jepx_index import calculate_week_index
from test_jepx_index import day_frame


def test_complete_jepx_days_weekly_counts_and_gaps(tmp_path):
    raw = pd.concat([day_frame("2026-02-23"), day_frame("2026-02-24").iloc[:-1], day_frame("2026-02-25")])
    daily, _ = calculate_week_index(raw, "2026-02-23", "Tokyo")
    jkm = load_daily_jkm(tmp_path / "absent.csv")
    rows = comparison_rows(daily, jkm, "2026-02-23", "2026-03-01", True)
    assert rows.observed_days.tolist() == [2, 2]
    assert rows.value.tolist() == [22, 20]
    fig = comparison_figure(comparison_rows(daily, jkm, "2026-02-23", "2026-03-01"), "2026-02-23", "2026-03-01")
    assert len(fig.data) == 2
    assert pd.isna(fig.data[0].y[1])
    assert fig.data[0].connectgaps is False
    assert fig.layout.shapes[0].x0 == "2026-02-28"


def test_jkm_metadata_contract_separation_and_date_filter(tmp_path):
    path = tmp_path / "jkm.csv"
    path.write_text("date,price,unit,source,price_type,contract_month\n2026-02-23,10,USD/MMBtu,licensed,futures,2026-04\n2026-02-25,14,USD/MMBtu,licensed,futures,2026-04\n2026-02-26,30,USD/MMBtu,licensed,futures,2026-05\n", encoding="utf-8")
    jkm = load_daily_jkm(path)
    daily, _ = calculate_week_index(day_frame("2026-02-23"), "2026-02-23", "Tokyo")
    rows = comparison_rows(daily, jkm, "2026-02-23", "2026-03-01", True)
    fuel = rows.loc[rows.unit.eq("USD/MMBtu")]
    assert fuel.value.tolist() == [12, 30]
    assert fuel.observed_days.tolist() == [2, 1]
    assert fuel.period.eq(pd.Timestamp("2026-02-23")).all()
    fig = comparison_figure(rows, "2026-02-23", "2026-03-01", True)
    traces = [t for t in fig.data if t.yaxis == "y2"]
    assert len(traces) == 2 and list(traces[0].y) == [12]
    assert "JKM 선물가격" in traces[0].name
    subset = comparison_rows(daily, jkm, "2026-02-25", "2026-02-25")
    assert subset.value.tolist() == [14]
    path.write_text(path.read_text().replace("USD/MMBtu", "JPY/MMBtu"), encoding="utf-8")
    with pytest.raises(ValueError):
        load_daily_jkm(path)


def test_daily_panel_defaults_and_korean(monkeypatch):
    import index_app
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
from index_app import daily_fuel_panel
from utils.jepx_index import calculate_week_index
import pandas as pd
raw = pd.DataFrame({"delivery_date":pd.Timestamp("2026-02-23"),"area":"Tokyo","period_no":range(1,49),"price":range(48)})
daily, _ = calculate_week_index(raw,"2026-02-23","Tokyo")
daily_fuel_panel(daily)
''').run(timeout=30)
    assert not app.exception
    assert app.selectbox[0].value == "일별"
    assert len(app.get("plotly_chart")) == 1
    assert any("일별 JKM 데이터 미확보" in v.value for v in app.info)
    assert all("???" not in v.value and "\ufffd" not in v.value for v in list(app.markdown) + list(app.caption))
    app.selectbox[0].select("주별").run(timeout=30)
    assert not app.exception
