"""Local production-data smoke paths. No download/update controls are invoked."""

import json
from pathlib import Path
import subprocess
import ast

from streamlit.testing.v1 import AppTest

# Fixed pre-Daily production baseline; HEAD changes after feature/merge commits.
BASELINE_COMMIT = "c31c5066ad70a81303afd20073ece3c2872e6cbb"


def test_weekly_renderers_unchanged():
    original = subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:app.py"]).decode("utf-8")
    current = Path("app.py").read_text(encoding="utf-8")
    def functions(source):
        return {node.name: ast.dump(node) for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
    old, new = functions(original), functions(current)
    for name in old:
        if name != "render_jepx_market_placeholder":
            assert new[name] == old[name], name
    jepx_old = functions(subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:views/jepx_view.py"]).decode("utf-8"))
    jepx_new = functions(Path("views/jepx_view.py").read_text(encoding="utf-8"))
    for name in jepx_old:
        # These two functions have authorized spread-only visual emphasis.
        if name not in {"_render_metric_hierarchy_table", "render_jepx_weekly_monitor"}:
            assert jepx_new[name] == jepx_old[name], name


def test_production_market_daily_weekly_paths():
    app = AppTest.from_file("app.py", default_timeout=180).run()
    assert not app.exception
    assert app.radio(key="eprx_analysis_mode").value == "주간 분석"
    assert app.selectbox(key="eprx_analysis_week").value is not None
    app.radio(key="eprx_analysis_mode").set_value("Daily 분석").run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 2
    selector = app.selectbox(key="eprx_daily_date")
    assert selector.index == 0
    if len(selector.options) > 1:
        selector.select_index(1).run()
    app.radio(key="eprx_daily_area").set_value("도쿄").run()
    assert not app.exception
    app.radio(key="eprx_daily_unit").set_value("광역권·합산").run()
    for group, count in [("전국 합산", 9), ("도쿄+도호쿠", 2), ("중부+호쿠리쿠+간사이", 3)]:
        app.radio(key="eprx_daily_group").set_value(group).run()
        assert not app.exception
        for chart in app.get("plotly_chart"):
            assert len(json.loads(chart.proto.spec)["data"]) == count
    app.radio(key="eprx_analysis_mode").set_value("주간 분석").run()
    assert not app.exception
    app.segmented_control(key="market_selector").set_value("JEPX 현물시장").run()
    assert not app.exception
    assert app.selectbox(key="jepx_detail_week").value is not None
    assert any('class="jepx-primary-spread"' in item.value for item in app.markdown)
    app.radio(key="jepx_analysis_mode").set_value("Daily 분석").run()
    assert not app.exception
    assert len(app.selectbox(key="jepx_daily_area").options) == 9
    assert len(app.get("plotly_chart")) == 1
    assert any('class="jepx-primary-spread"' in item.value for item in app.markdown)
    app.selectbox(key="jepx_daily_date").select_index(1).run()
    app.selectbox(key="jepx_daily_area").set_value("중부").run()
    assert not app.exception
    app.radio(key="jepx_analysis_mode").set_value("주간 분석").run()
    assert not app.exception
