# 시계열 데이터 전처리 프로그램

Windows PC에서 Excel/CSV 파일의 시계열 데이터를 전처리하는 Python GUI 프로그램입니다.

## 주요 기능

- 📁 **파일 로드**: Excel (.xlsx, .xls) 및 CSV 파일 지원
- 🔧 **다중 조건 필터링**: AND 조건으로 여러 필터 조합
  - 연산자: `>=`, `<=`, `>`, `<`, `=`, `!=`, `범위(range)`
- 📊 **이상값 처리**: 
  - 2σ (95.4%), 2.5σ (98.8%), 3σ (99.7%), IQR 방식
  - 해당 값만 NaN으로 변경 또는 행 전체 삭제 선택
- 📈 **정규화**: Z-Score 또는 Min-Max 정규화 (선택사항)
- 💾 **저장**: 원본 양식 유지, 처리된 데이터만 저장

## 설치 방법

### 1. Python 설치 (3.8 이상)
https://www.python.org/downloads/ 에서 Python 다운로드 및 설치

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

## 실행 방법

### GUI 실행
```bash
python gui_app.py
```

### 명령줄 테스트
```bash
python data_preprocessor.py
```

## 사용 방법

1. **파일 불러오기**: "파일 불러오기" 버튼으로 Excel/CSV 파일 선택
2. **필터 추가**: "+ 필터 추가" 버튼으로 조건 설정
   - 예: `AMBIENT_TEMP >= 15` AND `FAN_CURRENT 범위 30~50`
3. **이상값 처리**: 방법(2.5σ 권장) 및 처리 방식 선택
4. **전처리 실행**: "🚀 전처리 실행" 버튼 클릭
5. **저장**: "💾 결과 저장" 버튼으로 결과 저장

## Windows .exe 파일 만들기

PyInstaller를 사용하여 독립 실행 파일을 만들 수 있습니다:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "DataPreprocessor" gui_app.py
```

생성된 파일: `dist/DataPreprocessor.exe`

## 파일 구조

```
Preprocessing/
├── data_preprocessor.py  # 데이터 처리 핵심 로직
├── gui_app.py            # GUI 애플리케이션
├── requirements.txt      # 의존성 목록
└── README.md             # 이 파일
```

## 예시 데이터 형식

```csv
Date,AMBIENT_TEMP,FAN_CURRENT,GEARBOX_OIL_TEMP
2025-11-27 00:00:00,18.5,45.2,65.3
2025-11-27 01:00:00,19.1,42.8,64.1
...
```

## 라이선스

MIT License
