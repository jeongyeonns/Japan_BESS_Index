# Korean UI text editing

The Windows PowerShell session used ASCII `$OutputEncoding`. Piping Korean
source code through `@' ... '@ | python` replaced Korean characters with `?`
before Python received them. Writing that damaged text with `encoding='utf-8'`
cannot restore it. This was reproduced with `'한글' | python`; Python received
`??`. Console output encoding was UTF-8, which does not control pipe encoding.

The first JKM commit `1972698` already contained damaged headings. Commit
`0278732` reintroduced damage in headings and source captions; `db93d82` only
changed a test. Earlier tests checked trace counts, not the rendered captions,
and even used the same incorrect UTF-8 bytes for the expected currency label.

Use a direct UTF-8 editor or `apply_patch` for Korean changes. Do not pipe
non-ASCII Python source through Windows PowerShell's default ASCII encoding.
If scripting is required, use an ASCII-only script with literal `\uXXXX`
escapes and explicit UTF-8 file reads/writes. Alternatively explicitly set
PowerShell `$OutputEncoding` to UTF-8 and configure the Python pipe reader
for UTF-8; test a round trip before editing files.

Run `.venv/Scripts/python.exe -m pytest tests/test_fuel_comparison.py -q`
before committing. The rendered-label test checks exact Korean headings,
captions, source links and Plotly names/axes, and rejects `?` and U+FFFD.
Tests must pass before a separate commit/push command is executed.
