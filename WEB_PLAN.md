# 웹 버전 전환 계획 메모

이 파일은 데스크톱 앱을 바로 대체하는 구현 문서가 아니라, 저장소에 있는 웹 UI 산출물의 현재 역할과 다음 개발 방향을 정리한 계획 메모입니다.

## 현재 상태

- `Preprocessing.html`이 최신 웹 UI 프로토타입입니다.
  - Excel 업로드(`.xlsx`), 필터, 이상값 처리, 시간 처리, 프리셋, 정상 Validation holdout, Simulation 다운로드, 차트/분포 비교 흐름이 들어 있습니다.
  - `assets/vendor/xlsx.full.min.js`, `assets/vendor/chart.umd.min.js`를 로컬 벤더 파일로 사용합니다.
- `web_app.html`은 이전 단일 HTML 프로토타입입니다.
  - CSV 중심 기본 전처리 흐름 확인용으로만 취급합니다.
  - 최신 기능 동기화 대상은 `Preprocessing.html`입니다.
- 데스크톱 앱의 최신 기본 흐름은 `gui_app.py`/`gui_app_mac.py`의 Validation 데이터 생성입니다.
  - 데스크톱 UI에는 별도 Simulation 생성 메뉴가 노출되어 있지 않습니다.
  - Simulation 관련 core 함수는 `data_preprocessor.py`에 남아 있으므로 웹/향후 기능 개발 시 재검토 대상입니다.

## 목표

1. 데스크톱 앱의 핵심 전처리 흐름을 웹에서도 재현
2. 발전운영팀원이 설치 없이 브라우저에서 기본 작업 수행 가능
3. 데스크톱 Validation 정책과 웹 Validation/Simulation 정책 차이를 명확히 분리
4. 운영 반영 전에는 데스크톱 core 로직과 웹 JS 로직의 수치 결과 정합성을 검증

## 우선순위

### 1단계 — 정합성 기준 고정
- 같은 샘플 데이터에 대해 필터/이상값/시간 처리 결과 행 수 비교
- 데스크톱 Validation 3종 산출물과 웹 Validation/Simulation 산출물의 역할 차이 문서화

### 2단계 — 웹 UI 안정화
- `Preprocessing.html` 기준으로 프리셋 import/export와 자동 저장 흐름 검증
- 대용량 데이터 처리 한계와 브라우저 메모리 안내 추가
- 차트/분포 비교 버튼 문구와 매뉴얼 문구 동기화

### 3단계 — 통합 여부 결정
- 데스크톱의 제거행 기반 Validation 생성 방식을 웹에도 이식할지 결정
- 웹의 정상 Validation holdout + Simulation 생성 방식을 데스크톱으로 되돌릴지 결정
- 최종 선택에 맞춰 README/MANUAL/MANUAL.html을 한 번 더 동기화

## 주의 사항

- `web_app.html`은 레거시로 보고 새 개발의 기준 파일로 쓰지 않습니다.
- `Preprocessing.html`은 현재 기능이 더 많지만 Python core와 완전한 1:1 포팅 상태라고 가정하지 않습니다.
- 운영 반영 전에는 반드시 동일 입력 데이터로 데스크톱/웹 결과를 비교해야 합니다.

## OPC 보조 태그 컬럼 기능 구상 (VDI 독립 실행)

상세 설계는 `OPC_HELPER_TAG_DESIGN.md`를 기준 문서로 사용합니다.

### 배경

- 최종 배포는 웹 UI가 목표지만, VDI망에서 OPC 값을 가져오려면 브라우저 단독 정적 HTML만으로는 한계가 있습니다.
- `RiMSproj_SD_Monitoring_System`을 런타임 패키지로 import하는 방식은 피하고, 필요한 OPC 조회 코드와 tags 데이터를 이 프로젝트 안에 벤더링/복사해 독립 실행 가능하게 구성합니다.
- 브라우저 UI는 태그 선택과 전처리 조작을 맡고, OPC 조회는 VDI 로컬 Python 백엔드/sidecar가 담당하는 구조가 안전합니다.

### 참조할 RiMS 파일

- `src/narae_rims_ax/utils_opcua.py`
  - 실제 값 조회가 검증된 기존 함수군: `snapshot`, `history_raw`, `history_time_avg`, `history_max`, `history_min`
  - robust tags CSV 로딩, `fulltagname -> utagid -> ns=<namespace>;i=<utagid>` 변환 포함
- `src/narae_rims_ax/data/tags.CSV`
  - 전체 태그 목록. 현재 약 109,027행 / 13MB 규모.
- `src/rims_sd_monitor/data_source/opcua_client.py`
  - `OpcUaClient.read_current_values`, `fetch_raw`, `fetch_twa` 형태의 얇은 클라이언트 래퍼
  - 긴 history 조회에서 장구간 prefetch를 피하고 boundary를 1/5/10/30분 창으로 제한하는 설계 참고
- `src/rims_sd_monitor/data_source/tag_map.py`, `opcua_config.py`
  - 태그 매핑/endpoint/namespace 설정 분리 참고

### 발전소별 태그 분할 초안

전체 tags 파일을 한 번에 브라우저에 올리기보다, 서버 시작 시 또는 빌드 시 발전소 prefix별로 분할한 인덱스를 만들고 필요한 것만 로드합니다.

| 표시명 | prefix 후보 | 확인된 태그 수(현재 tags.CSV 기준) |
|---|---|---:|
| 파주 | `PJ1`, `PJ2` | `PJ1`: 8,667 / `PJ2`: 7,641 |
| 광양 | `KY` | 17,432 |
| 하남 | `HN` | 30,542 |
| 위례 | `WR` | 10,869 |
| 여주 | `YJ` | 9,656 |

참고: `H2` prefix도 18,171개가 확인되므로 하남 계열인지 별도 구분인지 확인이 필요합니다.

### OPC 조회 안전장치

- 사용자가 선택한 보조 태그만 조회합니다. tags 전체 history를 요청하지 않습니다.
- 업로드 XLSX의 좌측 첫 시간 컬럼 범위를 기준으로 필요한 최소 구간만 조회합니다.
- 긴 구간은 chunk로 나눕니다. 기본값 후보: 30분~2시간 단위.
- 시작 직전 값 보정은 RiMS 쪽 설계처럼 긴 prefetch 대신 `start-1분`, `5분`, `10분`, `30분` 순서의 제한된 boundary 조회를 우선 적용합니다.
- 태그 수, 기간, 샘플 간격에 상한을 둬 timeout을 막습니다.

### 보조 컬럼 처리 원칙

- OPC에서 가져온 값은 좌측 첫 시간 컬럼에 맞춰 `__helper__` 메타를 가진 내부 임시 컬럼으로 붙입니다.
- 이 컬럼은 sorting/filter/preprocessing 기준으로만 사용합니다.
- 최종 저장 직전에는 모든 helper 컬럼을 삭제해 원본 데이터 행/열 구조를 유지합니다.
- UI에서는 helper 컬럼을 일반 데이터 컬럼과 시각적으로 구분하고, 최종 산출물에 포함되지 않는다는 안내를 표시합니다.

## 배포 형태: 포털 서버 우선 + 로컬 패키징 대안

### 1순위 — 사내 포털 서버 배포

- 기본 목표는 `Preprocessing.html` 기반 웹 UI를 사내 포털에서 여러 사용자가 접속해 쓰는 구조입니다.
- 이 경우 브라우저는 UI만 담당하고, 파일 업로드/OPC 조회/전처리 실행/결과 다운로드는 포털 서버의 backend API가 담당해야 합니다.
- 사용자별 작업 충돌을 막기 위해 서버는 `session_id`와 사용자 식별자를 기준으로 업로드 파일, 임시 helper 컬럼, 결과 파일, 즐겨찾기, 프리셋을 분리합니다.

권장 서버 저장 구조:

```text
runtime/
  tag_index/
    PJ1.json
    PJ2.json
    KY.json
    HN.json
    WR.json
    YJ.json
  users/
    {user_id}/
      favorites/
      presets/
  sessions/
    {session_id}/
      input.xlsx
      helper_tags.json
      processed_preview.json
      output.xlsx
```

핵심 원칙:

- 포털 로그인/SSO가 있으면 그 사용자 ID를 `user_id`로 사용합니다.
- 로그인 정보가 backend에 전달되지 않는 구조라면, 최소한 브라우저 세션별 `session_id`를 강하게 분리합니다.
- 업로드 파일과 결과 파일은 세션별 디렉터리에 저장하고, 일정 시간 후 자동 삭제합니다.
- 즐겨찾기/프리셋은 개인용과 공용을 분리합니다.

```text
개인 즐겨찾기: users/{user_id}/favorites/
개인 프리셋: users/{user_id}/presets/
공용 즐겨찾기: shared/favorites/
공용 프리셋: shared/presets/
```

### OPC 네트워크 전제 확인

포털 서버 방식에서 가장 중요한 전제는 포털 backend가 VDI/OPC UA 서버에 접근 가능한지입니다.

- 접근 가능: 포털 backend가 직접 OPC 조회 API를 제공하면 됩니다.
- 접근 불가: 포털 UI는 유지하되, VDI 내부에 별도 local collector/sidecar를 두거나 로컬 패키징 모드가 필요합니다.

### 2순위 — 로컬 PC/VDI 패키징 대안

포털 서버가 OPC망에 직접 접근하지 못하거나, 사용자가 VDI 안에서만 OPC 조회를 해야 하는 경우를 대비해 같은 UI/API 계약을 로컬 실행 패키지에서도 재사용합니다.

```text
same frontend
  -> portal backend  (서버 배포)
  -> local backend   (VDI/PC 패키징)
```

이렇게 하면 포털형과 로컬형을 별도 제품처럼 만들지 않고, backend base URL만 바꾸는 방식으로 유지할 수 있습니다.

### 다중 사용자 설계 체크리스트

- [ ] 업로드 파일은 사용자/세션별로 격리
- [ ] helper OPC 컬럼은 세션 메타로 저장하고 최종 산출물에서는 제거
- [ ] 태그 즐겨찾기는 개인/공용을 분리
- [ ] 전처리 프리셋은 개인/공용을 분리
- [ ] tags 인덱스는 발전소 prefix별로 분리 로딩
- [ ] OPC 조회는 선택된 태그와 업로드 시간 범위로 제한
- [ ] 오래된 session 작업 디렉터리는 자동 cleanup
- [ ] 같은 사용자가 여러 파일을 동시에 처리해도 충돌하지 않도록 `session_id` 기준 API 설계
