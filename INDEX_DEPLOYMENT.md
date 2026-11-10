# Index app deployment

- Repository: `jeongyeonns/Japan_BESS_Index`
- Branch: `main`
- Main file path: `index_app.py` (repository root)
- In Community Cloud **Advanced settings**, select Python **3.13**, the tested version.
  The existing `runtime.txt` is not a substitute for this UI setting.
- Dependencies: root `requirements.txt`. No secrets are required for this app.
- Local run: `python -m streamlit run index_app.py`

## Data and updates (verified 2026-11-10 KST)

The app reads committed public CSVs with existing loaders, relative to its own file.
JEPX data is available through **2026-11-10**, EPRX through **2026-11-09**.
All CSVs discovered by the app are tracked in Git, including legacy EPRX root files
that are now ignored for new additions. The raw-file exceptions preserve future
JEPX annual and EPRX primary-reserve CSV updates.

Both update workflows exist, but the new repository's GitHub Actions permission
API reports `enabled: false`; there are no workflow runs. Thus **automatic updates
are currently inactive**. Deploying the Streamlit app does not activate them.
Until Actions are enabled or new data is committed manually, the above dates are
the end of available data. Existing schedules are JEPX 19:15 and EPRX 06:00 JST/KST.
Successful scheduled downloads and pushes still need verification after enabling
Actions. No automation settings were changed in this deployment preparation.

## Interpretation and verification

- JEPX: hourly-average TB2/TB4 weekly spreads × 1,000 × 2/4 × 365.
- EPRX: daily top 12/24/36/48 valid maximum auction prices summed × 1,000,
  then averaged across valid days × 365. No extra 0.5 multiplier.
- Zero awarded volume is excluded, not interpreted as zero revenue. A genuine
  zero price with positive awarded volume is valid. Missing scenarios remain NaN.
- Legacy EPRX three-hour blocks are excluded. Calendar weeks run Monday–Sunday.
- These are annualized theoretical price opportunities, not actual ESS profits;
  the two markets must not be summed as realized total revenue.

Run the focused checks with pytest installed as a development dependency:

```sh
python -m pytest tests/test_jepx_index.py tests/test_eprx_index.py tests/test_index_dashboard.py tests/test_deployment_readiness.py -q
```

Linux path/import casing and Linux wheel resolution are checked during preparation.
Actual Linux/Community Cloud execution must be checked after deployment; no Linux
runtime is installed in the preparation environment. Existing pandas deprecation
warnings do not fail the current tests.
