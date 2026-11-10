import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from utils.eprx_index import calculate_eprx_week_index, PRICE_UNIT
from utils.eprx_loader import read_eprx_file, normalize_eprx_data
from streamlit.testing.v1 import AppTest


def frame(day="2026-11-02", prices=None):
    prices = [5.0] * 48 if prices is None else prices
    return pd.DataFrame({"delivery_date": pd.Timestamp(day), "period_no": range(1, len(prices) + 1),
                         "area": "Tokyo", "original_product": "一次調整力", "price_unit": PRICE_UNIT,
                         "max_price": prices, "awarded_volume": 10.0})


def result(data):
    return calculate_eprx_week_index(data, "2026-11-02", "Tokyo")


class EprxIndexTests(unittest.TestCase):
    def test_flat_prices_and_actual_top_n(self):
        _, summary = result(frame())
        self.assertEqual(summary.iloc[0].annual_index, 21_900_000)
        _, summary = result(frame(prices=list(range(48))))
        for row in summary.itertuples():
            self.assertEqual(row.annual_index, sum(range(48 - row.scenario, 48)) * 1000 * 365)
            self.assertEqual(row.used_periods, row.scenario)

    def test_insufficient_periods(self):
        daily, summary = result(frame(prices=[5] * 20))
        self.assertEqual(summary.valid_days.tolist(), [1, 0, 0, 0])
        self.assertTrue(summary.annual_index.iloc[1:].isna().all())
        self.assertFalse(daily.complete_day.any())

    def test_missing_no_award_and_actual_zero(self):
        data = frame()
        data.loc[0, "max_price"] = np.nan
        data.loc[1, "awarded_volume"] = 0
        data.loc[2, "max_price"] = 0
        daily, summary = result(data)
        self.assertEqual(daily.iloc[0].valid_periods, 46)
        self.assertEqual(summary.valid_days.tolist(), [1, 1, 1, 0])
        _, summary = result(frame(prices=[0] * 48))
        self.assertTrue(summary.annual_index.eq(0).all())
        data["max_price"] = np.nan
        self.assertTrue(result(data)[1].annual_index.isna().all())

    def test_week_mean_boundaries_region(self):
        other = frame()
        other["area"] = "Chubu"
        data = pd.concat([frame(), frame("2026-11-08", [10] * 48), frame("2026-11-09"), other], ignore_index=True)
        _, summary = result(data)
        self.assertTrue(summary.valid_days.eq(2).all())
        self.assertEqual(summary.iloc[0].annual_index, 7.5 * 12 * 1000 * 365)
        self.assertEqual(summary.iloc[0].average_price, 7.5)

    def test_reject_ambiguous_units_products_duplicates_and_legacy(self):
        for col, value in (("price_unit", "円/kWh"), ("original_product", "other"), ("period_no", 0)):
            data = frame()
            data.loc[0, col] = value
            self.assertTrue(result(data)[1].annual_index.isna().all())
        self.assertTrue(result(pd.concat([frame(), frame().iloc[:1]]))[1].annual_index.isna().all())
        _, summary = calculate_eprx_week_index(frame("2026-03-09"), "2026-03-09", "Tokyo")
        self.assertTrue(summary.annual_index.isna().all())

    def test_scenario_specific_valid_days(self):
        data = pd.concat([frame(), frame("2026-11-03", [10] * 12)], ignore_index=True)
        _, summary = result(data)
        self.assertEqual(summary.valid_days.tolist(), [2, 1, 1, 1])
        self.assertEqual(summary.iloc[0].annual_index, 32_850_000)
        self.assertEqual(summary.iloc[1].annual_index, 43_800_000)

    def test_actual_source_and_screen(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "data/eprx/raw/202611_1-0_prompt.csv"
        data = normalize_eprx_data(read_eprx_file(path), path)
        self.assertEqual(set(data.price_unit), {PRICE_UNIT})
        app = AppTest.from_file(str(root / "index_app.py")).run(timeout=180)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 6)
        week, area = app.selectbox[0].value, app.selectbox[1].value
        _, summary = calculate_eprx_week_index(data, week, area)
        self.assertGreater(summary.iloc[0].valid_days, 0)
        self.assertEqual(app.metric[2].value, f'{summary.iloc[0].annual_index / 10000:,.1f}만 엔')
        self.assertTrue(any("실제 ESS 낙찰수익을 의미하지 않습니다" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
