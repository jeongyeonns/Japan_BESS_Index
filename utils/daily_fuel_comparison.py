"""Observed daily prices only; never interpolate or repeat monthly prices."""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

JKM_COLUMNS = ["date", "price", "unit", "source", "price_type", "contract_month"]


def load_daily_jkm(path):
    if not Path(path).exists():
        return pd.DataFrame(columns=JKM_COLUMNS)
    data = pd.read_csv(path, dtype=str).fillna("")
    if not set(JKM_COLUMNS).issubset(data.columns):
        raise ValueError("일별 JKM CSV의 필수 컬럼이 없습니다.")
    data["date"] = pd.to_datetime(data.date, format="%Y-%m-%d", errors="raise")
    data["price"] = pd.to_numeric(data.price, errors="raise")
    if (not data.unit.eq("USD/MMBtu").all() or not data.price_type.isin(["spot", "futures"]).all()
            or not data.source.str.strip().ne("").all() or not np.isfinite(data.price).all()):
        raise ValueError("일별 JKM 단위·출처·가격 종류·가격을 확인해 주세요.")
    futures = data.price_type.eq("futures")
    if (not data.loc[futures, "contract_month"].str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all()
            or not data.loc[~futures, "contract_month"].eq("").all()
            or data.duplicated(["date", "source", "price_type", "contract_month"]).any()):
        raise ValueError("일별 JKM 계약월 또는 중복 관측값을 확인해 주세요.")
    return data.sort_values("date")


def comparison_rows(daily, jkm, start, end, weekly=False):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    rows = []
    valid = daily.loc[daily.valid].copy()
    for field in ("tb2", "tb4"):
        part = valid[["delivery_date", field]].rename(columns={"delivery_date": "date", field: "value"})
        rows.append(part.assign(series=field.upper(), unit="엔/kWh"))
    for (source, kind, contract), group in jkm.groupby(["source", "price_type", "contract_month"], dropna=False):
        label = "JKM 선물가격" if kind == "futures" else "JKM 현물가격"
        label += f" {contract} ({source})"
        rows.append(group[["date", "price"]].rename(columns={"price": "value"}).assign(series=label, unit="USD/MMBtu"))
    result = pd.concat(rows, ignore_index=True)
    result = result.loc[result.date.between(start, end)].dropna(subset=["value"])
    result["period"] = result.date - pd.to_timedelta(result.date.dt.weekday, unit="D") if weekly else result.date
    return result.groupby(["period", "series", "unit"], as_index=False).agg(value=("value", "mean"), observed_days=("date", "nunique"))


def comparison_figure(rows, start, end, weekly=False):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for (label, unit), group in rows.groupby(["series", "unit"], sort=False):
        fuel = unit == "USD/MMBtu"
        # Missing periods stay gaps. Futures contracts are separate traces.
        grid_start = pd.Timestamp(start)
        if weekly:
            grid_start -= pd.Timedelta(days=grid_start.weekday())
        group = group.set_index("period").reindex(pd.date_range(grid_start, end, freq="7D" if weekly else "D"))
        fig.add_trace(go.Scatter(x=group.index, y=group.value, name=f"{label} ({unit})", mode="lines+markers",
            connectgaps=False, customdata=group[["observed_days"]],
            line=dict(color="#DC2626" if fuel else {"TB2": "#2563EB", "TB4": "#0F766E"}[label], dash="dot" if fuel else "solid"),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.4f} " + unit + "<br>관측일: %{customdata[0]}일<extra>%{fullData.name}</extra>"), secondary_y=fuel)
    event = "2026-02-28"
    fig.add_shape(type="line", x0=event, x1=event, y0=0, y1=1, yref="paper", line=dict(color="gray", dash="dot"))
    fig.add_annotation(x=event, y=1, yref="paper", text="2026-02-28 중동 분쟁 시작", showarrow=False)
    left = pd.Timestamp(start)
    if weekly:
        left -= pd.Timedelta(days=left.weekday())
    fig.update_xaxes(range=[left, pd.Timestamp(end)], tickformat="%m/%d")
    fig.update_yaxes(title_text="JEPX 스프레드 (엔/kWh)", secondary_y=False, tickformat=",.2f", rangemode="tozero")
    fig.update_yaxes(title_text="JKM 가격 (USD/MMBtu)", secondary_y=True, tickformat=",.2f", rangemode="tozero")
    fig.update_layout(height=350, hovermode="x unified", margin=dict(t=40, b=40))
    return fig
