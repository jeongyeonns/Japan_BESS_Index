# Daily JKM connection (2026-11-12)

No verified daily JKM series has been imported. Monthly JPX data remains separate.

- https://www.oilpriceapi.com/jkm-lng-price-api advertises spot and futures feeds,
  but historical access requires an API token/plan. No authorized token was
  provided. This is a normalized feed, not an official Platts assessment file.
- https://kr.investing.com/commodities/lng-japan-korea-marker-platts-futures-historical-data
  exposes a recent futures window; the requested Jan-Apr history, historical
  contract mapping and reuse permission were not verified. Do not infer the
  contract month for historical rows from the current page title.
- EnergyRiskIQ, interpolated monthly values and carried-forward prices are not used.

To connect verified, licensed observations, add UTF-8 `data/jkm_daily.csv`:

`date,price,unit,source,price_type,contract_month`

Dates must be actual observation dates (`YYYY-MM-DD`), unit `USD/MMBtu`, source
a nonempty provenance URL/identifier, price_type `spot` or `futures`. Futures
require their actual `YYYY-MM` contract month; spot requires an empty contract.
Do not include repeated weekend/holiday snapshots. Duplicates per date/source/
type/contract, nonfinite prices and invalid metadata are rejected, with JEPX
still available. An API adapter can write this same CSV outside Streamlit.
The app reads only the saved file, cached by modification time. No scheduler or
API credentials were added. Cloud may require Reboot after adding a file.

Weekly averages use only observed days inside the selected dates, Monday-Sunday.
Source, spot/futures and contract-month series are never averaged together.
Contract changes are displayed as separate traces, not a continuous price jump.
