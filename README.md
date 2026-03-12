# 시계열 데이터 전처리 프로그램

Windows PC에서 Excel/CSV 파일의 시계열 데이터를 전처리하는 Python GUI 프로그램입니다.

## 🚀 빠른 시작 (Windows)

**Python 설치 없이 바로 사용하기:**

1. [Releases](https://github.com/lee-minki/data-preprocessing-tool/releases) 페이지에서 최신 버전의 `DataPreprocessor.exe` 다운로드
2. 다운로드한 exe 파일 실행
3. 바로 사용 가능!

> ⚠️ Windows Defender에서 경고가 뜰 수 있습니다. "추가 정보" → "실행"을 클릭하세요.

---

## 주요 기능

- 📁 **파일 로드**: Excel (.xlsx, .xls) 및 CSV 파일 지원
- 🔧 **다중 조건 필터링**: AND 조건으로 여러 필터 조합
  - 연산자: `>=`, `<=`, `>`, `<`, `=`, `!=`, `범위(range)`
- 📊 **이상값 처리**: 
  - 2σ (95.4%), 2.5σ (98.8%), 3σ (99.7%), IQR 방식
  - 이상값 포함 행 전체 삭제
- 📈 **정규화**: Z-Score 또는 Min-Max 정규화 (선택사항)
- 🧪 **Validation 데이터 생성**:
  - `*_prepro.xlsx`
  - `*_prepro_with_valid.xlsx`
  - `*_valid.xlsx`
- ⏳ **진행률 표시**: 대용량 데이터(20만행+) 처리 시 진행 상황 표시
- 💾 **저장**: 원본 양식 유지, 처리된 데이터만 저장

---

## 개발자용 설치 방법

### 1. Python 설치 (3.8 이상)
https://www.python.org/downloads/ 에서 Python 다운로드 및 설치

### 2. 저장소 클론
```bash
git clone https://github.com/lee-minki/data-preprocessing-tool.git
cd data-preprocessing-tool
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 실행
```bash
python gui_app.py
```

---

## 사용 방법

1. **파일 불러오기**: "파일 불러오기" 버튼으로 Excel/CSV 파일 선택
2. **필터 추가**: "+ 필터 추가" 버튼으로 조건 설정
   - 예: `AMBIENT_TEMP >= 15` AND `FAN_CURRENT 범위 30~50`
3. **이상값 처리**: 방법(2.5σ 권장) 선택
4. **전처리 실행**: "🚀 전처리 실행" 버튼 클릭
5. **저장**: "💾 결과 저장" 버튼으로 결과 저장

---

## 로컬에서 EXE 빌드하기

```bash
python -m pip install -r requirements.txt
python -m pip install -r build_requirements.txt
pyinstaller --noconfirm --clean DataPreprocessor_windows.spec
```

생성된 파일: `dist/DataPreprocessor_v1.7.0.exe`

Windows에서는 아래 배치 파일로도 빌드할 수 있습니다.

```bat
build_windows_exe.bat
```

---

## 파일 구조

```
data-preprocessing-tool/
├── .github/
│   └── workflows/
│       └── build.yml         # GitHub Actions 자동 빌드
├── data_preprocessor.py      # 데이터 처리 핵심 로직
├── gui_app.py                # GUI 애플리케이션
├── requirements.txt          # 의존성 목록
└── README.md                 # 이 파일
```

---

## 예시 데이터 형식

```csv
Date,AMBIENT_TEMP,FAN_CURRENT,GEARBOX_OIL_TEMP
2025-11-27 00:00:00,18.5,45.2,65.3
2025-11-27 01:00:00,19.1,42.8,64.1
...
```

---

## 라이선스

MIT License
