"""Spread emphasis changes presentation only, including zero/missing values."""

import ast
from html import escape
from pathlib import Path
import subprocess
from types import SimpleNamespace

from bs4 import BeautifulSoup
import pandas as pd
import pytest

from views import jepx_view

# Preserve the same comparison after the feature is committed and merged.
BASELINE_COMMIT = "c31c5066ad70a81303afd20073ece3c2872e6cbb"


@pytest.mark.parametrize("spread", ["12.34", "0.00", "-1.23", "계산 불가"])
def test_spread_row_emphasis_preserves_every_value(monkeypatch, spread):
    source = subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:views/jepx_view.py"]).decode("utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_render_metric_hierarchy_table")
    captured = []
    target = SimpleNamespace(markdown=lambda value, **kwargs: captured.append(value))
    namespace = {"pd": pd, "escape": escape, "st": target}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "baseline", "exec"), namespace)
    table = pd.DataFrame({"도쿄": ["18.20", spread, "+0.12"]}, index=[
        "일 평균 전력가격 (엔/kWh)", "평균 ESS 스프레드 (엔/kWh)", "전일 대비 평균 스프레드 변화 (엔/kWh)"])
    original = table.copy(deep=True)
    namespace["_render_metric_hierarchy_table"](table)
    monkeypatch.setattr(jepx_view, "st", target)
    jepx_view._render_metric_hierarchy_table(table)
    before, after = [BeautifulSoup(html, "html.parser") for html in captured]
    assert [row.get_text() for row in before.select("tr")] == [row.get_text() for row in after.select("tr")]
    emphasized = after.select("tr.jepx-primary-spread")
    assert len(emphasized) == 1
    value_cell = emphasized[0].select_one(".jepx-metric-value")
    assert value_cell.get_text() == spread
    assert value_cell.select_one("strong.jepx-spread-number").get_text() == spread
    assert not after.select("tr:not(.jepx-primary-spread) strong.jepx-spread-number")
    for before_row, after_row in zip(before.select("tbody tr"), after.select("tbody tr")):
        if "jepx-primary-spread" not in after_row.get("class", []):
            assert str(before_row) == str(after_row)
    assert "font-weight: 700" in after.style.get_text()
    assert ".jepx-primary-spread > .jepx-metric-value { font-weight: 800; font-size: 1.2em; }" in after.style.get_text()
    assert "tr.jepx-primary-spread > td" in after.style.get_text()
    assert "rgba(214, 39, 40, 0.10)" in after.style.get_text()
    pd.testing.assert_frame_equal(table, original)


def test_national_weekly_only_adds_spread_styling():
    old = ast.parse(subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:views/jepx_view.py"]).decode("utf-8"))
    new = ast.parse(Path("views/jepx_view.py").read_text(encoding="utf-8"))
    old_fn = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == "render_jepx_weekly_monitor")
    new_fn = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == old_fn.name)
    additions = [n for n in new_fn.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                 and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "set_properties"]
    assert len(additions) == 1
    assert "평균 ESS 스프레드 (엔/kWh)" in ast.unparse(additions[0])
    new_fn.body = [n for n in new_fn.body if n not in additions]
    assert ast.dump(new_fn) == ast.dump(old_fn)
