"""Daily renderers sharing the production data, KPI definitions and table styling."""

import pandas as pd
import streamlit as st

from utils.daily_analysis import (available_dates, select_day, day_quality, comparable_days,
                                 eprx_daily_kpis, jepx_daily_kpis, change_rate, daily_chart)
from utils.eprx_area_groups import AGGREGATE_REGION_GROUPS, AGGREGATE_REGION_CAPTIONS
from utils.eprx_areas import EPRX_AREA_OPTIONS, EPRX_AREA_DISPLAY
from utils.jepx_areas import JEPX_DETAIL_AREA_OPTIONS
from views.jepx_view import MODE_LABELS, _render_metric_hierarchy_table, _fmt


def _date_selector(data, key):
    dates = available_dates(data)
    if not dates:
        st.info("선택 가능한 실제 데이터 날짜가 없습니다.")
        return None
    return st.selectbox("분석일자", dates, format_func=lambda d: f"{pd.Timestamp(d):%Y-%m-%d}", key=key)


def _quality(data, day, areas, names, market):
    quality = day_quality(data, day, areas, market)
    for row in quality.itertuples():
        message = f"{names.get(row.area, row.area)} 데이터 {'완전' if row.complete else '불완전'}: {row.observed}/{row.expected}코마"
        if not row.complete:
            message += f" · 유효 코마 {row.usable}개 (누락·중복·결측 확인 필요)"
        (st.caption if row.complete else st.warning)(message)
    if not quality.complete.all():
        st.caption("관측된 값만 표시합니다. 누락·결측·중복 코마를 보완하지 않으며 전일 비교는 제공하지 않습니다.")


def render_eprx_daily_analysis(data, price_unit, table_renderer):
    st.subheader("EPRX Daily 분석")
    day = _date_selector(data, "eprx_daily_date")
    if day is None:
        return
    unit = st.radio("분석 단위", ["개별 지역", "광역권·합산"], horizontal=True, key="eprx_daily_unit")
    if unit == "개별 지역":
        label = st.radio("분석할 지역을 선택하세요.", list(EPRX_AREA_OPTIONS), horizontal=True, key="eprx_daily_area")
        selection = EPRX_AREA_OPTIONS[label]
        areas = [selection]
    else:
        label = st.radio("분석할 광역권·합산을 선택하세요.", list(AGGREGATE_REGION_GROUPS), horizontal=True, key="eprx_daily_group")
        selection, areas = label, list(AGGREGATE_REGION_GROUPS[label])
        st.caption(AGGREGATE_REGION_CAPTIONS[label])
    _quality(data, day, areas, EPRX_AREA_DISPLAY, "eprx")
    current = eprx_daily_kpis(data, day, selection)
    can_compare = comparable_days(data, day, areas, "eprx")
    previous = eprx_daily_kpis(data, pd.Timestamp(day) - pd.Timedelta(days=1), selection) if can_compare else {}
    metrics = ["평균 모집량 (MW)", "평균 입찰량 (MW)", "평균 낙찰량 (MW)", "입찰 대비 낙찰률 (%)"]
    labels = ["평균 모집량 (TSO별, MW)", "평균 입찰량 (전원 소재지별, MW)",
              "평균 낙찰량 (전원 소재지별, MW)", "입찰 대비 낙찰률 (전원 소재지별, %)"]
    values, changes = [], {}
    for index, metric in enumerate(metrics):
        value = current[metric]
        values.append("계산 불가" if pd.isna(value) else f"{value:.2%}" if index == 3 else f"{value:,.2f}")
        if can_compare and index < 3:
            changes[(labels[index], label)] = change_rate(value, previous[metric])
    st.subheader(f"{label} Daily 핵심지표")
    table_renderer(st, pd.DataFrame({label: values}, index=labels), change_rates=changes)
    st.caption(f"전일 대비 변화율 · 비교일: {pd.Timestamp(day) - pd.Timedelta(days=1):%Y-%m-%d}" if can_compare
               else "선택일 또는 전일 데이터 부족·거래제도 차이로 변화율 미제공")
    for column, title, axis in [("max_price", "시간대별 최고 낙찰가격", price_unit),
                                ("award_rate", "시간대별 입찰 대비 낙찰률", "%")]:
        st.subheader(f"{label if len(areas) == 1 else '지역별'} {title}")
        st.plotly_chart(daily_chart(data, day, areas, EPRX_AREA_DISPLAY, column, axis, "eprx"), width="stretch")
    st.caption("선택일의 실제 시간대별 값입니다. 광역권 그래프는 구성 지역별 값을 표시합니다.")


def render_jepx_daily_analysis(data, spread_provider, area_names):
    st.subheader("JEPX Daily 분석")
    day = _date_selector(data, "jepx_daily_date")
    if day is None:
        return
    controls = st.columns(3)
    label = controls[0].selectbox("분석할 지역을 선택하세요.", list(JEPX_DETAIL_AREA_OPTIONS), key="jepx_daily_area")
    area = JEPX_DETAIL_AREA_OPTIONS[label]
    duration = controls[1].selectbox("ESS 운용시간", [1, 2, 4], index=1, format_func=lambda n: f"{n}시간", key="jepx_daily_duration")
    mode_label = controls[2].selectbox("계산방식", list(MODE_LABELS), key="jepx_daily_mode")
    mode = MODE_LABELS[mode_label]
    spreads = spread_provider(duration, mode)
    _quality(data, day, [area], area_names, "jepx")
    current = jepx_daily_kpis(data, spreads, day, area, duration, mode)
    can_compare = comparable_days(data, day, [area], "jepx")
    previous = jepx_daily_kpis(data, spreads, pd.Timestamp(day) - pd.Timedelta(days=1), area, duration, mode) if can_compare else {}
    rows = [("일 평균 전력가격 (엔/kWh)", "average_market_price"),
            ("일 최저 전력가격 (엔/kWh)", "minimum_market_price"),
            ("일 최고 전력가격 (엔/kWh)", "maximum_market_price"),
            ("평균 충전가격 (엔/kWh)", "average_charge_price"),
            ("평균 방전가격 (엔/kWh)", "average_discharge_price"),
            ("평균 ESS 스프레드 (엔/kWh)", "average_spread")]
    table = pd.DataFrame({label: [_fmt(current.get(key, float("nan"))) for _, key in rows]}, index=[name for name, _ in rows])
    table.loc["최대 스프레드 발생일", label] = f"{pd.Timestamp(day):%Y-%m-%d}" if pd.notna(current.get("average_spread")) else "계산 불가"
    delta = current.get("average_spread", float("nan")) - previous.get("average_spread", float("nan"))
    table.loc["전일 대비 평균 스프레드 변화 (엔/kWh)", label] = f"{delta:+.2f}" if pd.notna(delta) else "계산 불가"
    st.subheader(f"{label} Daily 핵심지표")
    _render_metric_hierarchy_table(table)
    st.caption("전일 대비 변화는 기존 주간 지표와 동일하게 스프레드의 가격 차이입니다." if can_compare
               else "선택일 또는 전일 데이터 부족으로 전일 변화 미제공")
    st.subheader(f"{label} 시간대별 현물가격")
    st.plotly_chart(daily_chart(data, day, [area], area_names, "price", "엔/kWh", "jepx"), width="stretch")
    st.caption("선택일의 실제 30분 가격입니다. 불완전 날짜의 ESS 스프레드는 계산에서 제외합니다.")
    detail = select_day(spreads, day)
    detail = detail.loc[detail.area.eq(area)]
    st.markdown("### 일별 ESS 스프레드 상세 데이터")
    st.dataframe(detail[["charge_start", "charge_end", "charge_average_price", "discharge_start", "discharge_end",
                         "discharge_average_price", "spread", "completeness_flag", "warning_message"]].rename(columns={
        "charge_start": "충전 시작", "charge_end": "충전 종료", "charge_average_price": "충전 평균가격 (엔/kWh)",
        "discharge_start": "방전 시작", "discharge_end": "방전 종료", "discharge_average_price": "방전 평균가격 (엔/kWh)",
        "spread": "스프레드 (엔/kWh)", "completeness_flag": "데이터 완전성", "warning_message": "경고 내용"}), hide_index=True, width="stretch")
    st.caption("ESS 스프레드는 배터리 효율, 수수료, 계통비용 및 열화비용을 반영하지 않은 이론적 가격 차이입니다.")
