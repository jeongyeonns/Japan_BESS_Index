"""Primary reserve: TSO procurement MW versus source-area maximum prices."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.eprx_periods import EPRX_REFORM_DATE, expected_period_count


def weekly_market_trend(data, area, first, last):
    selected = data.loc[data.area.eq(area) & data.original_product.eq("一次調整力")].copy()
    selected["delivery_date"] = pd.to_datetime(selected.delivery_date).dt.normalize()
    rows = []
    for week in pd.date_range(first, last, freq="W-MON"):
        for legacy, regime in [(True, "3시간 블록"), (False, "30분 코마")]:
            days = [d for d in pd.date_range(week, periods=7) if (d < EPRX_REFORM_DATE) == legacy]
            if not days:
                continue
            g = selected.loc[selected.delivery_date.isin(days)].copy()
            expected = sum(expected_period_count(d) for d in days)
            periods = pd.to_numeric(g.period_no, errors="coerce")
            duplicates = g.duplicated(["delivery_date", "period_no"], keep=False)
            valid_period = periods.isin(range(1, (8 if legacy else 48) + 1)) & ~duplicates
            # Different source statuses cannot be silently mixed in one segment.
            if "source_status" in g and g.source_status.nunique() > 1:
                valid_period[:] = False
            observed = int(valid_period.sum())
            quantity = pd.to_numeric(g.procurement_volume, errors="coerce")
            price = pd.to_numeric(g.max_price, errors="coerce")
            awards = pd.to_numeric(g.awarded_volume, errors="coerce")
            q_ok = valid_period & g.volume_unit.eq("MW") & np.isfinite(quantity) & quantity.ge(0)
            p_ok = valid_period & g.price_unit.eq("円/kW・30分") & np.isfinite(price) & price.ge(0) & np.isfinite(awards) & awards.gt(0)
            duration = pd.Series(3.0 if legacy else 0.5, index=g.index)
            def mean(values, mask):
                return float((values[mask] * duration[mask]).sum() / duration[mask].sum()) if mask.any() else np.nan
            rows.append(dict(week=week, regime=regime, segment_start=days[0], segment_end=days[-1],
                procurement=mean(quantity, q_ok), max_price=mean(price, p_ok),
                expected_periods=expected, observed_periods=observed, procurement_periods=int(q_ok.sum()),
                price_periods=int(p_ok.sum()), duplicate_rows=int(duplicates.sum()),
                procurement_hours=float(duration[q_ok].sum()), price_hours=float(duration[p_ok].sum()),
                source_files=", ".join(sorted(g.source_file.dropna().unique())) if "source_file" in g else "",
                incomplete=bool(q_ok.sum() < expected or p_ok.sum() < expected)))
    return pd.DataFrame(rows)


def market_trend_figure(rows):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for i, (regime, g) in enumerate(rows.groupby("regime", sort=False)):
        details = g[["regime", "segment_start", "segment_end", "procurement_periods", "price_periods", "expected_periods"]].astype(str).values
        fig.add_trace(go.Bar(x=g.week, y=g.procurement, name="주간 평균 모집량 (MW, TSO별)",
            marker_color="#94a3b8", offsetgroup=regime, legendgroup="procurement", showlegend=i == 0,
            customdata=details, hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f} MW<br>%{customdata[0]}<br>%{customdata[1]}~%{customdata[2]}<br>유효 구간 %{customdata[3]}/%{customdata[5]}<extra>%{fullData.name}</extra>"), secondary_y=False)
        fig.add_trace(go.Scatter(x=g.week, y=g.max_price, name="주간 평균 최고 낙찰가격 (엔/kW·30분, 전원 소재지역별)",
            mode="lines+markers", connectgaps=False, line=dict(color="#a66a36"), legendgroup="price", showlegend=i == 0,
            customdata=details, hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.4f} 엔/kW·30분<br>%{customdata[0]}<br>%{customdata[1]}~%{customdata[2]}<br>유효 구간 %{customdata[4]}/%{customdata[5]}<extra>%{fullData.name}</extra>"), secondary_y=True)
    fig.add_shape(type="line", x0="2026-03-14", x1="2026-03-14", y0=0, y1=1, yref="paper", line=dict(dash="dot", color="#a66a36"))
    fig.update_xaxes(title_text="주차 시작일 (월요일)", tickformat="%m/%d")
    fig.update_yaxes(title_text="모집량 (MW, TSO별)", tickformat=",.1f", rangemode="tozero", secondary_y=False)
    fig.update_yaxes(title_text="최고 낙찰가격 (엔/kW·30분)", tickformat=",.2f", rangemode="tozero", secondary_y=True)
    fig.update_layout(height=340, barmode="group", legend=dict(orientation="h", y=1.25), margin=dict(t=75,b=45))
    return fig
