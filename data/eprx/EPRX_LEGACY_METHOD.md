# EPRX 2026 Q1 coverage and historical Index

Reviewed 2026-11-10. Existing CSVs are reused without changing prices or files.

| Existing file under data/eprx | Dates | Days | Blocks/day | Area/day groups |
|---|---|---:|---:|---:|
| 202601_1-0_prompt.csv | Jan 1–31 | 31 | 8 | 279 |
| 202602_1-0_prompt.csv | Feb 1–28 | 28 | 8 | 252 |
| 202603_1-0_0301-0313_prompt.csv | Mar 1–13 | 13 | 8 | 117 |
| 202603_1-0_0314-0331_prompt.csv | Mar 14–31 | 18 | 48 | 162 |

All nine areas are present. All 90 days have the expected unique period count.
The original metric is `最高落札価格（電源属地別）[円/kW・30分]`.
There are no missing maximum prices in these files. Zero awarded-volume entries
number 7 for the legacy period and 169 for the modern period; they are excluded
even when the source price is zero. Positive awarded volume with a true zero price
remains valid. The metadata identifies `一次調整力`, `速報値`; it does not provide
a separate online/offline classification.

## Official basis

- [EPRX trading rules effective 2025-04-01](https://www.eprx.or.jp/j_information/docs/kitei211f_20250401.pdf):
  Article 29, page 48, defines eight three-hour product blocks, including primary
  reserve. Article 46(1), page 93, computes contracted charges per 30-minute period
  as contracted unit price times contracted kW, summed over the settlement period.
- [OCCTO/EPRX system transition report, 2025-11-13](https://www.occto.or.jp/assets/iinkai/jukyuchousei/58/jukyu_shijyo_58_05.pdf):
  page 11 (PDF page 12) states the new 30-minute/day-ahead regime applies from
  2026-03-14 delivery. March 13 remains a three-hour-contract day, even if a
  later publication splits its results into 30-minute rows.

Combining the source unit with these rules, a whole three-hour block represents
six 30-minute settlement periods. The legacy price-opportunity calculation selects
the top 2/4/6/8 valid blocks for 6/12/18/24 hours, sums their source prices, then
multiplies by 6 × 1,000. The mean daily amount within the same regime is multiplied
by 365. Blocks are not expanded into synthetic, independently selectable prices.

The default modern function retains its existing top-12/24/36/48-period formula.
The legacy mode accepts only pre-reform dates and block numbers 1–8. Unknown units,
mixed products, duplicate periods, invalid prices and zero awarded volume cannot
be silently converted to zero revenue. A scenario needs at least its selected
number of valid blocks/periods; partial days remain flagged.

## Comparison and limits

The week Mar 9–15 has separate legacy Mar 9–13 (5-day denominator) and modern
Mar 14–15 (2-day denominator) summaries. No mixed-regime weekly average is used.
Charts separate the paths by regime and mark March 14. Details retain the actual
date span, valid day count, selected block/period count and source-unit mean price.

These are theoretical opportunities at published maximum prices, not actual
settlement proceeds. Article 46 also describes price-cap adjustments; caps,
subsequent settlements, penalties and fees are not newly applied to this index.
Market design changes prevent treating the two regimes as identical conditions.
