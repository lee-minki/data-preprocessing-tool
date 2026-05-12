# 프리비전 모델링 준비 전처리 Control Room

프리비전 모델링 데이터 준비 과정에서 반복되던 Operation Condition 기반 선별, 엑셀 수작업 전처리, Validation/Simulation 구성, 2분 단위 시간축 보정을 하나의 흐름으로 정리한 전처리 도구입니다. 데스크톱 GUI와 함께 XLSX 업로드 중심의 웹 Control Room(`Preprocessing.html`)을 제공합니다.

현재 웹 Control Room은 단순히 브라우저 화면만 로컬에서 도는 구조가 아니라, 브라우저 UI + Frontend JS 로직 + 로컬/VDI Python backend + 산출물 저장까지 모두 로컬 자원을 사용하는 형태입니다. 특히 OPC helper 연동은 방화벽 제약 때문에 서버에서 직접 붙지 못하고, 로컬/VDI 환경에서만 동작합니다.

기본 실행 파일은 Windows용 `gui_app.py`(tkinter)이고, macOS에서는 `gui_app_mac.py`(PyQt5)를 사용합니다.

## 빠른 시작

### Windows 실행 파일 사용

1. [Releases](https://github.com/lee-minki/data-preprocessing-tool/releases)에서 최신 `DataPreprocessor_v<version>.exe` 다운로드
2. 실행 파일 실행
3. 데이터 파일을 불러와 전처리 진행

> Windows Defender 경고가 표시되면 `추가 정보 → 실행`으로 진행합니다.

### 소스에서 실행

```bash
python -m pip install -r requirements.txt
python gui_app.py
```

macOS:

```bash
python -m pip install -r requirements.txt
python gui_app_mac.py
```

## 주요 기능

- **파일 로드**: 데스크톱은 Excel(`.xlsx`) / CSV(`.csv`) 지원, 웹 Control Room은 XLSX 업로드 중심
- **CSV 인코딩 자동 감지**: UTF-8, CP949, EUC-KR 순으로 시도
- **다중 조건 필터링**: 숫자 컬럼 기준 AND 조건 결합
  - 연산자: `>=`, `<=`, `>`, `<`, `=`, `!=`, `range`
- **이상값 처리**: `2σ`, `2.5σ`, `3σ`, `IQR`
  - 이상값이 포함된 행은 전체 삭제
- **시간 처리**:
  - 시간 정규화(`normalize_timestamps`): 지정 간격 기준으로 시각 보정
  - 시간 재정렬(`realign_timestamps`): 지정 시작 시각부터 시간축 재생성
- **프리셋 관리**: 저장 / 불러오기 / 내보내기 / 가져오기 / 파일+프리셋 한번에 열기
- **트렌드 차트**: 최대 5개 컬럼 비교, 평균선/통계 표시
- **웹 자동 저장 산출물**:
  - `*_prepro_with_valid.xlsx` — 전처리 완료 데이터 + 정상 Validation 20%
  - `Simulation_Data_YYYYMMDD_HHMMSS.xlsx` — 정상 → 전환 → 이상 Alert 점검용 데이터
- **데스크톱 Validation 데이터 생성**:
  - `*_prepro.xlsx`
  - `*_prepro_with_valid.xlsx`
  - `*_valid.xlsx`
- **도움말/단축키**: F1 매뉴얼, Ctrl+O/Ctrl+S/Ctrl+P/Ctrl+T 지원

## 권장 작업 흐름

### 웹 Control Room

1. XLSX 파일 업로드
2. 우측 데이터 분석 카드에서 원본 추세와 분포, 시간축 상태 확인
3. 필요하면 OPC helper 태그로 Operation Condition 판단 기준 보완
4. 좌측에서 이상값 방식, 선제거 모드, 대상 컬럼, 필터, 시간 처리, Validation / Simulation 조건 설정
5. `🚀 전처리 실행 · 자동 저장`
6. 실행 영역의 `저장 파일 구성`과 로그에서 `_prepro_with_valid.xlsx` / `Simulation_Data_*.xlsx` 확인

메인 화면의 `사용 순서` 항목 또는 `인터랙티브 매뉴얼 시작` 버튼을 누르면 각 부위가 하이라이트되고, 왜 이 단계가 필요한지와 기존 절차 대비 어떤 부분이 자동화되었는지부터 실행·자동 저장·로그 재확인까지 순서대로 확인할 수 있습니다.

### 데스크톱 GUI

1. 파일 불러오기
2. 필터 / 이상값 / 시간 처리 옵션 설정
3. `🚀 전처리 실행`
4. 필요 시 `🧪 Validation 데이터 생성`
5. `💾 결과 저장`

## 개발 환경

- Python: **3.11 권장**
  - 저장소 내 주석은 3.8+로 되어 있지만, GitHub Actions 빌드는 Python 3.11을 사용합니다.
- 주요 의존성: `pandas`, `numpy`, `openpyxl`, `matplotlib`, `mplcursors`, `PyQt5`
  - `PyQt5`는 macOS GUI(`gui_app_mac.py`) 실행에 필요합니다.

## 실행 명령

```bash
# Windows GUI
python gui_app.py

# macOS GUI
python gui_app_mac.py

# 시간 정규화 스모크 테스트
python test_time_norm.py

# 정적 점검
python -m ruff check .
```

`test_time_norm.py`는 pandas 초 단위 빈도 표기를 `61s`로 사용해 FutureWarning 없이 실행됩니다.

## 로컬 빌드

### Windows 로컬 EXE

```bash
python -m pip install -r requirements.txt
python -m pip install -r build_requirements.txt
pyinstaller --noconfirm --clean DataPreprocessor_windows.spec
```

출력 파일:

```text
dist/DataPreprocessor_v1.7.0.exe
```

또는 Windows에서 배치 파일 사용:

```bat
build_windows_exe.bat
```

### GitHub Actions 빌드

`.github/workflows/build.yml`은 다음 조건에서 Windows EXE를 자동 빌드합니다.

- `v*` 형식 태그 push
- 수동 실행(`workflow_dispatch`)

CI 빌드 명령:

```bash
pyinstaller --noconfirm --clean DataPreprocessor_windows.spec
```

산출물은 GitHub Release와 artifact로 업로드됩니다.

### macOS 빌드

macOS 패키징용 spec 파일이 포함되어 있습니다.

- `DataPreprocessor.spec`
- `gui_app_mac.py`



### VDI 테스트용 zip 만들기

Finder로 프로젝트 전체를 압축하면 `.venv/bin/python*` 같은 macOS 가상환경 symlink 때문에 `Operation not permitted`가 날 수 있습니다. 반복 테스트용으로는 아래 스크립트를 사용하세요.

```bash
./make_vdi_package.command
```

또는 Finder에서 `make_vdi_package.command`를 더블클릭해도 됩니다. 이 스크립트는 git에 커밋된 파일만 zip으로 묶기 때문에 `.venv`, `.git`, `build`, `dist`, `.playwright-mcp` 같은 로컬 산출물을 자동으로 제외합니다. 결과물은 `vdi_packages/` 아래에 생성됩니다.

## 웹/포털 개발 미리보기

OPC helper tag 조건 기능은 포털 서버형과 로컬/VDI backend형을 같은 API 계약으로 가져가는 방향입니다. 다만 현재 OPC UA 연동은 방화벽 제약 때문에 서버에서 직접 붙지 못하고, 로컬/VDI backend에서만 동작합니다. 즉, 서버 배포 시에는 세션/업로드/전처리/다운로드는 포털 backend로 올리고, OPC helper는 로컬 sidecar 또는 local backend를 통한 하이브리드 구조로 분리하는 것이 현실적인 방향입니다.

구조 설명 문서:
- `docs/architecture-and-deployment.md`
- `docs/architecture-preview.html`

현재 추가된 최소 backend skeleton은 아래처럼 실행할 수 있습니다.

웹 UI 기준 주요 동작:

- 필터는 조건에 맞는 행만 남깁니다. 예: `= 1`은 1인 행만 남기고, `!= 1`은 1이 아닌 행만 남깁니다.
- OPC helper 태그는 업로드 XLSX의 좌측 첫 시간 컬럼에 맞춰 내부 helper 컬럼으로 붙고, 최종 저장 파일에는 포함되지 않습니다.
- 시간 재정렬 시작 시간은 2분 배수로 자동 보정됩니다. 예: `10:05:00` → `10:04:00`.
- 헤더가 비어 있는 열은 로드 시 제외되어 Simulation/다운로드 파일에 빈 헤더 열이 따라붙지 않습니다.
- 이상값 처리 대상 컬럼은 기본 해제 상태이며, 이상값 처리가 켜져 있으면 1개 이상 선택해야 전처리가 실행됩니다.
- 이상값 처리 대상 컬럼을 선택하면 Simulation 대상도 자동으로 같은 컬럼이 체크됩니다. 이후 Simulation 대상은 사용자가 직접 수정할 수 있습니다. 선제거 모드(MAD/반복 clipping)는 메인 이상값 처리 전 극단값이 기준을 오염시키지 않도록 먼저 정리하는 옵션입니다.

```bash
# 태그 검색/정적 파일 확인용 로컬 backend
python3 -m preprocessing_portal.server --host 127.0.0.1 --port 8765 --index-dir opc_assets/tag_index

# 브라우저에서 열기
# http://127.0.0.1:8765/Preprocessing.html

# 태그 검색 API 예시
# http://127.0.0.1:8765/api/tags?plant=paju&q=CE901&limit=5
```

VDI OPC 현재값 probe 예시:

```bash
python3 -m preprocessing_portal.opc_adapter --index-dir opc_assets/tag_index --current --tag "PJ2.2C.21MBY10CE901////XQ91"
```

## 파일 구조

```text
data-preprocessing-tool/
├── .github/workflows/build.yml      # Windows EXE 자동 빌드
├── data_preprocessor.py             # 전처리 핵심 로직
├── gui_app.py                       # Windows GUI (tkinter)
├── gui_app_mac.py                   # macOS GUI (PyQt5)
├── preset_manager.py                # 프리셋 저장/불러오기/내보내기
├── version.py                       # 버전/앱 정보
├── MANUAL.md                        # 데스크톱 GUI 사용자 매뉴얼
├── MANUAL.html                      # 번들 도움말 HTML
├── Preprocessing.html               # 최신 웹 UI 프로토타입
├── web_app.html                     # 레거시 단일 HTML 웹 프로토타입
├── CHANGELOG.md                     # 변경 이력
├── requirements.txt                 # 런타임 의존성
├── build_requirements.txt           # 빌드 의존성
├── DataPreprocessor_windows.spec    # Windows PyInstaller spec
├── DataPreprocessor.spec            # macOS PyInstaller spec
├── build_windows_exe.bat            # Windows 로컬 빌드 스크립트
├── test_time_norm.py                # 시간 정규화 테스트
├── sample_data.csv                  # 예제 입력 데이터
└── developer_info.example.json      # 개발자 정보 예시 파일
```

## 개발자 정보 설정

앱은 `developer_info.json`이 있으면 이를 우선 읽고, 없으면 `version.py` 기본값을 사용합니다.

권장 형식:

```json
{
  "name": "Your Name",
  "email": "your.email@example.com",
  "organization": "Your Organization",
  "github": "github.com/your-account/your-repo"
}
```

파일 위치:

- 프로젝트 루트의 `developer_info.json`
- 또는 실행 파일과 같은 디렉터리

## 예시 데이터 형식

```csv
Date,AMBIENT_TEMP,FAN_CURRENT,GEARBOX_OIL_TEMP
2025-11-27 00:00:00,18.5,45.2,65.3
2025-11-27 01:00:00,19.1,42.8,64.1
...
```

## 관련 문서

- 데스크톱 사용자 매뉴얼: `MANUAL.md`
- 번들 도움말 HTML: `MANUAL.html`
- 변경 이력: `CHANGELOG.md`
- 웹 전환 메모: `WEB_PLAN.md`
- OPC 보조 태그 조건 설계: `OPC_HELPER_TAG_DESIGN.md`
- 웹 리디자인 플랜/현황: `WEB_REDESIGN_PLAN.md`

## 라이선스

MIT License
