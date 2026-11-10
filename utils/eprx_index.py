"""Primary reserve opportunity using source-area maximum auction prices."""

import numpy as np
import pandas as pd

from utils.eprx_periods import expected_period_count

SCENARIOS = (12, 24, 36, 48)
PRICE_UNIT = "円/kW・30分"


def calculate_eprx_week_index(data, week_start, area, *, _legacy=False):
    """Use available awarded periods, never fill missing/no-award prices."""
    start = pd.Timestamp(week_start).normalize()
    if start.weekday() != 0:
        raise ValueError("주차 시작일은 월요일이어야 합니다.")
    dates = pd.to_datetime(data["delivery_date"], errors="coerce").dt.normalize()
    selected = data.loc[data["area"].eq(area) & dates.between(start, start + pd.Timedelta(days=6))].copy()
    selected["delivery_date"] = pd.to_datetime(selected["delivery_date"]).dt.normalize()
    rows = []
    expected = 8 if _legacy else 48
    half_hours_per_period = 6 if _legacy else 1
    for day in pd.date_range(start, periods=7):
        group = selected.loc[selected["delivery_date"].eq(day)]
        periods = pd.to_numeric(group["period_no"], errors="coerce")
        prices = pd.to_numeric(group["max_price"], errors="coerce")
        volume = pd.to_numeric(group["awarded_volume"], errors="coerce")
        issue = ""
        if expected_period_count(day) != expected:
            issue = "해당 거래제도 밖의 날짜" if _legacy else "3시간 블록 자료: 30분 변환 안 함"
        elif not group.empty:
            if not group["original_product"].eq("一次調整力").all():
                issue = "1차 조정력 이외 상품 포함"
            elif not group["price_unit"].eq(PRICE_UNIT).all():
                issue = "가격 단위 불일치"
            elif not periods.isin(range(1, expected + 1)).all() or periods.duplicated().any():
                issue = "시간대 오류 또는 중복"
        valid = prices.notna() & np.isfinite(prices) & prices.ge(0) & volume.gt(0) & np.isfinite(volume)
        available = prices.loc[valid].sort_values(ascending=False) if not issue else pd.Series(dtype=float)
        for n in SCENARIOS:
            count = n // half_hours_per_period
            can_calculate = not issue and len(available) >= count
            chosen = available.head(count) if can_calculate else pd.Series(dtype=float)
            rows.append({
                "date": day, "scenario": n, "observed_periods": periods.nunique(),
                "valid_periods": len(available), "missing_prices": int(prices.isna().sum()),
                "no_award_periods": int(volume.eq(0).sum()),
                "selected_periods": count if can_calculate else 0,
                "average_price": chosen.mean(),
                "daily_opportunity": chosen.sum() * 1000 * half_hours_per_period if can_calculate else np.nan,
                "complete_day": not issue and len(available) == expected,
                "reason": issue or ("정상" if len(available) == expected else
                           "일부 유효 코마만 사용" if can_calculate else "유효 코마 부족"),
            })
    daily = pd.DataFrame(rows)
    summaries = []
    for n in SCENARIOS:
        scenario = daily.loc[daily["scenario"].eq(n)]
        valid_days = scenario.loc[scenario["daily_opportunity"].notna()]
        summaries.append({"scenario": n, "valid_days": len(valid_days),
                          "complete_days": int(valid_days["complete_day"].sum()),
                          "used_periods": int(valid_days["selected_periods"].sum()),
                          "average_price": valid_days["average_price"].mean(),
                          "annual_index": valid_days["daily_opportunity"].mean() * 365})
    return daily, pd.DataFrame(summaries)


def calculate_eprx_legacy_week_index(data, week_start, area):
    """3h blocks only: select 2/4/6/8 blocks, sum yen/kW/30min × 6 × 1000.

    Basis: EPRX 2025-04-01 trading rules, Articles 29 and 46(1).
    Never expand blocks into artificial independently selectable 30min prices.
    """
    return calculate_eprx_week_index(data, week_start, area, _legacy=True)
