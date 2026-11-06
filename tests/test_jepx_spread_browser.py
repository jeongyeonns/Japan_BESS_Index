"""Opt-in real-browser validation against an already running local app.

Set JEPX_BROWSER_URL; Playwright and local Chrome are only needed for this test.
JEPX_BASELINE_DIR optionally points to pre-change row snapshots for value checks.
"""

import json
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.environ.get("JEPX_BROWSER_URL"), reason="Local browser smoke is opt-in")
def test_weekly_daily_computed_spread_styles():
    playwright = pytest.importorskip("playwright.sync_api")
    output = Path("tmp/spread-visual")
    output.mkdir(parents=True, exist_ok=True)
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1100},
                                    extra_http_headers={"Accept-Encoding": "identity"})
            page.set_default_timeout(180000)
            page.goto(os.environ["JEPX_BROWSER_URL"])
            page.get_by_text("JEPX 현물시장", exact=True).click()
            page.locator(".jepx-metric-table").wait_for()
            for mode in ["weekly", "daily"]:
                if mode == "daily":
                    page.get_by_text("Daily 분석", exact=True).click()
                    page.get_by_text("JEPX Daily 분석", exact=True).wait_for()
                table = page.locator(".jepx-metric-table")
                table.locator("strong.jepx-spread-number").wait_for()
                rows = table.evaluate("""el => [...el.querySelectorAll('tbody tr')].map(row => ({
                    text: row.innerText, cls: row.className,
                    cells: [...row.cells].map(cell => {
                        let s = getComputedStyle(cell);
                        return {weight:s.fontWeight, size:parseFloat(s.fontSize),
                            background:s.backgroundColor, border:s.borderLeftWidth};
                    })
                }))""")
                spread = next(row for row in rows if row["cls"] == "jepx-primary-spread")
                ordinary = [row for row in rows if not row["cls"]]
                assert spread["cells"][1]["weight"] == "800"
                assert spread["cells"][1]["size"] == pytest.approx(ordinary[0]["cells"][1]["size"] * 1.2)
                assert all(cell["background"] == "rgba(214, 39, 40, 0.1)" for cell in spread["cells"])
                assert spread["cells"][0]["border"] == "4px"
                assert table.locator(".jepx-primary-spread .jepx-metric-main").evaluate("el => getComputedStyle(el).fontWeight") == "700"
                assert table.locator("strong.jepx-spread-number").evaluate("el => getComputedStyle(el).fontWeight") == "800"
                assert all(row["cells"][1]["weight"] == "400" for row in ordinary)
                baseline_dir = os.environ.get("JEPX_BASELINE_DIR")
                if baseline_dir:
                    baseline = json.loads((Path(baseline_dir) / f"{mode}-before.json").read_text(encoding="utf-8"))
                    assert [row["text"] for row in rows] == [row["text"] for row in baseline]
                    for old, new in zip(baseline, rows):
                        if not new["cls"]:
                            assert new["cells"][1]["size"] == float(old["cells"][1]["size"].removesuffix("px"))
                            assert new["cells"][1]["background"] == old["cells"][1]["background"]
                table.screenshot(path=str(output / f"{mode}-after.png"))
                (output / f"{mode}-after.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            browser.close()
