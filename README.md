# 우량채권 찾기 (bond.clisa.ai)

거래소에서 최근 5영업일 안에 거래된 공모 채권을 신용등급·세후 수익률·남은 기간으로 골라 보는 표.

- `docs/` : 공개 페이지 (GitHub Pages, 주소 bond.clisa.ai)
- `scripts/daily.py` : 매일 아침 자료 갱신 (GitHub Actions, 키는 저장소 Secret `DATA_GO_KR_KEY`)
- `data/issuer_ratings.json` : 발행사 신용등급표 (수동 관리, 신평사 공시로 확인)
- `data/missing_issuers.txt` : 거래됐으나 등급표에 없는 발행사 (갱신 때마다 자동 작성)

자료 출처: 금융위원회 채권시세정보·채권기본정보 (공공데이터포털, 공공누리 제4유형). 정보 제공이며 투자 권유가 아닙니다.
