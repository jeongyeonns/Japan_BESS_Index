"""Standalone dashboard. Existing market calculation engines are unchanged."""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from utils.jepx_areas import JEPX_AREA_DISPLAY, JEPX_DETAIL_AREAS
from utils.jepx_index import calculate_week_index
from utils.jepx_loader import find_jepx_files, load_all_jepx_data
from utils.eprx_loader import find_eprx_files, load_all_eprx_data
from utils.eprx_index import calculate_eprx_week_index
from utils.eprx_periods import expected_period_count

BASE = Path(__file__).resolve().parent
DATA_DIRECTORY = BASE / "data/jepx/raw"
EPRX_DIRECTORY = BASE / "data/eprx"


@st.cache_data
def load_data(signatures):
    return load_all_jepx_data(DATA_DIRECTORY)


@st.cache_data
def load_eprx_data(signatures):
    return load_all_eprx_data(EPRX_DIRECTORY)


def money(value):
    return "계산 불가" if pd.isna(value) else f"{value / 10000:,.1f}만 엔"


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
            daily, summary = calculate_eprx_week_index(subset, week, area)
            for row in summary.to_dict("records"):
                rows.append(dict(week=week, series=f"{row['scenario']}코마", value=row["annual_index"],
                                 valid_days=row["valid_days"], complete_days=row["complete_days"],
                                 average_price=row["average_price"], used_periods=row["used_periods"]))
        details.append(daily.assign(week=week))
    result = pd.DataFrame(rows)
    result["week_end"] = result.week + pd.Timedelta(days=6)
    result["quality"] = result.apply(lambda r: "계산 불가" if pd.isna(r.value) else "완전" if r.complete_days == 7 else "불완전", axis=1)
    return result, pd.concat(details, ignore_index=True)


def trend(history, selected_week, key):
    is_jepx = key == "JEPX_trend"
    chart_data = history.sort_values(["series", "week"]).copy()
    # Split paths at missing weeks instead of visually bridging absent values.
    chart_data["segment"] = chart_data.groupby("series")["value"].transform(lambda s: s.isna().cumsum()).astype(str)
    line = alt.Chart(chart_data).mark_line(point=True).encode(
        x=alt.X("week:T", title="주차 시작일 (월요일)", **({"axis": alt.Axis(format="%-m/%-d")} if is_jepx else {})),
        y=alt.Y("value:Q", title="만 엔/MW/년" if is_jepx else "엔/MW/년",
                axis=alt.Axis(labelExpr="format(datum.value / 10000, ',.0f')") if is_jepx else alt.Axis(format=",")),
        color=alt.Color("series:N", title="지표", scale=alt.Scale(scheme="tableau10"),
                        **({"legend": alt.Legend(labelExpr="datum.label === 'TB2' ? '2시간형 (TB2)' : '4시간형 (TB4)'")} if is_jepx else {})), detail="segment:N",
        tooltip=[alt.Tooltip("week:T", title="시작일", format="%Y-%m-%d"),
                 alt.Tooltip("week_end:T", title="종료일", format="%Y-%m-%d"),
                 alt.Tooltip("series:N", title="지표"), alt.Tooltip("value:Q", title="엔/MW/년", format=",.2f"),
                 alt.Tooltip("valid_days:Q", title="집계 일수 / 7"),
                 alt.Tooltip("complete_days:Q", title="완전일 / 7"), alt.Tooltip("quality:N", title="완전성")])
    rule = alt.Chart(pd.DataFrame({"week": [selected_week]})).mark_rule(color="#94a3b8", strokeDash=[4, 4]).encode(x="week:T")
    st.caption("선택 주차는 점선이며, 정확한 금액과 데이터 집계 일수는 툴팁에서 확인할 수 있습니다." if is_jepx else "주차별 연환산 Index · 선택 주차는 점선 · 완전성은 툴팁에서 확인")
    chart = (line + rule).properties(height=280)
    if is_jepx:
        chart = chart.properties(title="주차별 차익거래 수익기회")
    st.altair_chart(chart, width="stretch", key=key)


def jepx_card(row, previous):
    label = f"{row.series[-1]}시간형 차익거래 Index ({row.series})"
    exact = "계산 가능한 데이터가 없습니다." if pd.isna(row.value) else f"{row.value:,.2f} 엔/MW/년"
    st.metric(label, money(row.value), delta=change(row.value, previous), help=exact)
    st.caption("엔/MW/년")
    st.divider()
    spread = "—" if pd.isna(row.average_price) else f"{row.average_price:,.2f}엔/kWh"
    st.html(f"""<div style="display:grid;grid-template-columns:1fr auto;gap:0.5rem 1rem;font-size:0.95rem;">
        <span>주간 평균 스프레드</span><span style="text-align:right;font-variant-numeric:tabular-nums;">{spread}</span>
        <span>데이터 집계</span><span style="text-align:right;font-variant-numeric:tabular-nums;">{row.valid_days}/7일</span>
        </div>""")


def eprx_quality(data, week, area):
    selected = data.loc[data.area.eq(area) & data.delivery_date.between(week, week + pd.Timedelta(days=6))]
    rows = []
    for day in pd.date_range(week, periods=7):
        g = selected.loc[selected.delivery_date.eq(day)]
        rows.append({"날짜": day, "시간 단위": "30분" if expected_period_count(day) == 48 else "3시간 (계산 제외)", "고유 코마 수": g.period_no.nunique(),
                     "중복 코마 행 (통합 후)": int(g.period_no.duplicated(keep=False).sum()),
                     "낙찰량 양수·0엔": int((g.awarded_volume.gt(0) & g.max_price.eq(0)).sum()),
                     "낙찰량 0": int(g.awarded_volume.eq(0).sum()),
                     "가격 결측": int(g.max_price.isna().sum()), "낙찰량 미확인": int(g.awarded_volume.isna().sum())})
    return pd.DataFrame(rows)


def methodology():
    with st.expander("계산방법 및 유의사항"):
        st.markdown("**JEPX** · 인접 30분 가격을 1시간 평균으로 변환한 뒤 상위·하위 2/4시간의 평균 차이를 계산합니다. 주간 평균 TB2·TB4 스프레드 × 1,000 × 2/4 × 365로 1MW 기준 연환산합니다. 충방전 효율과 실제 운영 제약은 반영하지 않습니다.")
        st.markdown("**EPRX** · 전원 소재지역별 최고 낙찰가격을 기준으로 매일 가격이 높은 상위 N개 코마에 모두 낙찰된다고 가정한 이론적 상단 수익기회입니다. 실제 ESS 낙찰수익이나 시장 평균수익을 의미하지 않습니다. 일별 선택 가격 합 × 1,000의 유효일 평균 × 365이며, 원자료 단위는 円/kW・30分이므로 0.5를 추가로 곱하지 않습니다.")
        st.markdown("**데이터** · JEPX는 48코마가 모두 유효한 날, EPRX는 유효 코마가 N개 이상인 날만 계산합니다. EPRX의 2026-03-14 이전 3시간 블록은 변환하지 않습니다. 온라인·오프라인은 원자료에 구분이 없어 분리할 수 없습니다. 낙찰량 0은 미낙찰로 제외하고, 낙찰량 양수의 0엔 가격은 사용합니다. 가격·낙찰량이 결측이면 미낙찰 여부를 확정할 수 없습니다.")
        st.markdown("**공통** · 선택 주차의 가격 수준이 1년간 유지된다고 가정한 연환산 값입니다. JEPX와 EPRX 지표를 단순 합산하여 실제 ESS 총수익으로 해석해서는 안 됩니다. 결측은 0으로 대체하지 않습니다. 전주 대비는 정확히 7일 전 주차와 비교하며, 전주 값이 없거나 0이면 표시하지 않습니다. 불완전한 주차 간 비교에는 주의가 필요합니다.")


def main():
    st.set_page_config(page_title="Japan BESS Market Opportunity Index", layout="wide")
    st.title("Japan BESS Market Opportunity Index")
    st.caption("일본 전력시장 · JST 월~일 기준 · 모든 Index는 엔/MW/년")
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
    available = set().union(*(set(d.area) for d in sources.values()))
    areas = [a for a in JEPX_DETAIL_AREAS if a in available]
    if not areas:
        st.warning("지원 지역 데이터가 없습니다.")
        return
    area = controls[1].selectbox("분석 지역", areas, format_func=lambda a: JEPX_AREA_DISPLAY[a])
    st.caption(f"{JEPX_AREA_DISPLAY[area]} | {week:%Y-%m-%d} (월) ~ {week + pd.Timedelta(days=6):%Y-%m-%d} (일)")
    for market, title in (("JEPX", "차익거래 수익기회"), ("EPRX", "1차 조정력 수익기회")):
        st.divider()
        st.subheader(f"{market} — {title}")
        if market == "JEPX":
            st.markdown("하루 중 고가·저가 2시간 또는 4시간의 평균 스프레드를 기준으로 한 MW당 연간 차익거래 수익기회입니다.")
            with st.expander("JEPX 지표 설명"):
                st.markdown("하루 중 전력가격이 가장 높은 2시간 또는 4시간과 가장 낮은 2시간 또는 4시간의 평균 스프레드를 계산합니다. 선택한 주차의 평균 스프레드가 1년간 유지된다고 가정하여 MW당 연간 수익기회로 환산한 지표입니다.")
        if market not in sources:
            st.info(f"{market} 데이터가 없습니다.")
            continue
        data = sources[market]
        history, daily = weekly_results(data, market, area, first, last)
        current = history.loc[history.week.eq(week)]
        previous = history.loc[history.week.eq(week - pd.Timedelta(days=7))].set_index("series")
        if market == "EPRX":
            st.caption("전원 소재지역별 최고 낙찰가격 · 円/kW・30分 · 48코마는 24시간 참고 시나리오")
        for card, row in zip(st.columns(len(current)), current.itertuples()):
            with card.container(border=True):
                if market == "JEPX":
                    old = previous.loc[row.series, "value"] if row.series in previous.index else float("nan")
                    jepx_card(row, old)
                    continue
                label = f"{row.series} Index (엔/MW/년)" if market == "JEPX" else f"{row.series} · {int(row.series[:-2]) // 2}시간" + (" (참고용)" if row.series == "48코마" else "")
                old = previous.loc[row.series, "value"] if row.series in previous.index else float("nan")
                st.metric(label, money(row.value), delta=change(row.value, old) if market == "JEPX" else None)
                st.caption("— 엔/MW/년" if pd.isna(row.value) else f"{row.value:,.2f} 엔/MW/년")
                price_label = "주간 평균 스프레드" if market == "JEPX" else "선택 평균 최고 낙찰가격"
                unit = "엔/kWh" if market == "JEPX" else "엔/kW·30분"
                st.caption(f"{price_label}: " + ("—" if pd.isna(row.average_price) else f"{row.average_price:,.4f} {unit}"))
                st.caption(f"집계 {row.valid_days}/7일 · 완전일 {row.complete_days}/7일")
                if market == "EPRX":
                    st.caption(f"주간 사용 {int(row.used_periods)}코마")
        if current.value.isna().all():
            st.warning("선택 주차·지역에 계산 가능한 데이터가 없습니다. 결측은 0으로 표시하지 않습니다.")
        elif current.complete_days.lt(7).any():
            st.warning("불완전한 주간 데이터입니다. 유효일만 집계하며, EPRX는 일부 코마만 확보된 날도 N개 이상이면 계산합니다." if market == "EPRX" else "불완전한 주간 데이터입니다. 유효일만 집계하므로 전주와 비교 시 집계 일수를 확인하세요.")
        if market == "EPRX":
            st.info("최고 낙찰가격 기준 이론적 수익기회이며, 실제 ESS 낙찰수익을 의미하지 않습니다.")
            choices = st.multiselect("그래프 시나리오", current.series.tolist(), default=current.series.tolist())
            shown = current.loc[current.series.isin(choices)]
            bar = alt.Chart(shown).mark_bar(color="#537a96").encode(
                x=alt.X("series:N", title="시나리오", sort=current.series.tolist()),
                y=alt.Y("value:Q", title="엔/MW/년", axis=alt.Axis(format=",")),
                tooltip=[alt.Tooltip("series:N", title="시나리오"), alt.Tooltip("value:Q", title="엔/MW/년", format=",.2f"),
                         alt.Tooltip("average_price:Q", title="선택 평균가격 (엔/kW·30분)", format=".4f"), alt.Tooltip("valid_days:Q", title="집계 일수")])
            st.altair_chart(bar.properties(height=240), width="stretch")
            chart_history = history.loc[history.series.isin(choices)]
        else:
            chart_history = history
        trend(chart_history, week, f"{market}_trend")
        with st.expander(f"{market} 주간 수치·일별 검증"):
            st.dataframe(history.drop(columns="used_periods").rename(columns={"week": "주차 시작", "week_end": "주차 종료", "series": "지표", "value": "Index (엔/MW/년)", "valid_days": "집계 일수", "complete_days": "완전일 수", "average_price": "평균 스프레드 (엔/kWh)" if market == "JEPX" else "선택 평균가격 (엔/kW·30분)", "quality": "완전성"}), hide_index=True)
            if market == "EPRX":
                st.dataframe(eprx_quality(data, week, area), hide_index=True)
                st.caption("고유 코마·중복은 기존 로더 통합 후 기준입니다. 파일 간 중복 해소 내역은 아래 원자료 검증에서 확인하세요. 완전일은 48개 코마 모두 유효한 날입니다.")
            st.dataframe(daily.loc[daily.week.eq(week)].drop(columns="week").rename(columns={
                "delivery_date": "날짜", "date": "날짜", "tb2": "TB2 (엔/kWh)", "tb4": "TB4 (엔/kWh)",
                "valid": "유효 여부", "reason": "검증 결과", "scenario": "시나리오 코마", "observed_periods": "관측 코마",
                "valid_periods": "유효 코마", "missing_prices": "가격 결측", "no_award_periods": "낙찰량 0",
                "selected_periods": "사용 코마", "average_price": "선택 평균가격 (엔/kW·30분)",
                "daily_opportunity": "일간 기회 (엔/MW)", "complete_day": "48코마 유효"}), hide_index=True)
        with st.expander(f"{market} 원자료 검증·중복 해소 내역"):
            for diagnostic in diagnostics[market]:
                st.dataframe(diagnostic, hide_index=True)
    methodology()


if __name__ == "__main__":
    main()
