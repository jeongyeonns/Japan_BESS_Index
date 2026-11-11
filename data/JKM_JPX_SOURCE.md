# JKM 연동가격(JPX) 출처

- 공식 최신정산가격 페이지: https://www.jpx.co.jp/markets/derivatives/special-quotation/
- 공식 과거 가격 PDF: https://www.jpx.co.jp/markets/derivatives/special-quotation/mklp7700000028jz-att/sq_com_his.pdf

CSV의 `settlement_price_yen_mmbtu`는 JPX PDF의 `LNG (Platts JKM)` 월별 최종정산가격으로, 단위는 엔/MMBtu입니다. 현물 JKM 자체가 아니라 Platts JKM을 기초로 한 JPX 선물 최종정산가격이므로 화면에는 `JKM 연동가격(JPX)`로 표시합니다.

계약월과 JKM 평가기간은 다릅니다. 계약월 M의 평가기간은 두 달 전 16일부터 한 달 전 15일까지로 기록했으며, 그래프 연결 월은 평가기간 종료월(`comparison_month`)입니다. 따라서 JKM 값은 달력월 평균이 아닙니다.

JPX PDF의 구조와 이용조건을 안정적으로 자동 추출할 수 있는지 확인되지 않아 현재는 공식 PDF를 확인해 CSV에 수동 반영합니다. 누락 가격은 추정하거나 이전 값으로 보충하지 않습니다.
