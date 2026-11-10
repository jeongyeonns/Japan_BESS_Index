import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from utils.jepx_index import calculate_week_index
from utils.jepx_loader import load_all_jepx_data


def day_frame(day="2026-11-02", prices=None, area="Tokyo"):
    return pd.DataFrame({"delivery_date": pd.Timestamp(day), "area": area,
                         "period_no": range(1, 49),
                         "price": np.repeat(np.arange(24), 2) if prices is None else prices})


class IndexTests(unittest.TestCase):
    def test_hourly_ranking_and_annualization(self):
        # Each hour averages 5 despite highly different half-hour extremes.
        daily, summary = calculate_week_index(day_frame(prices=[0, 10] * 24), "2026-11-02", "Tokyo")
        self.assertEqual(daily.iloc[0].tb2, 0)
        self.assertEqual(summary["tb4_index"], 0)
        _, summary = calculate_week_index(day_frame(prices=np.repeat([0] * 12 + [10] * 12, 2)), "2026-11-02", "Tokyo")
        self.assertEqual(summary["tb2_index"], 7_300_000)
        self.assertEqual(summary["tb4_index"], 14_600_000)

    def test_week_mean_and_boundaries_and_region(self):
        data = pd.concat([day_frame(), day_frame("2026-11-08", np.zeros(48)),
                          day_frame("2026-11-09"), day_frame(area="Chubu")], ignore_index=True)
        daily, summary = calculate_week_index(data, "2026-11-02", "Tokyo")
        self.assertEqual(len(daily), 7)
        self.assertEqual(summary["valid_days"], 2)
        self.assertEqual(summary["tb2_spread"], 11)
        self.assertEqual(summary["tb4_spread"], 10)

    def test_invalid_days_not_filled(self):
        missing = day_frame().iloc[:-1]
        duplicate = pd.concat([day_frame(), day_frame().iloc[:1]])
        for frame in (missing, duplicate):
            self.assertEqual(calculate_week_index(frame, "2026-11-02", "Tokyo")[1]["valid_days"], 0)
        for column, value in (("price", np.nan), ("price", np.inf), ("period_no", 1.5), ("period_no", np.nan)):
            frame = day_frame().astype({column: float})
            frame.loc[0, column] = value
            with self.subTest(column=column, value=value):
                _, summary = calculate_week_index(frame, "2026-11-02", "Tokyo")
                self.assertEqual(summary["valid_days"], 0)
                self.assertTrue(pd.isna(summary["tb2_index"]))

    def test_negative_prices_and_monday_validation(self):
        frame = day_frame()
        frame["price"] -= 50
        self.assertEqual(calculate_week_index(frame, "2026-11-02", "Tokyo")[1]["tb2_spread"], 22)
        with self.assertRaises(ValueError):
            calculate_week_index(frame, "2026-11-03", "Tokyo")

    def test_actual_data_and_streamlit(self):
        root = Path(__file__).resolve().parents[1]
        data, _, _, _, _ = load_all_jepx_data(root / "data/jepx/raw")
        self.assertFalse(data.empty, "Actual local JEPX data required")
        app = AppTest.from_file(str(root / "index_app.py")).run(timeout=180)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([m.label for m in app.metric[:2]], ["2시간형 차익거래 Index (TB2)", "4시간형 차익거래 Index (TB4)"])
        week, area = app.selectbox[0].value, app.selectbox[1].value
        _, expected = calculate_week_index(data, week, area)
        self.assertGreater(expected["valid_days"], 0)
        self.assertEqual(app.metric[0].value, f'{expected["tb2_index"] / 10000:,.1f}만 엔')
        first = data["delivery_date"].min()
        first -= pd.Timedelta(days=first.weekday())
        app.selectbox[0].select(first).run(timeout=60)
        app.selectbox[1].select("Kyushu").run(timeout=60)
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
