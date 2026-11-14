# data/real — 실데이터 폴더 (저장소·제출물에 올리지 않음)

센터 PC 에서 아래 파일을 이 폴더에 둔 뒤 `DATA_MODE=real` 로 실행한다.

| 파일 | 내용 | 필요한 표준 컬럼 |
|---|---|---|
| `card.csv` | 제주데이터허브 605 · 관광지·상업지구 업종별 카드 데이터 (API) | area, ym, industry, amount |
| `bus.csv` | 제주데이터허브 614 · 일일 노선별 버스 이용자 정보 (API) | route_no, date, riders |
| `route_map.csv` | 노선–상권 연결표 (운영자가 작성) | route_no, area |
| `areas.csv` | 인접 지역 (선택) | area, neighbors(세미콜론 구분) |

원본 필드명이 표준 컬럼과 다르면 `../schema_map.json` 의 `columns` 만 고치면 된다.
카드 데이터는 센터 밖 반출이 제한될 수 있으므로 이 폴더는 `.gitignore` 로 제외돼 있다.
