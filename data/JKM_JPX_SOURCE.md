# JKM 연동가격(JPX) 출처 및 갱신

- 공식 최신 정산가격: https://www.jpx.co.jp/markets/derivatives/special-quotation/
- 공식 과거 가격 PDF: https://www.jpx.co.jp/markets/derivatives/special-quotation/mklp7700000028jz-att/sq_com_his.pdf

`jkm_prices_jpx_2026.csv`의 `settlement_price_yen_mmbtu`는 공식 PDF의
`LNG (Platts JKM)` 최종정산가격이며 단위는 엔/MMBtu입니다. 현물 JKM이 아닌
Platts JKM을 기초로 한 JPX 선물 최종정산가격이므로 앱에는 `JKM 연동가격(JPX)`으로 표시합니다.

계약월과 JKM 평가기간은 다릅니다. 계약월 M의 평가기간은 M-2월 16일부터 M-1월 15일까지이며,
그래프는 평가기간 종료월(`comparison_month`)을 기준으로 표시합니다.

## 자동화 제한과 수동 반영

JPX 이용조건은 허가 없이 사이트 정보의 수집, 2차 이용, 재배포를 금지합니다. 따라서 이 저장소의
GitHub Actions는 JPX PDF를 내려받거나 가격을 자동 추출하지 않습니다. 매월 18일과 23일 09:00 JST에
실행되는 `jpx-jkm-review-reminder.yml`은 수동 검토 알림만 남깁니다.

권한이 있는 절차로 확보한 입력 CSV는 기존과 동일한 다섯 열을 사용해야 합니다.

```text
contract_month,evaluation_start,evaluation_end,comparison_month,settlement_price_yen_mmbtu
```

다음 명령은 기간·단위·계약월 중복을 검증해 새 계약월만 병합합니다. 같은 계약월의 가격이 달라지면
기본적으로 실패하며, 공식 정정이 확인된 경우에만 `--allow-corrections`를 사용합니다. 이 경우 변경 이력은
`jkm_prices_jpx_corrections.csv`에, 확인 출처와 일자는 `jkm_prices_jpx_metadata.csv`에 기록됩니다.

```text
python -m utils.jkm_jpx_manual_update --input approved_jkm.csv --source-url https://www.jpx.co.jp/markets/derivatives/special-quotation/ --verified-at YYYY-MM-DD
```
