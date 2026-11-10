"""Check entrypoint imports in fresh and pre-update Python processes."""

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("cached_before_update", [False, True])
def test_entrypoint_imports(cached_before_update):
    setup = ""
    if cached_before_update:
        setup = """
import utils.eprx_index as cached
del cached.calculate_eprx_legacy_week_index
cached.calculate_eprx_week_index = None
"""
    script = setup + """
from pathlib import Path
import index_app
import utils.eprx_index as engine
assert Path(engine.__file__).resolve() == Path('utils/eprx_index.py').resolve()
assert callable(index_app.calculate_eprx_week_index)
assert callable(index_app.calculate_eprx_legacy_week_index)
assert index_app.calculate_eprx_week_index is engine.calculate_eprx_week_index
assert index_app.calculate_eprx_legacy_week_index is engine.calculate_eprx_legacy_week_index
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert result.returncode == 0, result.stderr
