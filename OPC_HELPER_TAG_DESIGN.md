# OPC 보조 태그 조건 기능 설계

## 1. 결정 요약

이 기능은 업로드한 전처리 대상 XLSX 데이터에 OPC 태그 값을 **임시 보조 컬럼(helper column)** 으로 붙여 조건/소팅에 활용하고, 최종 산출물 저장 시에는 helper 컬럼을 제거해 원본 데이터 컬럼 구조를 보존하는 기능이다.

배포 구조는 아래 두 경로를 모두 고려하되, **사내 포털 서버형을 1순위**로 둔다.

```text
1순위: 브라우저 UI -> 포털 backend -> OPC UA 조회/전처리
2순위: 브라우저 UI -> 로컬/VDI backend -> OPC UA 조회/전처리
```

두 경로 모두 같은 frontend와 같은 API 계약을 쓰도록 설계한다.

---

## 2. 목표와 비목표

### 목표

- 여러 사용자가 포털 웹 UI로 전처리 작업을 수행할 수 있게 한다.
- 사용자가 원본 XLSX 컬럼만으로도 조건을 설정할 수 있게 한다.
- 사용자가 원하는 OPC 태그를 선택해 보조 조건/소팅 기준으로 쓸 수 있게 한다.
- 태그가 많으므로 발전소/prefix별 인덱스로 분리해 빠르게 검색한다.
- OPC 조회는 선택한 태그와 업로드 데이터 시간 범위로 제한해 timeout 위험을 낮춘다.
- 최종 산출물에는 helper OPC 컬럼을 포함하지 않는다.
- 개인별 태그 즐겨찾기와 전처리 프리셋을 지원한다.
- 공용 즐겨찾기/공용 프리셋을 확장 가능하게 둔다.

### 비목표 / 보류

- OPC UA 서버에 값을 write하는 기능은 포함하지 않는다.
- 초기 MVP에서는 사용자 권한/승인 워크플로우까지 만들지 않는다.
- 초기 MVP에서는 모든 발전소 전체 태그를 한 번에 브라우저에 로드하지 않는다.
- 초기 MVP에서는 여러 사용자가 같은 세션을 공동 편집하는 기능은 만들지 않는다.

---

## 3. 배포 아키텍처

### 3.1 포털 서버형

```text
사용자 브라우저
  -> 사내 포털 frontend
  -> preprocessing backend API
  -> OPC UA 조회 코드 + 발전소별 tags index
  -> OPC UA server
```

서버는 사용자/세션 단위로 파일과 상태를 분리한다.

```text
runtime/
  tag_index/
    PJ1.json
    PJ2.json
    KY.json
    HN.json
    WR.json
    YJ.json
  shared/
    favorites/
    presets/
  users/
    {user_id}/
      favorites/
      presets/
  sessions/
    {session_id}/
      input.xlsx
      metadata.json
      helper_tags.json
      processed_preview.json
      output.xlsx
```

### 3.2 로컬/VDI 패키징형

포털 backend가 OPC망에 접근하지 못하는 경우 같은 frontend를 로컬 backend에 연결한다.

```text
same frontend
  -> portal backend
  -> local backend
```

로컬형은 PyInstaller 또는 유사한 방식으로 Python backend + HTML/assets + tags index를 묶는 것을 목표로 한다.

---

## 4. 참조/벤더링 대상

`/Users/mk/worksapces/RiMSproj_SD_Monitoring_System`에서 아래 기능을 참고한다. 런타임 import가 아니라 필요한 코드를 이 프로젝트로 복사/축약해 독립 실행 가능하게 만든다.

### 4.1 우선 참조

- `src/narae_rims_ax/utils_opcua.py`
  - 실제 값 조회가 검증된 함수군
  - `snapshot()`
  - `history_raw()`
  - `history_time_avg()`
  - `history_max()`
  - `history_min()`
  - `load_tags_table()`
  - `load_tag_map()`
  - `fulltagname_to_nodeid()`
- `src/narae_rims_ax/data/tags.CSV`
  - 전체 태그 목록
  - 현재 확인 기준: 약 109,027행 / 13MB

### 4.2 설계 참고

- `src/rims_sd_monitor/data_source/opcua_client.py`
  - `OpcUaClient.read_current_values()`
  - `OpcUaClient.fetch_raw()`
  - `OpcUaClient.fetch_twa()`
  - 긴 history 조회 시 boundary 조회를 1/5/10/30분으로 제한하는 구조
- `src/rims_sd_monitor/data_source/tag_map.py`
- `src/rims_sd_monitor/data_source/opcua_config.py`
- `src/rims_sd_monitor/live_collect_narae.py`
  - 실제 수집 예시

---

## 5. tags 인덱스 전략

전체 `tags.CSV`를 그대로 브라우저로 보내지 않는다. backend가 startup 또는 빌드 시점에 발전소별 검색 인덱스를 만든다.

| 표시명 | prefix 후보 | 현재 확인 태그 수 |
|---|---|---:|
| 파주 | `PJ1`, `PJ2` | `PJ1`: 8,667 / `PJ2`: 7,641 |
| 광양 | `KY` | 17,432 |
| 하남 | `HN` | 30,542 |
| 위례 | `WR` | 10,869 |
| 여주 | `YJ` | 9,656 |

추가 확인 필요:

- `H2` prefix가 18,171개 확인됨. 하남 계열인지 별도 사업장인지 확인 후 분류한다.
- `PJ` 단독 prefix는 현재 확인된 fulltagname prefix 기준 0개이며, 파주는 `PJ1`, `PJ2`로 다룬다.

인덱스 항목 예:

```json
{
  "fulltagname": "PJ2.2C.21MBY10CE901////XQ01",
  "plant": "PJ2",
  "sourcename": "2C",
  "tagname": "21MBY10CE901//XQ01",
  "utagid": 123456,
  "description": "21 GT ACTIVE POWER / ACTIVE POWER,FILTERED",
  "units": "MW"
}
```

검색 대상:

- `fulltagname`
- `tagname`
- `description`
- `units`

---

## 6. 사용자 흐름

### 6.1 원본 컬럼만 사용하는 흐름

```text
XLSX 업로드
  -> 원본 컬럼 조건 추가
  -> 전처리 실행
  -> 결과 저장
```

이 경우 OPC 조회는 발생하지 않는다.

### 6.2 OPC helper 태그를 추가하는 흐름

```text
XLSX 업로드
  -> 날짜/시간 컬럼 확인
  -> OPC 태그 조건 추가
  -> 발전소 선택
  -> prefix 선택
  -> 태그 검색
  -> 태그 선택
  -> 조회 실행
  -> helper 컬럼 우측 추가
  -> helper 컬럼으로 조건/소팅 설정
  -> 전처리 실행
  -> 저장 시 helper 컬럼 제거
```

---

## 7. UI 구성

### 7.1 조건 빌더

조건 row는 원본 컬럼과 OPC helper 태그를 동일한 조건 빌더에서 다룬다.

```text
[조건 대상] [컬럼/태그] [연산자] [값] [역할] [삭제]
```

예:

```text
원본 컬럼   AMBIENT_TEMP       >=       15      필터
원본 컬럼   FAN_CURRENT        range    30~50   필터
OPC 태그    21 GT ACTIVE POWER >        100     필터
OPC 태그    ST LOAD            asc      -       소팅
```

### 7.2 OPC 태그 선택 패널

```text
발전소: [파주 ▼]
prefix: [PJ1] [PJ2]
검색: [LOAD / CE901 / description]

검색 결과
☆ PJ2.2C.21MBY10CE901////XQ01   21 GT ACTIVE POWER
☆ PJ2.2C.22MBY10CE901////XQ01   22 GT ACTIVE POWER
☆ PJ2.2C.20MKA01CE903////XQ01   ST LOAD

[선택 태그를 helper 조건에 추가]
[즐겨찾기에 추가]
```

### 7.3 즐겨찾기

즐겨찾기는 전처리 프리셋과 분리한다.

```text
즐겨찾기 = 태그 선택 편의
프리셋 = 실행 조건 묶음
```

즐겨찾기 UI:

```text
내 태그 세트
- 파주 2CC Load 확인용
- 여주 GT 주요 태그
- 광양 PHD 자주 쓰는 태그

[불러오기] [편집] [내보내기]
```

프리셋 UI:

```text
전처리 프리셋
- 파주 2CC Load 기준 전처리
- Load 기준 정렬 후 전처리
- Validation 생성 포함

[불러오기] [저장] [내보내기]
```

---

## 8. 데이터 모델

### 8.1 helper tag metadata

```json
{
  "id": "helper_opc_001",
  "source": "opc",
  "output": false,
  "role": "filter_sort_only",
  "fulltagname": "PJ2.2C.21MBY10CE901////XQ01",
  "display_name": "21 GT ACTIVE POWER",
  "description": "21 GT ACTIVE POWER / ACTIVE POWER,FILTERED",
  "units": "MW",
  "match_method": "previous_hold"
}
```

### 8.2 condition

```json
{
  "source": "helper_opc",
  "helper_id": "helper_opc_001",
  "operator": ">",
  "value": 100,
  "use_for": "filter"
}
```

원본 컬럼 조건:

```json
{
  "source": "original",
  "column": "AMBIENT_TEMP",
  "operator": ">=",
  "value": 15,
  "use_for": "filter"
}
```

### 8.3 favorite tag set

```json
{
  "version": 1,
  "id": "paju_2cc_load",
  "name": "파주 2CC Load 확인용",
  "scope": "personal",
  "plant": "paju",
  "prefixes": ["PJ2"],
  "tags": [
    {
      "fulltagname": "PJ2.2C.21MBY10CE901////XQ01",
      "display_name": "21 GT ACTIVE POWER",
      "description": "21 GT ACTIVE POWER / ACTIVE POWER,FILTERED",
      "units": "MW"
    }
  ],
  "created_at": "2026-04-13T10:00:00",
  "updated_at": "2026-04-13T10:00:00"
}
```

### 8.4 preprocessing preset

```json
{
  "version": 2,
  "name": "파주 2CC Load 기준 전처리",
  "helper_tags": [
    {
      "id": "helper_opc_001",
      "fulltagname": "PJ2.2C.21MBY10CE901////XQ01",
      "display_name": "21 GT ACTIVE POWER",
      "output": false
    }
  ],
  "filters": [
    {
      "source": "original",
      "column": "AMBIENT_TEMP",
      "operator": ">=",
      "value": 15
    },
    {
      "source": "helper_opc",
      "helper_id": "helper_opc_001",
      "operator": ">",
      "value": 100
    }
  ],
  "sort": [
    {
      "source": "helper_opc",
      "helper_id": "helper_opc_001",
      "direction": "asc"
    }
  ]
}
```

---

## 9. API 초안

### 9.1 세션 생성

```http
POST /api/sessions
```

응답:

```json
{
  "session_id": "sess_20260413_abcdef",
  "user_id": "portal_user_id"
}
```

### 9.2 XLSX 업로드

```http
POST /api/sessions/{session_id}/upload
```

응답:

```json
{
  "ok": true,
  "columns": ["Date", "AMBIENT_TEMP", "FAN_CURRENT"],
  "date_column_candidates": ["Date"],
  "row_count": 100000
}
```

### 9.3 태그 검색

```http
GET /api/tags?plant=paju&prefix=PJ2&q=LOAD&limit=100
```

### 9.4 helper 태그 조회/부착

```http
POST /api/sessions/{session_id}/helper-tags/fetch
```

요청:

```json
{
  "date_column": "Date",
  "match_method": "previous_hold",
  "tags": ["PJ2.2C.21MBY10CE901////XQ01"],
  "limits": {
    "max_tags": 5,
    "chunk_minutes": 60,
    "boundary_minutes": [1, 5, 10, 30]
  }
}
```

응답:

```json
{
  "ok": true,
  "helper_tags": [
    {
      "id": "helper_opc_001",
      "fulltagname": "PJ2.2C.21MBY10CE901////XQ01",
      "display_name": "21 GT ACTIVE POWER",
      "non_null_count": 98234
    }
  ]
}
```

### 9.5 전처리 실행

```http
POST /api/sessions/{session_id}/process
```

요청:

```json
{
  "filters": [],
  "sort": [],
  "outlier": {"apply": true, "method": "2.5sigma"},
  "time": {"normalize": false, "realign": false}
}
```

### 9.6 결과 다운로드

```http
GET /api/sessions/{session_id}/download
```

서버는 다운로드 전 helper 컬럼을 제거한다.

---

## 10. OPC 조회 안전장치

- 선택된 태그만 조회한다.
- 한 번에 선택 가능한 태그 수를 제한한다. MVP 기본값: 5개, 최대값: 10개.
- 업로드 데이터의 시간 범위를 조회 범위로 사용한다.
- 기간이 길면 chunk로 나눈다. MVP 기본값: 60분 단위.
- boundary 조회는 1/5/10/30분으로 제한한다.
- 무제한 prefetch 금지.
- 조회 실패/timeout 태그는 helper 컬럼을 생성하되 결측률을 표시하고 조건 적용 전 경고한다.

---

## 11. MVP 구현 순서

1. 서버 세션 모델 추가
2. XLSX 업로드 API 추가
3. tags.CSV를 발전소 prefix별 JSON 인덱스로 변환하는 스크립트 추가
4. 태그 검색 API 추가
5. `narae_rims_ax/utils_opcua.py` 기반 OPC 조회 adapter 벤더링
6. helper 태그 fetch API 추가
7. frontend 조건 빌더에 원본 컬럼/OPC helper 조건 통합
8. 전처리 실행 시 helper 컬럼 사용, 저장 시 helper 컬럼 제거
9. 개인 즐겨찾기/프리셋 저장 추가
10. 공용 즐겨찾기/프리셋은 읽기 전용 seed로 추가

---

## 12. 검증 기준

- 원본 컬럼만으로 기존 전처리 흐름이 동작한다.
- OPC helper 태그 없이도 조건을 설정하고 실행할 수 있다.
- OPC helper 태그를 추가해 조건/소팅에 사용할 수 있다.
- 최종 다운로드 파일에는 helper 컬럼이 없다.
- 같은 사용자가 두 세션을 동시에 열어도 파일/조건/결과가 섞이지 않는다.
- 다른 사용자 간 즐겨찾기/프리셋이 섞이지 않는다.
- 공용 즐겨찾기는 여러 사용자가 읽을 수 있다.
- 태그 검색은 발전소 prefix별로 제한된다.
- 장구간 OPC 조회가 무제한 prefetch를 하지 않는다.

---

## 13. 현재 추가된 실행 골격

이번 설계 기준에 맞춰 아래 독립 실행 골격을 추가했다.

### 13.1 태그 인덱스 생성/검색

```bash
# RiMS tags.CSV에서 발전소 prefix별 JSONL 인덱스 생성
python3 -m preprocessing_portal.tag_index build \
  --tags-csv /path/to/tags.CSV \
  --output-dir opc_assets/tag_index

# 인덱스 검색 예시
python3 -m preprocessing_portal.tag_index search \
  --index-dir opc_assets/tag_index \
  --prefix PJ2 \
  --query CE901 \
  --limit 5
```

현재 저장소에는 아래 인덱스가 생성되어 있다.

```text
opc_assets/tag_index/PJ1.jsonl
opc_assets/tag_index/PJ2.jsonl
opc_assets/tag_index/KY.jsonl
opc_assets/tag_index/HN.jsonl
opc_assets/tag_index/WR.jsonl
opc_assets/tag_index/YJ.jsonl
opc_assets/tag_index/manifest.json
```

### 13.2 로컬/포털 backend skeleton

```bash
python3 -m preprocessing_portal.server \
  --host 127.0.0.1 \
  --port 8765 \
  --index-dir opc_assets/tag_index
```

확인 URL:

```text
http://127.0.0.1:8765/Preprocessing.html
http://127.0.0.1:8765/api/health
http://127.0.0.1:8765/api/tags?plant=paju&q=CE901&limit=5
```

### 13.3 VDI OPC 현재값 probe

VDI에서 `opcua` 패키지가 설치되어 있고 OPC망 접근이 가능할 때:

```bash
python3 -m preprocessing_portal.opc_adapter \
  --index-dir opc_assets/tag_index \
  --current \
  --tag "PJ2.2C.21MBY10CE901////XQ91"
```

이 명령은 저장소 내부 tag index에서 `utagid`를 찾고 `ns=<namespace>;i=<utagid>` NodeId로 현재값을 조회한다.

### 13.4 현재 UI 연결 상태

`Preprocessing.html`에는 현재 아래 흐름이 연결되어 있다.

```text
XLSX 업로드
  -> OPC 보조 태그 패널
  -> 발전소/prefix 검색
  -> 태그 선택
  -> /api/opc/helper-values 호출
  -> __helper__ 컬럼을 원본 데이터 우측에 부착
  -> 필터 dropdown/table sort에서 helper 컬럼 사용
  -> XLSX/CSV export 시 __helper__ 컬럼 제외
```

주의:

- 현재 즐겨찾기는 브라우저 `localStorage` 기반 임시 구현이다. 포털 다중 사용자용 개인/공용 즐겨찾기 저장 API는 다음 단계에서 서버 저장소로 이전한다.
- 현재 전처리 계산은 브라우저에서 수행된다. 포털 서버가 파일을 직접 처리해야 하는 요구가 확정되면 `/api/sessions` 기반 서버 처리로 확장한다.
