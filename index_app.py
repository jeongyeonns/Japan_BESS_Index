"""Standalone dashboard. Existing market calculation engines are unchanged."""
from pathlib import Path
import math

import altair as alt
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.eprx_market_trend import weekly_market_trend

from utils.jepx_areas import JEPX_AREA_DISPLAY, JEPX_DETAIL_AREAS
from utils.jepx_index import calculate_week_index
from utils.jepx_loader import find_jepx_files, load_all_jepx_data
from utils.eprx_loader import find_eprx_files, load_all_eprx_data
from utils import eprx_index

# A live Streamlit process can retain the module from before the legacy update.
if not hasattr(eprx_index, "calculate_eprx_legacy_week_index"):
    from importlib import reload
    reload(eprx_index)

from utils.eprx_index import calculate_eprx_week_index, calculate_eprx_legacy_week_index
from utils.eprx_periods import expected_period_count, EPRX_REFORM_DATE

BASE = Path(__file__).resolve().parent
DATA_DIRECTORY = BASE / "data/jepx/raw"
EPRX_DIRECTORY = BASE / "data/eprx"
FUEL_PRICE_FILE = BASE / "data/fuel_prices_2026.csv"
JKM_PRICE_FILE = BASE / "data/jkm_prices_jpx_2026.csv"
LEGACY_LABEL = "3시간 블록"
MODERN_LABEL = "30분 코마"


@st.cache_data
def load_data(signatures):
    return load_all_jepx_data(DATA_DIRECTORY)


@st.cache_data
def load_eprx_data(signatures):
    return load_all_eprx_data(EPRX_DIRECTORY)


@st.cache_data
def load_fuel_prices(signature):
    if not FUEL_PRICE_FILE.exists():
        return pd.DataFrame(columns=["month", "jkm_usd_mmbtu", "japan_lng_usd_mmbtu", "australia_coal_usd_ton"])
    prices = pd.read_csv(FUEL_PRICE_FILE, parse_dates=["month"])
    return prices.sort_values("month")


@st.cache_data
def load_jkm_prices(signature):
    columns = ["contract_month", "evaluation_start", "evaluation_end", "comparison_month", "settlement_price_yen_mmbtu"]
    if not JKM_PRICE_FILE.exists():
        return pd.DataFrame(columns=columns)
    prices = pd.read_csv(JKM_PRICE_FILE, parse_dates=["evaluation_start", "evaluation_end", "comparison_month"])
    return prices.sort_values("comparison_month")


def monthly_jepx_spreads(data, area):
    dates = pd.to_datetime(data.delivery_date).dt.normalize()
    first = dates.min() - pd.Timedelta(days=dates.min().weekday())
    last = dates.max() - pd.Timedelta(days=dates.max().weekday())
    _, daily = weekly_results(data, "JEPX", area, first, last)
    daily = daily.loc[daily["valid"]].copy()
    date_column = "date" if "date" in daily.columns else "delivery_date"
    daily["month"] = pd.to_datetime(daily[date_column]).dt.to_period("M").dt.to_timestamp()
    return daily.groupby("month", as_index=False)[["tb2", "tb4"]].mean()


def comparison_jepx_periods(daily, weekly=True):
    data = daily.loc[daily.delivery_date.ge(pd.Timestamp("2026-01-01"))].copy()
    data.loc[~data.valid, ["tb2", "tb4"]] = float("nan")
    data["month"] = data.delivery_date - pd.to_timedelta(data.delivery_date.dt.weekday, unit="D") if weekly else data.delivery_date
    return data.groupby("month", as_index=False)[["tb2", "tb4"]].mean()


def build_fuel_comparison_figure(jepx_monthly, fuel_prices, jkm_prices, fuel_column, fuel_label, fuel_unit, weekly=True):
    common = jepx_monthly.sort_values("month")
    prices = (jkm_prices.rename(columns={"comparison_month": "month"}) if jkm_prices is not None else pd.DataFrame(columns=["month", fuel_column])) if fuel_column == "settlement_price_yen_mmbtu" else fuel_prices
    prices = prices.loc[prices.month.ge(pd.Timestamp("2026-01-01")) & prices[fuel_column].notna()].sort_values("month")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    yen = "엔"
    fig.add_trace(go.Scatter(x=common.month, y=common.tb2, name="JEPX TB2 (" + yen + "/kWh)", mode="lines+markers", line={"color": "#2563EB", "dash": "solid"}), secondary_y=False)
    fig.add_trace(go.Scatter(x=common.month, y=common.tb4, name="JEPX TB4 (" + yen + "/kWh)", mode="lines+markers", line={"color": "#0F766E", "dash": "solid"}), secondary_y=False)
    fuel_color = {"settlement_price_yen_mmbtu": "#DC2626", "japan_lng_usd_mmbtu": "#7C3AED", "australia_coal_usd_ton": "#EA580C"}[fuel_column]
    fig.add_trace(go.Scatter(x=prices.month, y=prices[fuel_column], name=f"{fuel_label} ({fuel_unit})", mode="lines+markers", connectgaps=False, marker={"size": 7}, line={"color": fuel_color, "dash": "dot", "width": 3}), secondary_y=True)
    for trace, unit in zip(fig.data, ["엔/kWh", "엔/kWh", fuel_unit]):
        trace.hovertemplate = "%{x|%Y-%m-%d}<br>%{y:,.4f} " + unit + "<extra>%{fullData.name}</extra>"
        trace.connectgaps = False
    fig.data[2].hovertemplate = "월별 관측기간: %{x|%Y-%m}<br>%{y:,.4f} " + fuel_unit + "<extra>%{fullData.name}</extra>"
    if fuel_column == "settlement_price_yen_mmbtu":
        if {"contract_month", "evaluation_start", "evaluation_end"}.issubset(prices.columns):
            fig.data[2].customdata = prices[["contract_month", "evaluation_start", "evaluation_end"]].astype(str).values
            fig.data[2].hovertemplate += "<br>계약월: %{customdata[0]}<br>평가기간: %{customdata[1]}~%{customdata[2]}"
        fig.add_shape(type="line", x0="2026-02-28", x1="2026-02-28", y0=0, y1=1, yref="paper", line=dict(color="gray", dash="dot"))
        fig.add_annotation(x="2026-02-28", y=1, yref="paper", text="2/28 중동 분쟁 시작", showarrow=False)
    fig.update_layout(height=548, margin={"l": 65, "r": 80, "t": 55, "b": 45}, legend={"orientation": "h", "y": 1.12}, hovermode="x unified")
    fig.update_xaxes(title_text="주차 시작일 (월요일)" if weekly else "날짜", tickformat="%Y-%m-%d", nticks=8)
    values = jepx_monthly.loc[jepx_monthly.month.ge(pd.Timestamp("2026-01-01")), ["tb2", "tb4"]].stack().dropna()
    limits = [min(0, float(values.min()) * 1.1), max(1, float(values.max()) * 1.1)] if not values.empty else [0, 1]
    fig.update_yaxes(title_text="JEPX 스프레드 (엔/kWh)", secondary_y=False, range=limits, tickformat=",.2f", showgrid=True)
    fuel_values = prices[fuel_column].dropna()
    if fuel_values.empty:
        fuel_limits, fuel_tick0, fuel_dtick = [0, 1], 0, 1
    else:
        low, high = float(fuel_values.min()), float(fuel_values.max())
        padding = max((high - low) * 0.1, abs(high) * 0.05, 0.5)
        fuel_dtick = 500 if fuel_column == "settlement_price_yen_mmbtu" and high - low <= 3500 else 1000 if fuel_column == "settlement_price_yen_mmbtu" else 1 if high - low <= 8 else 2
        fuel_tick0 = math.floor((low - padding) / fuel_dtick) * fuel_dtick
        fuel_limits = [fuel_tick0, math.ceil((high + padding) / fuel_dtick) * fuel_dtick]
    fig.update_yaxes(title_text=fuel_unit, secondary_y=True, range=fuel_limits, tickmode="linear", tick0=fuel_tick0, dtick=fuel_dtick, tickformat=",.0f", showgrid=False)
    return fig


def fuel_comparison_charts(daily, fuel_prices, jkm_prices=None):
    st.markdown("### JEPX 스프레드와 발전연료 가격 추이 비교")
    period = st.selectbox("분석 주기", ["주별", "일별"], key="fuel_frequency")
    jepx_monthly = comparison_jepx_periods(daily, weekly=period == "주별")
    st.caption("※ JKM 연동가격과 일본 LNG 수입가격은 현재 월별 자료만 확보되어 있습니다.  \n따라서 JEPX 스프레드만 선택한 주기에 따라 표시하며, 연료가격은 월별 기준으로 제공합니다.")
    latest = fuel_prices.month.max().strftime("%Y-%m") if not fuel_prices.empty else "없음"
    jkm_latest = jkm_prices.comparison_month.max().strftime("%Y-%m") if jkm_prices is not None and not jkm_prices.empty else "없음"
    st.caption(f"World Bank Pink Sheet 최신 갱신월: {latest} · JPX JKM 최신 평가기간 종료월: {jkm_latest}")
    charts = [
        ("JKM 연동가격(JPX)", "settlement_price_yen_mmbtu", "엔/MMBtu"),
        ("일본 LNG 수입가격", "japan_lng_usd_mmbtu", "USD/MMBtu"),
    ]
    for label, column, unit in charts:
        fig = build_fuel_comparison_figure(jepx_monthly, fuel_prices, jkm_prices, column, label, unit, weekly=period == "주별")
        st.markdown(f"#### {label}")
        descriptions = {
            "settlement_price_yen_mmbtu": "JKM은 동북아 LNG 현물시장의 가격지표로, 중동 사태와 같은 국제 LNG 공급 충격을 빠르게 반영하는 지표입니다.  \n본 그래프는 JKM 현물가격 자체가 아닌 JPX의 JKM 연동 선물 최종정산가격이며, 평가기간 종료월을 기준으로 표시한 값입니다.",
            "japan_lng_usd_mmbtu": "일본에 실제 도착한 LNG의 평균 수입가격으로, 장기계약 물량과 유가 연동 가격 등이 반영된 값입니다.  \nJKM과 달리 현물시장 가격 급등이 수입가격에 반영되기까지 시차가 있어, 두 가격의 움직임이 다르게 나타날 수 있는 지표입니다.",
        }
        st.caption(descriptions[column])
        st.plotly_chart(fig, use_container_width=True)
        if column == "settlement_price_yen_mmbtu":
            st.caption(f"출처: [JEPX 스폿시장 가격](https://www.jepx.jp/electricpower/market-data/spot/) / [JPX LNG (Platts JKM) 선물 최종정산가격](https://www.jpx.co.jp/markets/derivatives/special-quotation/) · 최신 확보월(평가기간 종료월): {jkm_latest}")
        elif column == "japan_lng_usd_mmbtu":
            st.caption(f"출처: [JEPX 스폿시장 가격](https://www.jepx.jp/electricpower/market-data/spot/) / [World Bank Pink Sheet (LNG Japan)](https://www.worldbank.org/en/research/commodity-markets) · 최신 확보월: {latest}")

def money(value):
    return "계산 불가" if pd.isna(value) else f"{value / 10000:,.1f}만 엔/MW/year"


def change(current, previous):
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return None
    return f"{(current / previous - 1) * 100:+.1f}% 전주 대비"


@st.cache_data(show_spinner="지역별 주간 Index 계산 중…")
def weekly_results(data, market, area, first, last):
    """Cache all weeks per source/region, independent of the selected week."""
    rows, details = [], []
    regional = data.loc[data.area.eq(area)]
    for week in pd.date_range(first, last, freq="W-MON"):
        subset = regional.loc[regional.delivery_date.between(week, week + pd.Timedelta(days=6))]
        if market == "JEPX":
            daily, summary = calculate_week_index(subset, week, area)
            for hours in (2, 4):
                rows.append(dict(week=week, series=f"TB{hours}", value=summary[f"tb{hours}_index"],
                                 valid_days=summary["valid_days"], complete_days=summary["valid_days"],
                                 average_price=summary[f"tb{hours}_spread"], used_periods=None))
        else:
            for regime, calculate in ((LEGACY_LABEL, calculate_eprx_legacy_week_index), (MODERN_LABEL, calculate_eprx_week_index)):
                days = [d for d in pd.date_range(week, periods=7) if (d < EPRX_REFORM_DATE) == (regime == LEGACY_LABEL)]
                if not days:
                    continue
                daily, summary = calculate(subset, week, area)
                for row in summary.to_dict("records"):
                    rows.append(dict(week=week, series=f"{row['scenario']}코마", value=row["annual_index"],
                                     valid_days=row["valid_days"], complete_days=row["complete_days"],
                                     average_price=row["average_price"], used_periods=row["used_periods"],
                                     regime=regime, expected_days=len(days), segment_start=days[0], segment_end=days[-1]))
                details.append(daily.loc[daily.date.isin(days)].assign(week=week, regime=regime))
            continue
        details.append(daily.assign(week=week))
    result = pd.DataFrame(rows)
    result["week_end"] = result.week + pd.Timedelta(days=6)
    result["quality"] = result.apply(lambda r: "계산 불가" if pd.isna(r.value) else "불완전" if r.complete_days < r.get("expected_days", 7) else "제도별 부분 주간" if r.get("expected_days", 7) < 7 else "완전", axis=1)
    return result, pd.concat(details, ignore_index=True)


def trend(history, selected_week, key, procurement=None):
    is_jepx = key == "JEPX_trend"
    chart_data = history.sort_values(["series", "week"]).copy()
    # Split paths at missing weeks instead of visually bridging absent values.
    chart_data["segment"] = chart_data.groupby("series")["value"].transform(lambda s: s.isna().cumsum()).astype(str)
    if not is_jepx and "regime" in chart_data:
        chart_data["segment"] = chart_data["regime"] + ":" + chart_data.groupby(["series", "regime"])["value"].transform(lambda s: s.isna().cumsum()).astype(str)
    line = alt.Chart(chart_data).mark_line(point=True).encode(
        x=alt.X("week:T", title="주차 시작일 (월요일)", axis=alt.Axis(format="%-m/%-d")),
        y=alt.Y("value:Q", title="만 엔/MW/년", axis=alt.Axis(labelExpr="format(datum.value / 10000, ',.0f')")),
        color=alt.Color("series:N", title="지표", scale=alt.Scale(scheme="tableau10"),
                        legend=alt.Legend(labelExpr="datum.label === 'TB2' ? '2시간형 (TB2)' : '4시간형 (TB4)'" if is_jepx else "(parseInt(datum.label) / 2) + '시간 기준'")), detail="segment:N",
        tooltip=[alt.Tooltip("week:T", title="시작일", format="%Y-%m-%d"),
                 alt.Tooltip("week_end:T", title="종료일", format="%Y-%m-%d"),
                 alt.Tooltip("series:N", title="지표"), alt.Tooltip("value:Q", title="엔/MW/년", format=",.2f"),
                 alt.Tooltip("valid_days:Q", title="집계 일수"),
                 alt.Tooltip("complete_days:Q", title="완전일 수"), alt.Tooltip("quality:N", title="완전성")]
                + ([] if is_jepx else [alt.Tooltip("regime:N", title="거래제도"), alt.Tooltip("segment_start:T", title="집계 시작", format="%Y-%m-%d"), alt.Tooltip("segment_end:T", title="집계 종료", format="%Y-%m-%d")]))
    if not is_jepx:
        line = line.encode(strokeDash=alt.value([1, 0]))
        line = line.encode(y=alt.Y("value:Q", title="수익기회 Index (엔/MW/year)", axis=alt.Axis(format=",.0f")))
    rule = alt.Chart(pd.DataFrame({"week": [selected_week]})).mark_rule(color="#94a3b8", strokeDash=[4, 4]).encode(x="week:T")
    st.caption("선택 주차는 점선이며, 정확한 금액과 데이터 집계 일수는 툴팁에서 확인할 수 있습니다.")
    chart = (line + rule).properties(height=280)
    if is_jepx:
        chart = chart.properties(title="주차별 차익거래 수익기회")
    else:
        st.markdown("#### 주차별 조정력 수익기회")
        st.caption("3/14 제도 변경: 3시간 블록 → 30분 코마")
        st.caption("점선 왼쪽: 기존 3시간 블록 · 점선 오른쪽: 변경 후 30분 코마")
        reform = alt.Chart(pd.DataFrame({"date": [EPRX_REFORM_DATE], "label": ["3/14 제도 변경"]})).encode(x="date:T")
        chart = (line + rule + reform.mark_rule(color="#a66a36", strokeDash=[6, 3])).properties(height=300)
        st.caption("3/14부터 3시간 블록·주간 거래가 30분 코마·전일 거래로 변경된 자료입니다. 선은 제도별로 분리되어 있으며, 전후 차이는 가격과 제도 변경의 영향을 함께 포함한 값입니다.")
        if procurement is not None:
            volume = procurement.sort_values(["regime", "week"]).copy()
            volume["segment"] = volume.regime + ":" + volume.groupby("regime").procurement.transform(lambda s: s.isna().cumsum()).astype(str)
            volume["series"] = "주간 평균 모집량 (MW)"
            legend = alt.Legend(labelExpr="datum.label === '주간 평균 모집량 (MW)' ? datum.label : (parseInt(datum.label) / 2) + '시간 기준'")
            scale = alt.Scale(domain=["12코마", "24코마", "36코마", "48코마", "주간 평균 모집량 (MW)"], range=["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#808080"])
            color = alt.Color("series:N", title="지표", scale=scale, legend=legend)
            # Keep both index rules on the left axis; resolve the volume axis separately.
            line = line.encode(color=color)
            left = line + rule + reform.mark_rule(color="#a66a36", strokeDash=[6, 3])
            right = alt.Chart(volume).mark_line(strokeDash=[4, 4], point=alt.OverlayMarkDef(shape="circle")).encode(
                x=alt.X("week:T", title="주차 시작일 (월요일)", axis=alt.Axis(format="%-m/%-d")),
                y=alt.Y("procurement:Q", title="주간 평균 모집량 (MW)", axis=alt.Axis(orient="right", format=",.2f"), scale=alt.Scale(zero=True)),
                color=color, detail="segment:N",
                tooltip=[alt.Tooltip("week:T", title="주차 시작", format="%Y-%m-%d"), alt.Tooltip("procurement:Q", title="주간 평균 모집량 (MW)", format=",.4f"), alt.Tooltip("regime:N", title="거래제도"), alt.Tooltip("segment_start:T", title="집계 시작"), alt.Tooltip("segment_end:T", title="집계 종료"), alt.Tooltip("procurement_periods:Q", title="모집량 관측구간"), alt.Tooltip("expected_periods:Q", title="기대구간")])
            chart = alt.layer(left, right).resolve_scale(y="independent").properties(height=300)
        chart = chart.configure_legend(orient="top", direction="horizontal", title=None, columns=5, offset=8)
    st.altair_chart(chart, width="stretch", key=key)
    if not is_jepx and procurement is not None:
        st.caption("※ 모집량은 TSO 조달지역 기준이며, 수익기회 Index는 전원 소재지역별 최고 낙찰가격을 기준으로 계산합니다.")


@st.cache_data
def cached_market_trend(data, area, first, last):
    return weekly_market_trend(data, area, first, last)


def jepx_card(row, previous):
    label = f"{row.series[-1]}시간형 차익거래 Index ({row.series})"
    exact = "계산 가능한 데이터가 없습니다." if pd.isna(row.value) else f"{row.value:,.2f} 엔/MW/year"
    st.metric(label, money(row.value), delta=change(row.value, previous), help=exact)
    st.divider()
    spread = "—" if pd.isna(row.average_price) else f"{row.average_price:,.2f}엔/kWh"
    st.html(f"""<div style="display:grid;grid-template-columns:1fr auto;gap:0.5rem 1rem;font-size:0.95rem;">
        <span>주간 평균 스프레드</span><span style="text-align:right;font-variant-numeric:tabular-nums;">{spread}</span>
        <span>데이터 집계</span><span style="text-align:right;font-variant-numeric:tabular-nums;">{row.valid_days}/7일</span>
        </div>""")


def eprx_card(row):
    hours = int(row.series[:-2]) // 2
    exact = "계산 가능한 데이터가 없습니다." if pd.isna(row.value) else f"{row.value:,.2f} 엔/MW/year"
    st.metric(f"{hours}시간 기준 조정력 Index", money(row.value), help=exact)
    st.divider()
    price = "—" if pd.isna(row.average_price) else f"{row.average_price:,.2f}엔/kW·30분"
    price_label = "선택 블록 평균 최고 낙찰가격" if row.regime == LEGACY_LABEL else "선택 코마 평균 최고 낙찰가격"
    st.html(f"""<div style="display:grid;grid-template-columns:1fr auto;gap:0.5rem 1rem;font-size:0.95rem;">
        <span>{price_label}</span><span style="text-align:right;font-variant-numeric:tabular-nums;">{price}</span>
        <span>데이터 집계</span><span style="text-align:right;font-variant-numeric:tabular-nums;">{row.valid_days}/{row.expected_days}일</span>
        </div>""")


def eprx_quality(data, week, area):
    selected = data.loc[data.area.eq(area) & data.delivery_date.between(week, week + pd.Timedelta(days=6))]
    rows = []
    for day in pd.date_range(week, periods=7):
        g = selected.loc[selected.delivery_date.eq(day)]
        rows.append({"날짜": day, "시간 단위": "30분" if expected_period_count(day) == 48 else "3시간", "고유 코마 수": g.period_no.nunique(),
                     "중복 코마 행 (통합 후)": int(g.period_no.duplicated(keep=False).sum()),
                     "낙찰량 양수·0엔": int((g.awarded_volume.gt(0) & g.max_price.eq(0)).sum()),
                     "낙찰량 0": int(g.awarded_volume.eq(0).sum()),
                     "가격 결측": int(g.max_price.isna().sum()), "낙찰량 미확인": int(g.awarded_volume.isna().sum())})
    return pd.DataFrame(rows)


def methodology():
    with st.expander("데이터 해석 및 유의사항"):
        st.markdown("JEPX는 48코마가 모두 유효한 날, EPRX는 필요한 수의 유효 코마 또는 블록이 있는 날만 집계한 값입니다. 3/9~3/15는 이전 5일과 이후 2일을 분리한 평균이며, 두 제도를 혼합한 평균은 제공하지 않습니다. 온라인·오프라인 구분은 원자료에 없는 정보입니다. 낙찰량 0과 결측은 제외 대상이며, 낙찰량 양수의 실제 0엔 가격은 유효한 값입니다.")
        st.markdown("EPRX는 공표된 최고 낙찰가격 기준이며, 상한가격 적용·사후 정산·페널티·수수료를 반영한 실제 정산액과는 다른 값입니다.")
        st.markdown("JEPX와 EPRX 지표를 단순 합산한 값은 실제 ESS 총수익이 아닙니다. 결측은 0으로 대체하지 않습니다. 전주 대비는 정확히 7일 전 주차와 비교한 값이며, 전주 값이 없거나 0이면 표시하지 않습니다. 불완전한 주차를 비교할 때는 집계 일수도 함께 확인하는 것이 필요합니다.")


def main():
    st.set_page_config(page_title="Japan BESS Market Opportunity Index", layout="wide")
    st.title("Japan BESS Market Opportunity Index")
    with st.container(key="index_intro"):
        with st.container(key="index_intro_copy"):
            st.markdown("Modo Energy는 영국·독일 등 해외 전력시장의 ESS 수익성을 MW당 연간 금액으로 보여주는 Index를 제공합니다.")
            st.markdown("일본은 해당 Index의 공개 대상에 포함되어 있지 않아, 본 앱에서는 JEPX·EPRX 시장가격을 활용해 일본의 지역별·주차별 수익기회를 비교할 수 있도록 했습니다.")
        with st.container(key="index_intro_notes"):
            st.caption("※ 실제 ESS 운영수익이 아닌, 시장가격을 바탕으로 계산한 이론적 수익기회입니다.")
            st.caption("[Modo Energy 공식 벤치마크](https://modoenergy.com/product/benchmarks)")
    st.html("""<style>
        :is(.st-key-index_intro, .st-key-jepx_explanation, .st-key-eprx_explanation),
        :is(.st-key-index_intro, .st-key-jepx_explanation, .st-key-eprx_explanation)
        > [data-testid="stVerticalBlock"] { gap: 12px; }
        :is(.st-key-index_intro_copy, .st-key-index_intro_notes, .st-key-eprx_notes),
        :is(.st-key-index_intro_copy, .st-key-index_intro_notes, .st-key-eprx_notes)
        > [data-testid="stVerticalBlock"] { gap: 5px; }
        [data-testid="stMetric"] { container-type: inline-size; }
        [data-testid="stMetricValue"] {
            font-size: clamp(0.8rem, 5cqi, 2rem);
            white-space: nowrap;
        }
    </style>""")
    sources, diagnostics = {}, {}
    for market, directory, finder, loader in (("JEPX", DATA_DIRECTORY, find_jepx_files, load_data), ("EPRX", EPRX_DIRECTORY, find_eprx_files, load_eprx_data)):
        try:
            files = finder(directory)
            paths = files.get("file_path", []) if market == "JEPX" else files
            signatures = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)
            if not signatures:
                st.warning(f"{market} 원자료가 없습니다: {directory.relative_to(BASE)}")
                continue
            loaded = loader(signatures)
            if not loaded[0].empty:
                sources[market] = loaded[0]
                diagnostics[market] = loaded[2:] if market == "JEPX" else loaded[1:]
        except Exception as exc:
            st.error(f"{market} 데이터 로딩 실패: {exc}")
    if not sources:
        st.warning("분석 가능한 원자료가 없습니다.")
        methodology()
        return
    dates = pd.concat([d.delivery_date for d in sources.values()]).dropna()
    if dates.empty:
        st.warning("분석 가능한 날짜가 없습니다.")
        methodology()
        return
    first = dates.min().normalize() - pd.Timedelta(days=dates.min().weekday())
    last = dates.max().normalize() - pd.Timedelta(days=dates.max().weekday())
    weeks = list(pd.date_range(first, last, freq="W-MON"))[::-1]
    controls = st.columns(2)
    week = controls[0].selectbox("분석 주차 (월~일)", weeks, format_func=lambda d: f"{d:%Y-%m-%d} ~ {d + pd.Timedelta(days=6):%Y-%m-%d}")
    controls[0].caption("사용자가 선택한 주차의 시장가격 수준이 1년간 유지된다고 가정하여, 해당 주차의 일평균 수익기회를 MW당 연간 금액으로 환산합니다.  \n이를 통해 특정 주차의 시장 수익성을 확인하고, 지역별·주차별 수익기회가 어떻게 달라지는지 비교할 수 있습니다.")
    available = set().union(*(set(d.area) for d in sources.values()))
    areas = [a for a in JEPX_DETAIL_AREAS if a in available]
    if not areas:
        st.warning("지원 지역 데이터가 없습니다.")
        return
    area = controls[1].selectbox("분석 지역", areas, format_func=lambda a: JEPX_AREA_DISPLAY[a])
    st.caption(f"{JEPX_AREA_DISPLAY[area]} | {week:%Y-%m-%d} (월) ~ {week + pd.Timedelta(days=6):%Y-%m-%d} (일)")
    market_tabs = st.tabs(["JEPX — 차익거래 수익기회", "EPRX — 조정력 수익기회"])
    for tab, (market, title) in zip(market_tabs, (("JEPX", "차익거래 수익기회"), ("EPRX", "조정력 수익기회"))):
        with tab:
            st.divider()
            st.subheader(f"{market} — {title}")
            if market == "JEPX":
                with st.container(key="jepx_explanation"):
                    st.markdown("하루 중 전력가격이 가장 높은 2시간 또는 4시간과 가장 낮은 2시간 또는 4시간의 평균 스프레드를 구하고, 이를 주간 평균으로 계산합니다.")
                    st.markdown("**산식**  \n주간 평균 스프레드 × 1,000kW × 거래시간(2H/4H) × 365일")
                    st.markdown("**ex)** 2시간형 평균 스프레드 10엔/kWh → 730만 엔/MW/year")
            else:
                with st.container(key="eprx_explanation"):
                    st.markdown("하루 중 최고 낙찰가격이 높은 시간대부터 6·12·18·24시간을 선택하고, 해당 시간대에 모두 낙찰된다고 가정합니다.")
                    st.markdown("**산식**  \n일별 상위 N개 코마의 최고 낙찰가격 합계 × 1,000kW → 주간 일평균 × 365일")
                    st.markdown("**ex)** 낙찰가격 5엔/kW·30분, 하루 12코마(6시간) → 2,190만 엔/MW/year")
                    with st.container(key="eprx_notes"):
                        st.caption("※ 최고 낙찰가격 기준의 이론적 수익기회로, 실제 평균 낙찰수익과는 차이가 있습니다.")
                        st.caption("※ 2026년 3월 14일 이전에는 3시간 블록 기준의 별도 산식을 적용합니다.")
            if market not in sources:
                st.info(f"{market} 데이터가 없습니다.")
                continue
            data = sources[market]
            history, daily = weekly_results(data, market, area, first, last)
            current = history.loc[history.week.eq(week)]
            if market == "EPRX":
                regimes = current.regime.unique().tolist()
                regime = st.radio("해당 주차의 거래제도", regimes, horizontal=True) if len(regimes) > 1 else regimes[0]
                current = current.loc[current.regime.eq(regime)]
                if len(regimes) > 1:
                    st.warning("제도 변경이 포함된 주차입니다. 3/9~3/13의 3시간 블록 5일과 3/14~3/15의 30분 코마 2일을 별도로 집계한 값입니다.")
                segment = current.iloc[0]
                st.caption(f"집계 기준은 {regime}이며, 대상 기간은 {segment.segment_start:%Y-%m-%d}~{segment.segment_end:%Y-%m-%d}입니다. 24시간 기준은 참고용입니다.")
            previous = history.loc[history.week.eq(week - pd.Timedelta(days=7))].set_index("series")
            cards = [card for _ in range(0, len(current), 2) for card in st.columns(2)]
            for card, row in zip(cards, current.itertuples()):
                with card.container(border=True):
                    if market == "JEPX":
                        old = previous.loc[row.series, "value"] if row.series in previous.index else float("nan")
                        jepx_card(row, old)
                        continue
                    eprx_card(row)
            if current.value.isna().all():
                st.warning("선택 주차·지역에 계산 가능한 데이터가 없습니다. 결측은 0으로 표시하지 않습니다.")
            elif (current.complete_days < (current.expected_days if market == "EPRX" else 7)).any():
                st.warning("불완전한 주간 데이터입니다. EPRX는 필요한 수 이상의 유효 코마·블록이 있는 날만 집계한 값이며, 일부 관측값만으로 계산된 날은 상세 검증에서 확인할 수 있습니다." if market == "EPRX" else "불완전한 주간 데이터입니다. 유효일만 집계하므로 전주와 비교 시 집계 일수를 확인하세요.")
            if market == "EPRX":
                choices = st.multiselect("그래프 시나리오", current.series.tolist(), default=current.series.tolist(), format_func=lambda s: f"{int(s[:-2]) // 2}시간 기준")
                shown = current.loc[current.series.isin(choices)]
                bar = alt.Chart(shown).mark_bar(color="#537a96").encode(
                    x=alt.X("series:N", title="시나리오", sort=current.series.tolist(), axis=alt.Axis(labelExpr="(parseInt(datum.label) / 2) + '시간'")),
                    y=alt.Y("value:Q", title="만 엔/MW/년", axis=alt.Axis(labelExpr="format(datum.value / 10000, ',.0f')")),
                    tooltip=[alt.Tooltip("series:N", title="시나리오"), alt.Tooltip("value:Q", title="엔/MW/년", format=",.2f"),
                             alt.Tooltip("average_price:Q", title="선택 평균가격 (엔/kW·30분)", format=".4f"), alt.Tooltip("valid_days:Q", title="집계 일수")])
                st.altair_chart(bar.properties(height=240), width="stretch")
                chart_history = history.loc[history.series.isin(choices)]
            else:
                chart_history = history
            procurement = cached_market_trend(data, area, first, last) if market == "EPRX" else None
            trend(chart_history, week, f"{market}_trend", procurement)
            if market == "JEPX":
                fuel_prices = load_fuel_prices((str(FUEL_PRICE_FILE), FUEL_PRICE_FILE.stat().st_mtime_ns) if FUEL_PRICE_FILE.exists() else None)
                jkm_prices = load_jkm_prices((str(JKM_PRICE_FILE), JKM_PRICE_FILE.stat().st_mtime_ns) if JKM_PRICE_FILE.exists() else None)
                if not fuel_prices.empty or not jkm_prices.empty:
                    fuel_comparison_charts(daily, fuel_prices, jkm_prices)
            with st.expander(f"{market} 주간 수치·일별 검증"):
                table = history.drop(columns="used_periods") if market == "JEPX" else history
                st.dataframe(table.rename(columns={"week": "주차 시작", "week_end": "주차 종료", "series": "지표" if market == "JEPX" else "시간조건 (30분 환산 수)", "value": "Index (엔/MW/년)", "valid_days": "집계 일수", "complete_days": "완전일 수", "average_price": "평균 스프레드 (엔/kWh)" if market == "JEPX" else "선택 평균가격 (엔/kW·30분)", "quality": "완전성", "regime": "거래제도", "expected_days": "해당 제도 일수", "segment_start": "집계 시작", "segment_end": "집계 종료", "used_periods": "사용 코마 또는 블록 수"}), hide_index=True)
                if market == "EPRX":
                    st.dataframe(eprx_quality(data, week, area), hide_index=True)
                    st.caption("고유 시간대·중복은 기존 로더 통합 후 기준입니다. 완전일은 해당 제도의 8개 블록 또는 48개 코마 모두 유효한 날입니다. 파일 간 중복 해소 내역은 아래 원자료 검증에서 확인할 수 있습니다.")
                st.dataframe(daily.loc[daily.week.eq(week)].drop(columns="week").rename(columns={
                    "delivery_date": "날짜", "date": "날짜", "tb2": "TB2 (엔/kWh)", "tb4": "TB4 (엔/kWh)",
                    "valid": "유효 여부", "reason": "검증 결과", "scenario": "시간조건 (30분 환산 수)", "observed_periods": "관측 시간대 수",
                    "valid_periods": "유효 시간대 수", "missing_prices": "가격 결측", "no_award_periods": "낙찰량 0",
                    "selected_periods": "사용 코마 또는 블록 수", "average_price": "선택 평균가격 (엔/kW·30분)",
                    "daily_opportunity": "일간 기회 (엔/MW)", "complete_day": "모든 시간대 유효", "regime": "거래제도"}), hide_index=True)
            with st.expander(f"{market} 원자료 검증·중복 해소 내역"):
                for diagnostic in diagnostics[market]:
                    st.dataframe(diagnostic, hide_index=True)
    methodology()


if __name__ == "__main__":
    main()
# USD/�� unit compatibility marker
