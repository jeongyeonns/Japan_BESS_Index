"""Daily-only selections and validation; never fill missing observations."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from utils.eprx_area_groups import AGGREGATE_REGION_GROUPS, aggregate_region_data
from utils.eprx_periods import expected_period_count, period_start_label
from utils.eprx_areas import EPRX_AREA_COLORS
from utils.regional_charts import _finish, _add_autoscale_hint
from utils.regional_analysis import calculate_area_kpis
from utils.jepx_weekly_analysis import create_area_price_spread_comparison


def available_dates(data, today=None):
    today = pd.Timestamp(today or pd.Timestamp.now(tz="Asia/Tokyo").date()).normalize()
    dates = pd.to_datetime(data["delivery_date"]).dt.normalize()
    return sorted(dates.loc[dates.le(today)].dropna().unique(), reverse=True)


def select_day(data, day):
    return data.loc[pd.to_datetime(data["delivery_date"]).dt.normalize().eq(pd.Timestamp(day))].copy()


def day_quality(data, day, areas, market):
    """Require every constituent, unique valid slots, and finite source values."""
    raw = select_day(data, day)
    expected = expected_period_count(day) if market == "eprx" else 48
    columns = (["procurement_volume", "bid_volume", "awarded_volume", "max_price", "min_price", "avg_price"]
               if market == "eprx" else ["price"])
    rows = []
    for area in areas:
        part = raw.loc[raw.area.eq(area)]
        valid = part.period_no.isin(range(1, expected + 1))
        valid &= np.isfinite(part[columns].apply(pd.to_numeric, errors="coerce")).all(axis=1)
        duplicates = part.period_no.duplicated(keep=False)
        count = part.loc[valid & ~duplicates, "period_no"].nunique()
        observed = part.loc[part.period_no.isin(range(1, expected + 1)), "period_no"].nunique()
        rows.append({"area": area, "observed": observed, "usable": count, "expected": expected,
                     "complete": count == expected and len(part) == expected})
    return pd.DataFrame(rows)


def comparable_days(data, day, areas, market):
    previous = pd.Timestamp(day) - pd.Timedelta(days=1)
    return (day_quality(data, day, areas, market).complete.all()
            and day_quality(data, previous, areas, market).complete.all()
            and (market != "eprx" or expected_period_count(day) == expected_period_count(previous)))


def eprx_daily_kpis(data, day, selection):
    raw = select_day(data, day)
    if selection in AGGREGATE_REGION_GROUPS:
        raw, _ = aggregate_region_data(raw, selection)
    else:
        raw = raw.loc[raw.area.eq(selection)].copy()
    # The existing KPI helper accepts a profile and raw observations. For one day
    # the profile is the observations themselves, without any weekly averaging.
    profile = raw.assign(price_range=raw.max_price - raw.min_price,
                         shortage_volume=(raw.procurement_volume - raw.awarded_volume).clip(lower=0))
    return calculate_area_kpis(profile, raw)


def jepx_daily_kpis(data, spreads, day, area, duration, mode):
    raw = select_day(data, day)
    daily = select_day(spreads, day)
    if raw.empty or daily.empty:
        return pd.Series(dtype=object)
    week = pd.Timestamp(day) - pd.Timedelta(days=pd.Timestamp(day).weekday())
    result = create_area_price_spread_comparison(raw, daily, week, duration, mode)
    selected = result.loc[result.area.eq(area)]
    return selected.iloc[0] if not selected.empty else pd.Series(dtype=object)


def change_rate(current, previous):
    if not np.isfinite(current) or not np.isfinite(previous) or previous == 0:
        return np.nan
    return (current - previous) / previous


def daily_chart(data, day, areas, names, column, unit, market):
    raw = select_day(data, day)
    count = expected_period_count(day) if market == "eprx" else 48
    labels = ([period_start_label(day, n) for n in range(1, count + 1)]
              if market == "eprx" else [f"{n // 2:02d}:{n % 2 * 30:02d}" for n in range(48)])
    figure = go.Figure()
    for area in areas:
        part = raw.loc[raw.area.eq(area)].copy()
        if column == "award_rate":
            part[column] = part.awarded_volume.div(part.bid_volume.where(part.bid_volume.ne(0))) * 100
        # Reindex only the display axis: gaps remain NaN, never interpolated.
        part = part.loc[~part.period_no.duplicated(keep=False)].set_index("period_no")
        values = part[column].reindex(range(1, count + 1)).replace([np.inf, -np.inf], np.nan)
        name = names.get(area, area)
        figure.add_trace(go.Scatter(x=labels, y=values, name=name,
                                   line=dict(color=EPRX_AREA_COLORS.get(name)) if market == "eprx" else None,
                                   mode="lines", connectgaps=False))
    figure.update_layout(xaxis_title="시간대", yaxis_title=unit, hovermode="x unified",
                         legend=dict(itemclick="toggle", itemdoubleclick="toggleothers"))
    if market == "eprx":
        _finish(figure, unit)
        _add_autoscale_hint(figure)
    figure.update_xaxes(type="category", categoryorder="array", categoryarray=labels,
                        tickmode="array", tickvals=labels[::max(1, count // 12)])
    return figure
