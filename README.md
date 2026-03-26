# 시계열 데이터 전처리 프로그램

Excel/CSV 형식의 시계열 데이터를 필터링, 이상값 처리, 정규화, 시간 보정, Validation 데이터 생성까지 한 번에 수행하는 데스크톱 GUI 도구입니다.

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

- **파일 로드**: Excel(`.xlsx`, `.xls`) / CSV(`.csv`) 지원
- **CSV 인코딩 자동 감지**: UTF-8, CP949, EUC-KR 순으로 시도
- **다중 조건 필터링**: 숫자 컬럼 기준 AND 조건 결합
  - 연산자: `>=`, `<=`, `>`, `<`, `=`, `!=`, `range`
- **이상값 처리**: `2σ`, `2.5σ`, `3σ`, `IQR`
  - 이상값이 포함된 행은 전체 삭제
- **정규화**: `Z-Score`, `Min-Max`
- **시간 처리**:
  - 시간 정규화(`normalize_timestamps`): 지정 간격 기준으로 시각 보정
  - 시간 재정렬(`realign_timestamps`): 지정 시작 시각부터 시간축 재생성
- **프리셋 관리**: 저장 / 불러오기 / 내보내기 / 가져오기 / 파일+프리셋 한번에 열기
- **트렌드 차트**: 최대 5개 컬럼 비교, 평균선/통계/정규화 표시
- **Validation 데이터 생성**:
  - `*_prepro.xlsx`
  - `*_prepro_with_valid.xlsx`
  - `*_valid.xlsx`
- **시뮬레이션 데이터 생성**: 정상 → 전환 → 비정상 구간 데이터 생성
- **도움말/단축키**: F1 매뉴얼, Ctrl+O/Ctrl+S/Ctrl+P/Ctrl+T 지원

## 권장 작업 흐름

1. 파일 불러오기
2. 필터 / 이상값 / 정규화 / 시간 처리 옵션 설정
3. `🚀 전처리 실행`
4. 필요 시 `🧪 Validation 데이터 생성`
5. `💾 결과 저장`

Validation 데이터 생성은 전처리 과정에서 제거된 행이 있어야 동작합니다.

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

# 시간 정규화 테스트
python test_time_norm.py
```

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

## 파일 구조

```text
data-preprocessing-tool/
├── .github/workflows/build.yml      # Windows EXE 자동 빌드
├── data_preprocessor.py             # 전처리 핵심 로직
├── gui_app.py                       # Windows GUI (tkinter)
├── gui_app_mac.py                   # macOS GUI (PyQt5)
├── preset_manager.py                # 프리셋 저장/불러오기/내보내기
├── version.py                       # 버전/앱 정보
├── MANUAL.md                        # 사용자 매뉴얼
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

- 사용자 매뉴얼: `MANUAL.md`
- 변경 이력: `CHANGELOG.md`

## 라이선스

MIT License
