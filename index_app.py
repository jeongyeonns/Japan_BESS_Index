"""Standalone dashboard. Existing market calculation engines are unchanged."""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

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
LEGACY_LABEL = "3시간 블록"
MODERN_LABEL = "30분 코마"


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


def trend(history, selected_week, key):
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
        line = line.encode(strokeDash=alt.StrokeDash("regime:N", title="거래제도"))
    rule = alt.Chart(pd.DataFrame({"week": [selected_week]})).mark_rule(color="#94a3b8", strokeDash=[4, 4]).encode(x="week:T")
    st.caption("선택 주차는 점선이며, 정확한 금액과 데이터 집계 일수는 툴팁에서 확인할 수 있습니다.")
    chart = (line + rule).properties(height=280)
    if is_jepx:
        chart = chart.properties(title="주차별 차익거래 수익기회")
    else:
        reform = alt.Chart(pd.DataFrame({"date": [EPRX_REFORM_DATE], "label": ["3/14 제도 변경"]})).encode(x="date:T")
        chart = (line + rule + reform.mark_rule(color="#a66a36", strokeDash=[6, 3]) + reform.mark_text(align="left", dx=5, dy=8, baseline="top", color="#a66a36").encode(y=alt.value(0), text="label:N")).properties(height=280, title="주차별 조정력 수익기회")
        st.caption("3/14부터 3시간 블록·주간 거래가 30분 코마·전일 거래로 변경된 자료입니다. 선은 제도별로 분리되어 있으며, 전후 차이는 가격과 제도 변경의 영향을 함께 포함한 값입니다.")
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


def eprx_card(row):
    hours = int(row.series[:-2]) // 2
    exact = "계산 가능한 데이터가 없습니다." if pd.isna(row.value) else f"{row.value:,.2f} 엔/MW/년"
    st.metric(f"{hours}시간 기준 조정력 Index", money(row.value), help=exact)
    st.caption("엔/MW/년")
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
    with st.expander("계산방법 및 유의사항"):
        st.markdown("**JEPX** · 인접 30분 가격을 1시간 평균으로 변환한 뒤 상위·하위 2/4시간의 평균 차이를 계산합니다. 주간 평균 TB2·TB4 스프레드 × 1,000 × 2/4 × 365로 1MW 기준 연환산합니다. 충방전 효율과 실제 운영 제약은 반영하지 않습니다.")
        st.markdown("**EPRX** · 전원 소재지역별 최고 낙찰가격을 기준으로 매일 가격이 높은 상위 N개 코마에 모두 낙찰된다고 가정한 이론적 상단 수익기회입니다. 실제 ESS 낙찰수익이나 시장 평균수익을 의미하지 않습니다. 일별 선택 가격 합 × 1,000의 유효일 평균 × 365이며, 원자료 단위는 円/kW・30分이므로 0.5를 추가로 곱하지 않습니다.")
        st.markdown("**데이터** · JEPX는 48코마가 모두 유효한 날, EPRX는 필요한 수의 유효 코마 또는 블록이 있는 날만 집계한 값입니다. 3/13 이전 EPRX는 상위 2·4·6·8개 3시간 블록의 가격 합 × 6 × 1,000을 일별로 계산한 별도 지표입니다. 3/9~3/15는 이전 5일과 이후 2일을 분리한 평균이며, 두 제도를 혼합한 평균은 제공하지 않습니다. 온라인·오프라인 구분은 원자료에 없는 정보입니다. 낙찰량 0과 결측은 제외 대상이며, 낙찰량 양수의 실제 0엔 가격은 유효한 값입니다.")
        st.markdown("EPRX는 공표된 최고 낙찰가격 기준이며, 상한가격 적용·사후 정산·페널티·수수료를 반영한 실제 정산액과는 다른 값입니다.")
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
                st.code("주간 평균 스프레드(엔/kWh) × 1,000kW × 거래시간(2시간 또는 4시간) × 365일", language=None)
                st.caption("계산방법 설명용 예시입니다. 2시간 기준 주간 평균 스프레드가 10엔/kWh라면 730만 엔/MW/년이며, 실제 선택 주차의 시장값은 아닙니다.")
        else:
            st.markdown("최고 낙찰가격이 높은 시간대에 하루 6·12·18·24시간 모두 낙찰된다고 가정한 연환산 수익기회입니다. 실제 낙찰시간을 보장하는 지표는 아닙니다.")
            with st.expander("EPRX 지표 설명"):
                st.markdown("하루 중 최고 낙찰가격이 높은 시간대부터 6시간, 12시간, 18시간 또는 24시간을 선택합니다. 선택한 시간대에 모두 낙찰된다고 가정하고, 해당 주차의 일평균 수익기회를 365일 기준으로 환산한 지표입니다.")
                st.code("30분 코마: 일별 상위 N개 최고 낙찰가격 합계 × 1,000kW → 해당 주차의 일평균 × 365일\n3시간 블록: 일별 상위 2·4·6·8개 최고 낙찰가격 합계 × 6코마 × 1,000kW → 제도별 일평균 × 365일", language=None)
                st.caption("계산방법 설명용 예시입니다. 모든 30분 낙찰가격이 5엔/kW·30분이고 하루 12코마(6시간)에 모두 낙찰된다면 2,190만 엔/MW/년이며, 실제 시장값은 아닙니다.")
                st.markdown("[3시간 블록·정산 근거: EPRX 2025년 규정 제29·46조](https://www.eprx.or.jp/j_information/docs/kitei211f_20250401.pdf) · [2026-03-14 제도 변경 안내](https://www.occto.or.jp/assets/iinkai/jukyuchousei/58/jukyu_shijyo_58_05.pdf)")
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
        if market == "EPRX":
            st.caption("전원 소재지역별 최고 낙찰가격 · 円/kW・30分 · 48코마는 24시간 참고 시나리오")
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
            st.info("최고 낙찰가격 기준 이론적 수익기회이며, 실제 ESS 낙찰수익을 의미하지 않습니다.")
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
        trend(chart_history, week, f"{market}_trend")
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
