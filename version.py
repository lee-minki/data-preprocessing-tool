from collections.abc import Mapping
from typing import cast

# 버전 정보
__version__ = "1.7.0"
__version_info__ = (1, 7, 0)

# 앱 정보 (폐쇄망 환경용 - 모든 정보 내장)
APP_NAME = "σ 조기경보 시계열 데이터 전처리프로그램"
APP_SYMBOL = "σ"  # 시그마 (표준편차/통계 심볼)
APP_DESCRIPTION = "Excel/CSV 파일의 시계열 데이터 필터링, 이상값 처리, 시간 보정 도구"

# 개발자 정보 (기본값 - developer_info.json으로 덮어쓰기 가능)
DEVELOPER_INFO = {
    "name": "이민기",
    "email": "minki.lee@sk.com",
    "organization": "나래O&M",
    "github": "github.com/lee-minki/data-preprocessing-tool",
}

# 최근 패치노트 (앱 내 표시용)
CHANGELOG = """
## v1.7.0 (2026-03-12)
- Validation 데이터 자동 생성
- `*_prepro.xlsx`, `*_prepro_with_valid.xlsx`, `*_valid.xlsx` 자동 저장
- 선택 태그별 제거행 기반 / sigma 기반 synthetic validation 생성
- Validation 설정 프리셋 저장/복원

## v1.6.0 (2024-12-24)
- 시뮬레이션 데이터 생성 기능 추가
- ML 모델 테스트용 정상→비정상 전환 데이터
- 점진적 Gradient 보간

## v1.5.2 (2024-12-23)
- 파일명에 버전 표시 (DataPreprocessor_v1.5.2.exe)
- 윈도우 타이틀에 버전 표시

## v1.5.1 (2024-12-23)
- 다중 컬럼 트렌드 차트 (Ctrl+클릭)
- 인터랙티브 호버 커서 (컬럼명 + 값)
- 컬럼별 색상 구분

## v1.5.0 (2024-12-23)
- 트렌드 차트 기능 (분석 → 트렌드 차트)
- 자동 스케일, 평균선, 통계 표시

## v1.4.0 (2024-12-23)
- Mac 버전 (PyQt5) 추가

## v1.3.x (2024-12-23)
- 사용자 매뉴얼 (F1)
- 프로그램 정보 다이얼로그
- 프리셋 저장/불러오기

## v1.2.0 (2024-12-23)
- 시간 정규화 (2분 간격 스냅)

## v1.1.0 (2024-12-23)
- 도움말 툴팁, 동적 컬럼, 시간 재정렬

## v1.0.0 (2024-12-23)
- 최초 릴리스
"""

# 주요 기능 목록 (About 다이얼로그용)
FEATURES = [
    "📁 Excel/CSV 파일 로드",
    "🔧 다중 조건 필터링 (AND)",
    "📊 이상값 처리 (2σ, 2.5σ, 3σ, IQR)",
    "📈 트렌드 차트 (다중 컬럼, 인터랙티브)",
    "🕐 시간 정규화/재정렬",
    "🧪 Validation 데이터 자동 생성",
    "🧬 시뮬레이션 데이터 생성",
    "💾 프리셋 저장/불러오기",
    "⏳ 진행률 표시 (대용량 지원)",
]


def _normalize_developer_info(data: object) -> dict[str, str]:
    if not isinstance(data, Mapping):
        return DEVELOPER_INFO.copy()

    def to_string_key_dict(source: Mapping[object, object]) -> dict[str, object]:
        result: dict[str, object] = {}
        for raw_key, value in source.items():
            result[str(raw_key)] = value
        return result

    data_map = to_string_key_dict(cast(Mapping[object, object], data))
    nested = data_map.get("developer")
    source_map = (
        to_string_key_dict(cast(Mapping[object, object], nested))
        if isinstance(nested, Mapping)
        else data_map
    )

    def read_text(key: str) -> str:
        value = source_map.get(key)
        return value if isinstance(value, str) else ""

    normalized = {
        "name": read_text("name"),
        "email": read_text("email"),
        "organization": read_text("organization") or read_text("company"),
        "github": read_text("github"),
    }

    return {key: normalized[key] or DEVELOPER_INFO[key] for key in DEVELOPER_INFO}


def get_developer_info() -> dict[str, str]:
    """개발자 정보 반환 (외부 파일 우선, 없으면 기본값)"""
    import json
    from pathlib import Path

    # 외부 파일 확인
    for path in [
        Path(__file__).parent / "developer_info.json",
        Path.cwd() / "developer_info.json",
    ]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw_data = cast(object, json.load(f))
                    return _normalize_developer_info(raw_data)
            except (json.JSONDecodeError, OSError, KeyError):
                pass

    return DEVELOPER_INFO
