"""Hourly TB opportunity index using the existing normalized JEPX schema."""

import numpy as np
import pandas as pd

from utils.jepx_spread import validate_daily_price_profile


def calculate_week_index(data: pd.DataFrame, week_start, area: str):
    """Return seven daily rows and averages over complete days only (JST)."""
    start = pd.Timestamp(week_start).normalize()
    if start.weekday() != 0:
        raise ValueError("주차 시작일은 월요일이어야 합니다.")
    dates = pd.to_datetime(data["delivery_date"], errors="coerce").dt.normalize()
    selected = data.loc[data["area"].eq(area) & dates.between(start, start + pd.Timedelta(days=6))].copy()
    selected["delivery_date"] = pd.to_datetime(selected["delivery_date"], errors="coerce").dt.normalize()
    rows = []
    for day in pd.date_range(start, periods=7):
        group = selected.loc[selected["delivery_date"].eq(day)]
        row = {"delivery_date": day, "tb2": np.nan, "tb4": np.nan, "valid": False, "reason": "데이터 없음"}
        if not group.empty:
            # Guard fractional/missing periods before the existing integer validator.
            periods = pd.to_numeric(group["period_no"], errors="coerce")
            if periods.isna().any() or not periods.isin(range(1, 49)).all():
                row["reason"] = "시간대 번호 오류"
            else:
                profile, validation = validate_daily_price_profile(group)
                if not validation["is_valid"]:
                    row["reason"] = validation["warning_message"]
                elif not np.isfinite(profile["price"].to_numpy(dtype=float)).all():
                    row["reason"] = "유한하지 않은 가격"
                else:
                    hourly = profile.groupby((profile["period_no"] - 1) // 2)["price"].mean()
                    for hours in (2, 4):
                        row[f"tb{hours}"] = float(hourly.nlargest(hours).mean() - hourly.nsmallest(hours).mean())
                    row.update(valid=True, reason="정상")
        rows.append(row)
    daily = pd.DataFrame(rows)
    summary = {"valid_days": int(daily["valid"].sum())}
    for hours in (2, 4):
        spread = daily.loc[daily["valid"], f"tb{hours}"].mean()
        summary[f"tb{hours}_spread"] = spread
        summary[f"tb{hours}_index"] = spread * 1000 * hours * 365
    return daily, summary
