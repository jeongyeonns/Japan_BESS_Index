# JEPX 2026 January–March backfill

- Official source: https://www.jepx.jp/electricpower/market-data/spot/
- Download: POST `https://www.jepx.jp/_download.php`, form
  `dir=spot_summary&file=spot_summary_2025.csv`.
- Retrieved 2026-11-10 using the existing `utils.jepx_downloader --year 2025`.
- Official fiscal-year file: 2025-04-01 through 2026-03-31, 17,520 rows.
- Original SHA-256: `cf95e1aea783ecac2d876244d99c6610506db2bb4ed1c24c5dc887e7c16731d0`.
- Added file: `raw/spot_summary_2025_20260101_20260331.csv`.
- Extracted by delivery date (`受渡日`): 2026-01-01 through 2026-03-31,
  4,320 rows / 90 days / 48 periods daily. All nine areas plus System retained.
- Original columns, prices in yen/kWh, and cp932 encoding retained; no imputation.
- Extract SHA-256: `ec7e260d463f50825370198da16cda85559080bf2b993e1f7aad86f79cb45f35`.

The existing `raw/spot_summary_2026.csv` is unchanged. The loader combines the
two disjoint delivery-date ranges. Keeping the backfill separate preserves it
when the existing current-fiscal-year downloader refreshes the 2026 file.

Local backup and unmodified downloaded source are in the Git-ignored directory
`.test-tmp-jepx-backfill/` (not required at runtime).
