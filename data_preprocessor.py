"""
데이터 전처리 모듈 (Data Preprocessing Module)
- 시계열 데이터 로드, 필터링, 이상값 처리
- Date 형식 보존 및 시간 재정렬 기능
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from zipfile import BadZipFile


class DataPreprocessor:
    """시계열 데이터 전처리 클래스"""

    ZIP_SIGNATURE = b"PK\x03\x04"
    OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    # 처리 상수
    MAX_NUMERIC_COLUMNS = 30
    IQR_MULTIPLIER = 1.5
    MAX_VALIDATION_RATIO = 0.8
    MIN_VALIDATION_ROWS = 4
    DEFAULT_INTERVAL_MINUTES = 2
    LARGE_FILE_BYTES = 10 * 1024 * 1024
    LARGE_DATA_WARNING_ROWS = 100_000
    MAX_PREVIEW_COLUMNS = 30
    SIGMA_MAP = {
        "2sigma": 2.0,
        "2.5sigma": 2.5,
        "3sigma": 3.0,
    }
    SIGMA_DISPLAY = {
        "2sigma": "2σ (95.4%)",
        "2.5sigma": "2.5σ (98.8%)",
        "3sigma": "3σ (99.7%)",
        "iqr": "IQR",
    }

    # 용어 도움말
    HELP_TEXTS = {
        "2sigma": "2σ: 평균에서 2표준편차 밖의 값을 이상값으로 봅니다.\n장점: 기준이 단순하고 빠릅니다.\n단점: 실제 정상값도 같이 지울 수 있어 다소 보수적입니다.",
        "2.5sigma": "2.5σ: 평균에서 2.5표준편차 밖의 값을 이상값으로 봅니다.\n장점: 과하게 지우지 않으면서 튀는 값을 잘 잡습니다.\n단점: 분포가 많이 치우치면 기준이 덜 안정적일 수 있습니다.",
        "3sigma": "3σ: 평균에서 3표준편차 밖의 값만 이상값으로 봅니다.\n장점: 극단값 위주로 제거해 원본 보존이 쉽습니다.\n단점: 약한 이상은 남을 수 있습니다.",
        "iqr": "IQR: 가운데 50% 구간을 기준으로 너무 벗어난 값을 찾습니다.\n장점: 비대칭 데이터에도 비교적 강합니다.\n단점: 표본 수가 적으면 기준이 흔들릴 수 있습니다.",
        "outlier_apply": "이상값 처리를 켜면 숫자 컬럼에서 튀는 행을 제거합니다.\n장점: 모델 입력이 안정됩니다.\n단점: 실제 중요한 이벤트도 빠질 수 있습니다.",
        "outlier_drop": "이상값이 들어있는 행은 항상 전체 삭제합니다.\n장점: 한 행에 섞인 이상 패턴을 깔끔하게 제거합니다.\n단점: 같은 행의 다른 정상 값도 함께 사라집니다.",
        "time_normalize": "시간 정규화는 밀린 시간을 가장 가까운 간격으로 보정합니다.\n장점: 엑셀 자동채우기 오류를 빠르게 고칠 수 있습니다.\n단점: 원래 시간 오차 정보는 사라집니다.",
        "time_realign": "시간 재정렬은 남은 행에 새 시간축을 다시 붙입니다.\n장점: 학습/검증 구간을 일정 간격으로 맞추기 쉽습니다.\n단점: 원래 수집 시간과는 달라질 수 있습니다.",
        "validation_ratio": "Validation 비율은 전처리 데이터 길이 대비 검증 구간 길이입니다.\n장점: 솔루션에서 뒤 구간 드래그 기준을 맞추기 쉽습니다.\n단점: 너무 크게 잡으면 synthetic 데이터 비중이 커집니다.",
        "validation_removed": "제거행 기반 구간은 전처리에서 걸러진 실제 이상값을 재료로 씁니다.\n장점: 현장에서 나온 이상 패턴을 다시 검증에 넣을 수 있습니다.\n단점: 제거행이 적거나 편향되면 패턴이 단순해질 수 있습니다.",
        "validation_sigma": "표준편차 기반 구간은 평균과 표준편차를 기준으로 선형적으로 더 벗어난 값을 만듭니다.\n장점: 점진적으로 커지는 이상 추세를 보기 좋습니다.\n단점: 실제 현장 패턴과 완전히 같지는 않을 수 있습니다.",
        "validation_save": "생성 버튼을 누르면 원본 폴더에 전처리본, validation 포함본, validation 전용본을 함께 저장합니다.\n장점: 업로드용과 시뮬레이션용 파일을 한 번에 얻습니다.\n단점: 같은 이름 파일이 있으면 덮어쓰게 됩니다.",
    }

    def __init__(self):
        self.original_df: Optional[pd.DataFrame] = None
        self.processed_df: Optional[pd.DataFrame] = None
        self.columns: List[str] = []
        self.numeric_columns: List[str] = []
        self.date_column: Optional[str] = None
        self.original_date_format: Optional[str] = None  # 원본 날짜 형식 저장
        self.stats: Dict[str, Any] = {}
        self.removed_rows: List[pd.DataFrame] = []  # 제거된 행들 (시뮬레이션용)

    def reset_processing_state(self):
        """새 전처리 실행 전 상태를 초기화합니다."""
        self.removed_rows = []
        if self.original_df is not None:
            self.processed_df = self.original_df.copy()
            self.stats["original_rows"] = len(self.original_df)
            self.stats["columns"] = len(self.columns)
            self.stats["numeric_columns"] = len(self.numeric_columns)
            self.stats["filtered_rows"] = len(self.original_df)
            self.stats["filter_removed"] = 0
            self.stats["outliers_removed"] = 0
            self.stats["rows_after_outlier"] = len(self.original_df)

    def load_data(self, file_path: str) -> Tuple[bool, str]:
        """
        Excel 또는 CSV 파일을 로드하고 컬럼을 자동 감지합니다.

        Args:
            file_path: 파일 경로

        Returns:
            (성공 여부, 메시지)
        """
        try:
            path = Path(file_path)

            if path.suffix.lower() == ".xlsx":
                self.original_df = pd.read_excel(file_path, engine="openpyxl")
            elif path.suffix.lower() == ".csv":
                # 인코딩 자동 감지 시도
                try:
                    self.original_df = pd.read_csv(file_path, encoding="utf-8")
                except UnicodeDecodeError:
                    try:
                        self.original_df = pd.read_csv(file_path, encoding="cp949")
                    except UnicodeDecodeError:
                        self.original_df = pd.read_csv(file_path, encoding="euc-kr")
            else:
                return False, f"지원하지 않는 파일 형식입니다: {path.suffix}"

            self.processed_df = self.original_df.copy()
            self.removed_rows = []

            # Unnamed 컬럼 제거
            unnamed_cols = [
                col for col in self.original_df.columns if "Unnamed" in str(col)
            ]
            if unnamed_cols:
                self.original_df.drop(columns=unnamed_cols, inplace=True)
                self.processed_df.drop(columns=unnamed_cols, inplace=True)

            self.columns = list(self.original_df.columns)

            # 날짜 컬럼 자동 감지 (형식 보존)
            self._detect_date_column()

            # 숫자 컬럼 감지 (최대 30개)
            self._detect_numeric_columns()

            self.stats["original_rows"] = len(self.original_df)
            self.stats["columns"] = len(self.columns)
            self.stats["numeric_columns"] = len(self.numeric_columns)

            return (
                True,
                f"파일 로드 완료: {len(self.original_df)}행, {len(self.columns)}열",
            )

        except Exception as e:
            self.original_df = None
            self.processed_df = None
            self.columns = []
            self.numeric_columns = []
            self.date_column = None
            self.original_date_format = None
            return False, self._format_load_error(Path(file_path), e)

    def _read_file_signature(self, path: Path, size: int = 8) -> bytes:
        """파일 시그니처를 읽습니다."""
        try:
            with open(path, "rb") as f:
                return f.read(size)
        except OSError:
            return b""

    def _is_likely_protected_excel(self, path: Path, error_message: str) -> bool:
        """AIP/DRM 보호 또는 형식 불일치로 보이는 Excel 파일인지 추정합니다."""
        if path.suffix.lower() != ".xlsx":
            return False

        signature = self._read_file_signature(path)
        message = error_message.lower()

        # 보호되었거나 실제 형식이 다른 경우 xlsx(zip) 시그니처가 아닐 수 있습니다.
        if signature.startswith(self.OLE_SIGNATURE):
            return True

        protection_hints = [
            "not a zip file",
            "excel file format cannot be determined",
            "xlrd",
            "encrypted",
        ]
        return not signature.startswith(self.ZIP_SIGNATURE) and any(
            hint in message for hint in protection_hints
        )

    def _format_load_error(self, path: Path, error: Exception) -> str:
        """사용자에게 보여줄 파일 로드 오류 메시지를 생성합니다."""
        raw_message = str(error)
        suffix = path.suffix.lower()

        if self._is_likely_protected_excel(path, raw_message):
            return (
                "파일 로드 실패: 문서보안(AIP/DRM)이 적용되었거나 보안 해제가 끝나지 않은 Excel 파일로 보입니다.\n"
                "파일 탐색기에서 대상 파일을 우클릭한 뒤 '문서보안 해제'를 완료한 후 다시 시도해주세요.\n"
                "보안 해제 후에도 동일하면 파일 확장자(.xlsx)와 실제 파일 형식을 확인해주세요.\n"
                f"원본 오류: {raw_message}"
            )

        if suffix == ".xlsx" and isinstance(error, BadZipFile):
            return (
                "파일 로드 실패: Excel 파일 형식이 올바르지 않습니다.\n"
                "문서보안 해제가 필요한 파일이거나 확장자와 실제 파일 형식이 다를 수 있습니다.\n"
                "파일 탐색기에서 '문서보안 해제' 후 다시 시도해주세요.\n"
                f"원본 오류: {raw_message}"
            )

        return f"파일 로드 실패: {raw_message}"

    def _detect_date_column(self):
        """날짜 컬럼을 자동 감지합니다. 원본 형식을 보존합니다."""
        date_keywords = ["date", "time", "datetime", "날짜", "시간", "timestamp"]

        for col in self.columns:
            if any(keyword in col.lower() for keyword in date_keywords):
                self.date_column = col

                # 원본 형식 샘플 저장 (첫 번째 유효한 값)
                sample_value = (
                    self.original_df[col].dropna().iloc[0]
                    if len(self.original_df[col].dropna()) > 0
                    else None
                )
                if sample_value is not None:
                    self.original_date_format = str(sample_value)

                # 날짜 형식으로 변환 시도 (내부 처리용)
                try:
                    self.original_df[col] = pd.to_datetime(self.original_df[col])
                    self.processed_df[col] = pd.to_datetime(self.processed_df[col])
                except (ValueError, TypeError):
                    pass
                break

    def _detect_numeric_columns(self):
        """숫자 컬럼을 감지합니다. 최대 30개까지 지원. Unnamed 컬럼 제외."""
        self.numeric_columns = []
        for col in self.columns:
            # Unnamed 컬럼과 날짜 컬럼 제외
            if col != self.date_column and "Unnamed" not in str(col):
                if pd.api.types.is_numeric_dtype(self.original_df[col]):
                    self.numeric_columns.append(col)
                    if len(self.numeric_columns) >= self.MAX_NUMERIC_COLUMNS:
                        break

    def get_column_stats(self, column: str) -> Dict[str, float]:
        """특정 컬럼의 통계 정보를 반환합니다."""
        if column not in self.numeric_columns:
            return {}

        data = self.processed_df[column].dropna()

        return {
            "count": len(data),
            "mean": data.mean(),
            "std": data.std(),
            "min": data.min(),
            "max": data.max(),
            "q1": data.quantile(0.25),
            "median": data.median(),
            "q3": data.quantile(0.75),
        }

    @classmethod
    def get_help_text(cls, key: str) -> str:
        """용어에 대한 도움말 반환"""
        return cls.HELP_TEXTS.get(key, "도움말이 없습니다.")

    def apply_filters(self, filters: List[Dict]) -> Tuple[bool, str]:
        """
        다중 조건으로 데이터를 필터링합니다 (AND 조건).

        Args:
            filters: 필터 조건 목록
                [
                    {'column': 'AMBIENT_TEMP', 'operator': '>=', 'value': 15},
                    {'column': 'FAN_CURRENT', 'operator': 'range', 'min': 30, 'max': 50}
                ]

        Returns:
            (성공 여부, 메시지)
        """
        try:
            if self.original_df is None:
                return False, "먼저 데이터를 로드해주세요."

            # 원본에서 다시 시작
            self.processed_df = self.original_df.copy()

            before_count = len(self.processed_df)

            mask = pd.Series([True] * len(self.processed_df))

            for f in filters:
                column = f.get("column")
                operator = f.get("operator")

                if column not in self.columns:
                    continue

                col_data = self.processed_df[column]

                if operator == ">=":
                    mask &= col_data >= f.get("value", 0)
                elif operator == "<=":
                    mask &= col_data <= f.get("value", 0)
                elif operator == ">":
                    mask &= col_data > f.get("value", 0)
                elif operator == "<":
                    mask &= col_data < f.get("value", 0)
                elif operator == "=":
                    mask &= col_data == f.get("value", 0)
                elif operator == "!=":
                    mask &= col_data != f.get("value", 0)
                elif operator == "range":
                    min_val = f.get("min", float("-inf"))
                    max_val = f.get("max", float("inf"))
                    mask &= (col_data >= min_val) & (col_data <= max_val)

            # 제거될 행 저장 (시뮬레이션용)
            removed = self.processed_df[~mask].copy()
            if len(removed) > 0:
                removed["_removal_reason"] = "filter"
                self.removed_rows.append(removed)

            self.processed_df = self.processed_df[mask].reset_index(drop=True)

            after_count = len(self.processed_df)
            self.stats["filtered_rows"] = after_count
            self.stats["filter_removed"] = before_count - after_count

            return (
                True,
                f"필터링 완료: {before_count} → {after_count}행 ({after_count / before_count * 100:.1f}%)",
            )

        except Exception as e:
            return False, f"필터링 실패: {str(e)}"

    def remove_outliers(
        self,
        method: str = "2.5sigma",
        columns: Optional[List[str]] = None,
        action: str = "drop",
    ) -> Tuple[bool, str]:
        """
        이상값을 제거합니다.

        Args:
            method: 이상값 탐지 방법
                - '2sigma': ±2 표준편차 (95.4% 포함)
                - '2.5sigma': ±2.5 표준편차 (98.8% 포함) [권장]
                - '3sigma': ±3 표준편차 (99.7% 포함)
                - 'iqr': IQR 방식
            columns: 적용할 컬럼 목록 (None이면 모든 숫자 컬럼)
            action: 이상값 처리 방법
                - 'nan': 해당 값만 NaN으로 변경
                - 'drop': 해당 행 전체 삭제 [기본값]

        Returns:
            (성공 여부, 메시지)
        """
        try:
            if self.processed_df is None:
                return False, "먼저 데이터를 로드해주세요."

            # 정책상 이상값은 항상 해당 행 전체 삭제
            action = "drop"

            target_columns = columns if columns else self.numeric_columns

            # Phase 1: 원본 데이터에서 모든 컬럼의 이상값 마스크를 먼저 계산
            combined_mask = pd.Series(False, index=self.processed_df.index)
            col_outlier_counts = {}

            for col in target_columns:
                if col not in self.numeric_columns:
                    continue

                data = self.processed_df[col]

                if method == "iqr":
                    q1 = data.quantile(0.25)
                    q3 = data.quantile(0.75)
                    iqr = q3 - q1
                    lower = q1 - self.IQR_MULTIPLIER * iqr
                    upper = q3 + self.IQR_MULTIPLIER * iqr
                else:
                    n = self.SIGMA_MAP.get(method, 2.5)
                    mean = data.mean()
                    std = data.std()
                    lower = mean - n * std
                    upper = mean + n * std

                outlier_mask = (data < lower) | (data > upper)
                col_outliers = int(outlier_mask.sum())
                if col_outliers > 0:
                    col_outlier_counts[col] = col_outliers
                combined_mask |= outlier_mask

            outlier_count = int(combined_mask.sum())

            # Phase 2: 제거될 행 저장 (시뮬레이션/validation용, 중복 없이 한 번만)
            if outlier_count > 0:
                removed = self.processed_df[combined_mask].copy()
                removed["_removal_reason"] = "outlier"
                removed["_outlier_columns"] = ", ".join(col_outlier_counts.keys())
                self.removed_rows.append(removed)

            # Phase 3: 통합 마스크로 한 번에 삭제
            if action == "drop":
                self.processed_df = self.processed_df[~combined_mask].reset_index(
                    drop=True
                )

            self.stats["outliers_removed"] = outlier_count
            self.stats["rows_after_outlier"] = len(self.processed_df)

            return (
                True,
                f"이상값 처리 완료 ({self.SIGMA_DISPLAY.get(method, method)}): {outlier_count}개 행 제거",
            )

        except Exception as e:
            return False, f"이상값 처리 실패: {str(e)}"

    def _get_removed_source_df(self) -> pd.DataFrame:
        """시뮬레이션에 사용할 제거된 원본 행을 반환합니다."""
        if not self.removed_rows:
            return pd.DataFrame()

        all_removed = pd.concat(self.removed_rows, ignore_index=True)
        meta_cols = [c for c in all_removed.columns if c.startswith("_")]
        return all_removed.drop(columns=meta_cols, errors="ignore")

    def _infer_interval_minutes(self, fallback_minutes: int = 2) -> int:
        """날짜 컬럼에서 간격을 추정합니다."""
        if (
            self.processed_df is None
            or self.date_column is None
            or self.date_column not in self.processed_df.columns
        ):
            return fallback_minutes

        try:
            dates = (
                pd.to_datetime(self.processed_df[self.date_column])
                .dropna()
                .sort_values()
            )
            if len(dates) < 2:
                return fallback_minutes

            diffs = dates.diff().dropna().dt.total_seconds() / 60
            positive_diffs = diffs[diffs > 0]
            if positive_diffs.empty:
                return fallback_minutes

            return max(1, int(round(positive_diffs.median())))
        except Exception:
            return fallback_minutes

    def _repeat_tail(self, df: pd.DataFrame, rows: int) -> pd.DataFrame:
        """마지막 구간을 반복해 지정 길이만큼 확장합니다."""
        if df.empty or rows <= 0:
            return pd.DataFrame(columns=df.columns)

        tail_df = df.tail(min(rows, len(df))).copy().reset_index(drop=True)
        if len(tail_df) < rows:
            repeat_times = (rows // max(1, len(tail_df))) + 1
            tail_df = pd.concat([tail_df] * repeat_times, ignore_index=True).head(rows)
        return tail_df.reset_index(drop=True)

    def _allocate_segment_lengths(
        self, total_rows: int, ratios: List[float]
    ) -> List[int]:
        """비율 합계에 맞춰 행 수를 분배합니다."""
        if total_rows <= 0:
            return [0 for _ in ratios]

        raw = [total_rows * (ratio / 100.0) for ratio in ratios]
        lengths = [int(value) for value in raw]
        remainder = total_rows - sum(lengths)

        order = sorted(
            range(len(ratios)),
            key=lambda idx: (raw[idx] - lengths[idx], ratios[idx]),
            reverse=True,
        )

        for idx in order[:remainder]:
            lengths[idx] += 1

        return lengths

    def _save_dataframe(
        self,
        df: pd.DataFrame,
        output_path: Path,
        date_format: str = "%Y-%m-%d %H:%M:%S",
        sheet_name: Optional[str] = None,
    ) -> None:
        """데이터프레임을 Excel 또는 CSV로 저장합니다."""
        save_df = df.copy()

        if self.date_column and self.date_column in save_df.columns:
            try:
                save_df[self.date_column] = pd.to_datetime(
                    save_df[self.date_column]
                ).dt.strftime(date_format)
            except (ValueError, TypeError):
                pass

        if output_path.suffix.lower() == ".xlsx":
            from openpyxl.utils.dataframe import dataframe_to_rows
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            if sheet_name:
                ws.title = sheet_name

            for r_idx, row in enumerate(
                dataframe_to_rows(save_df, index=False, header=True), 1
            ):
                for c_idx, value in enumerate(row, 1):
                    cell = ws.cell(row=r_idx, column=c_idx, value=value)
                    if (
                        self.date_column
                        and save_df.columns[c_idx - 1] == self.date_column
                        and r_idx > 1
                    ):
                        try:
                            if cell.value and not isinstance(cell.value, datetime):
                                cell.value = pd.to_datetime(cell.value)
                        except Exception:
                            pass
                        cell.number_format = "YYYY-MM-DD HH:MM:SS"

            wb.save(output_path)
        else:
            save_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    def _build_validation_block(
        self,
        target_columns: List[str],
        validation_ratio: float,
        segment_ratios: List[float],
        sigma_start: float,
        sigma_end: float,
        interval_minutes: Optional[int] = None,
    ) -> Tuple[bool, str, Optional[pd.DataFrame], Dict[str, Any]]:
        """Validation 전용 synthetic 블록을 생성합니다."""
        if self.processed_df is None or self.processed_df.empty:
            return False, "먼저 데이터를 전처리해주세요.", None, {}

        if not target_columns:
            return False, "대상 컬럼을 1개 이상 선택하세요.", None, {}

        invalid_cols = [c for c in target_columns if c not in self.numeric_columns]
        if invalid_cols:
            return False, f"유효하지 않은 컬럼: {', '.join(invalid_cols)}", None, {}

        if len(segment_ratios) != 4:
            return False, "구간 비율은 4개여야 합니다.", None, {}

        ratio_sum = sum(segment_ratios)
        if abs(ratio_sum - 100.0) > 1e-6:
            return False, "구간 비율의 합계는 100이어야 합니다.", None, {}

        if sigma_start <= 0 or sigma_end <= 0 or sigma_end < sigma_start:
            return (
                False,
                "표준편차 배수는 0보다 커야 하며 종료 배수는 시작 배수 이상이어야 합니다.",
                None,
                {},
            )

        validation_ratio = max(0.01, min(validation_ratio, self.MAX_VALIDATION_RATIO))
        source_df = self.processed_df.reset_index(drop=True).copy()
        validation_rows = max(
            self.MIN_VALIDATION_ROWS, int(round(len(source_df) * validation_ratio))
        )
        segment_lengths = self._allocate_segment_lengths(
            validation_rows, segment_ratios
        )
        removed_source = self._get_removed_source_df().reset_index(drop=True)

        if segment_lengths[1] > 0 and removed_source.empty:
            return (
                False,
                "제거행 기반 이상 구간을 만들 제거 데이터가 없습니다. 필터링 또는 이상값 처리를 먼저 실행하세요.",
                None,
                {},
            )

        base_validation = self._repeat_tail(source_df, validation_rows)
        if base_validation.empty:
            return False, "Validation 블록을 만들 원본 데이터가 부족합니다.", None, {}

        boundaries = []
        cursor = 0
        for length in segment_lengths:
            boundaries.append((cursor, cursor + length))
            cursor += length

        validation_df = base_validation.copy()
        segment2_start, segment2_end = boundaries[1]
        segment4_start, segment4_end = boundaries[3]

        for col in target_columns:
            normal_series = source_df[col].dropna()
            if normal_series.empty:
                return (
                    False,
                    f"선택한 컬럼 '{col}'에 사용할 정상 데이터가 없습니다.",
                    None,
                    {},
                )

            removed_values = pd.Series(dtype=float)
            if col in removed_source.columns:
                removed_values = pd.to_numeric(
                    removed_source[col], errors="coerce"
                ).dropna()

            if segment_lengths[1] > 0 and removed_values.empty:
                return (
                    False,
                    f"선택한 컬럼 '{col}'에 사용할 제거행 기반 이상 데이터가 없습니다.",
                    None,
                    {},
                )

            mean = float(normal_series.mean())
            std = float(normal_series.std())
            if pd.isna(std) or std == 0:
                return (
                    False,
                    f"선택한 컬럼 '{col}'의 표준편차가 0이라 sigma 기반 validation을 만들 수 없습니다.",
                    None,
                    {},
                )

            removed_mean = (
                float(removed_values.mean()) if not removed_values.empty else mean
            )
            direction = 1 if removed_mean >= mean else -1

            if segment_lengths[1] > 0:
                baseline_idx = max(0, segment2_start - 1)
                baseline = float(validation_df.loc[baseline_idx, col])
                sorted_values = removed_values.sort_values(
                    ascending=(direction > 0)
                ).to_numpy()
                repeat_times = (segment_lengths[1] // len(sorted_values)) + 1
                target_values = np.tile(sorted_values, repeat_times)[
                    : segment_lengths[1]
                ]
                weights = np.linspace(1.0 / segment_lengths[1], 1.0, segment_lengths[1])
                generated = baseline + weights * (target_values - baseline)
                validation_df.loc[segment2_start : segment2_end - 1, col] = generated

            if segment_lengths[3] > 0:
                baseline_idx = max(0, segment4_start - 1)
                baseline = float(validation_df.loc[baseline_idx, col])
                sigma_targets = (
                    mean
                    + direction
                    * np.linspace(sigma_start, sigma_end, segment_lengths[3])
                    * std
                )
                weights = np.linspace(1.0 / segment_lengths[3], 1.0, segment_lengths[3])
                generated = baseline + weights * (sigma_targets - baseline)
                validation_df.loc[segment4_start : segment4_end - 1, col] = generated

        if self.date_column and self.date_column in validation_df.columns:
            step_minutes = interval_minutes or self._infer_interval_minutes()
            last_time = pd.to_datetime(source_df[self.date_column].iloc[-1])
            validation_df[self.date_column] = [
                last_time + timedelta(minutes=step_minutes * (idx + 1))
                for idx in range(len(validation_df))
            ]

        info = {
            "validation_rows": validation_rows,
            "segment_lengths": segment_lengths,
            "target_columns": target_columns,
            "sigma_start": sigma_start,
            "sigma_end": sigma_end,
        }
        return True, "Validation 블록 생성 완료", validation_df, info

    def generate_validation_outputs(
        self,
        target_columns: List[str],
        validation_ratio: float = 0.20,
        segment_ratios: Optional[List[float]] = None,
        sigma_start: float = 2.5,
        sigma_end: float = 4.0,
        interval_minutes: Optional[int] = None,
        original_path: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, str]]:
        """
        Validation synthetic 데이터를 생성하고 3개 산출물을 자동 저장합니다.

        Returns:
            (성공 여부, 메시지, 생성 파일 경로 dict)
        """
        paths: Dict[str, str] = {}

        try:
            segment_ratios = segment_ratios or [25, 25, 25, 25]
            success, msg, validation_df, info = self._build_validation_block(
                target_columns=target_columns,
                validation_ratio=validation_ratio,
                segment_ratios=segment_ratios,
                sigma_start=sigma_start,
                sigma_end=sigma_end,
                interval_minutes=interval_minutes,
            )
            if not success or validation_df is None:
                return False, msg, paths

            source_df = self.processed_df.reset_index(drop=True).copy()
            combined_df = pd.concat([source_df, validation_df], ignore_index=True)

            if original_path:
                original = Path(original_path)
                base_dir = original.parent
                base_name = original.stem
            else:
                base_dir = Path.cwd()
                base_name = "processed_data"

            prepro_path = base_dir / f"{base_name}_prepro.xlsx"
            combined_path = base_dir / f"{base_name}_prepro_with_valid.xlsx"
            valid_path = base_dir / f"{base_name}_valid.xlsx"

            self._save_dataframe(source_df, prepro_path)
            self._save_dataframe(combined_df, combined_path)
            self._save_dataframe(validation_df, valid_path)

            paths = {
                "prepro": str(prepro_path),
                "prepro_with_valid": str(combined_path),
                "valid": str(valid_path),
            }

            segment_lengths = info["segment_lengths"]
            message = (
                "Validation 데이터 생성 완료\n"
                f"- 대상 컬럼: {', '.join(target_columns)}\n"
                f"- Validation 길이: {info['validation_rows']:,}행 ({validation_ratio * 100:.1f}%)\n"
                f"- 구간 길이: 정상1 {segment_lengths[0]:,}행 / 제거행기반 {segment_lengths[1]:,}행 / "
                f"정상2 {segment_lengths[2]:,}행 / sigma기반 {segment_lengths[3]:,}행\n"
                f"- Sigma 구간: {sigma_start:.2f}σ → {sigma_end:.2f}σ\n"
                f"- 저장 파일:\n"
                f"  1) {prepro_path}\n"
                f"  2) {combined_path}\n"
                f"  3) {valid_path}"
            )
            return True, message, paths
        except Exception as e:
            import traceback

            return (
                False,
                f"Validation 데이터 생성 실패: {str(e)}\n{traceback.format_exc()}",
                paths,
            )

    def generate_appended_tail_dataset(
        self,
        target_columns: List[str],
        append_ratio: float = 0.15,
        transition_ratio: float = 0.35,
        interval_minutes: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        전처리 완료 데이터 뒤에 synthetic anomaly tail을 붙인 별도 파일을 생성합니다.

        Args:
            target_columns: 이상을 지시할 태그 목록
            append_ratio: 원본 대비 뒤에 붙일 길이 비율 (기본 15%)
            transition_ratio: 추가 tail 중 전이 구간 비율
            interval_minutes: 시간 간격 (None이면 데이터에서 추정)
            output_path: 저장 경로

        Returns:
            (성공 여부, 메시지)
        """
        try:
            if self.processed_df is None or self.processed_df.empty:
                return False, "먼저 데이터를 전처리해주세요."

            removed_source = self._get_removed_source_df()
            if removed_source.empty:
                return (
                    False,
                    "붙일 이상 tail을 만들 제거 데이터가 없습니다. 필터링 또는 이상값 처리를 먼저 실행하세요.",
                )

            if not target_columns:
                return False, "대상 컬럼을 1개 이상 선택하세요."

            invalid_cols = [c for c in target_columns if c not in self.numeric_columns]
            if invalid_cols:
                return False, f"유효하지 않은 컬럼: {', '.join(invalid_cols)}"

            append_ratio = max(0.01, min(append_ratio, 0.5))
            transition_ratio = max(0.0, min(transition_ratio, 0.9))

            source_df = self.processed_df.reset_index(drop=True).copy()
            append_rows = max(3, int(round(len(source_df) * append_ratio)))
            transition_rows = min(
                append_rows - 1, max(1, int(round(append_rows * transition_ratio)))
            )
            abnormal_rows = max(1, append_rows - transition_rows)

            base_tail = source_df.tail(append_rows).copy().reset_index(drop=True)
            if len(base_tail) < append_rows:
                repeat_times = (append_rows // len(base_tail)) + 1
                base_tail = (
                    pd.concat([base_tail] * repeat_times, ignore_index=True)
                    .head(append_rows)
                    .reset_index(drop=True)
                )

            source_candidates = removed_source.copy()
            for col in target_columns:
                if col in source_candidates.columns:
                    source_candidates = source_candidates[
                        source_candidates[col].notna()
                    ]

            if source_candidates.empty:
                return False, "선택한 태그들에 사용할 이상 데이터가 부족합니다."

            source_candidates = source_candidates.reset_index(drop=True)
            repeat_times = (abnormal_rows // len(source_candidates)) + 1
            anomaly_rows = (
                pd.concat([source_candidates] * repeat_times, ignore_index=True)
                .head(abnormal_rows)
                .reset_index(drop=True)
            )

            synthetic_tail = base_tail.copy()
            last_normal_row = source_df.iloc[-1]

            for col in target_columns:
                baseline = float(last_normal_row[col])
                first_abnormal = float(anomaly_rows.iloc[0][col])

                for i in range(transition_rows):
                    ratio = (i + 1) / (transition_rows + 1)
                    synthetic_tail.loc[i, col] = (
                        baseline + (first_abnormal - baseline) * ratio
                    )

                for i in range(abnormal_rows):
                    row_idx = transition_rows + i
                    if row_idx >= len(synthetic_tail):
                        break
                    synthetic_tail.loc[row_idx, col] = anomaly_rows.iloc[i][col]

            if self.date_column and self.date_column in source_df.columns:
                step_minutes = interval_minutes or self._infer_interval_minutes()
                last_time = pd.to_datetime(source_df[self.date_column].iloc[-1])
                new_times = [
                    last_time + timedelta(minutes=step_minutes * (i + 1))
                    for i in range(len(synthetic_tail))
                ]
                synthetic_tail[self.date_column] = new_times

            combined_df = pd.concat([source_df, synthetic_tail], ignore_index=True)

            if output_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"Residual_Challenge_{timestamp}.xlsx"

            output_path = Path(output_path)
            self._save_dataframe(
                combined_df, output_path, sheet_name="ResidualChallenge"
            )

            return True, (
                f"후행 이상 tail 파일 생성 완료: {output_path}\n"
                f"- 대상 컬럼: {', '.join(target_columns)}\n"
                f"- 원본 행 수: {len(source_df):,}행\n"
                f"- 추가 tail: {append_rows:,}행 ({append_ratio * 100:.1f}%)\n"
                f"- 전이 구간: {transition_rows:,}행\n"
                f"- 이상 구간: {abnormal_rows:,}행"
            )
        except Exception as e:
            import traceback

            return (
                False,
                f"후행 이상 tail 생성 실패: {str(e)}\n{traceback.format_exc()}",
            )

    def normalize_timestamps(self, interval_minutes: int = 2) -> Tuple[bool, str]:
        """
        시간을 가장 가까운 지정된 간격으로 정규화(스냅)합니다.
        예: 00:01:00 → 00:00:00, 00:02:01 → 00:02:00, 00:05:59 → 00:06:00

        엑셀 자동채우기에서 발생하는 시간 밀림 현상을 보정합니다.

        Args:
            interval_minutes: 간격 (분), 기본값 2분

        Returns:
            (성공 여부, 메시지)
        """
        try:
            if self.processed_df is None or self.date_column is None:
                return False, "데이터 또는 날짜 컬럼이 없습니다."

            dates = pd.to_datetime(self.processed_df[self.date_column])

            # 벡터화: 자정부터의 총 분 계산
            total_minutes = (
                dates.dt.hour * 60
                + dates.dt.minute
                + dates.dt.second / 60
                + dates.dt.microsecond / 60_000_000
            )

            # 가장 가까운 간격으로 반올림
            snapped_minutes = (
                total_minutes / interval_minutes
            ).round() * interval_minutes

            # 24시간 넘어가면 다음 날로
            days_add = (snapped_minutes // (24 * 60)).astype(int)
            snapped_minutes = snapped_minutes % (24 * 60)

            snapped_hours = (snapped_minutes // 60).astype(int)
            snapped_mins = (snapped_minutes % 60).astype(int)

            # 벡터화된 새 시간 생성
            new_dates = (
                dates.dt.normalize()
                + pd.to_timedelta(snapped_hours, unit="h")
                + pd.to_timedelta(snapped_mins, unit="m")
                + pd.to_timedelta(days_add, unit="D")
            )

            # 변경된 행 수 계산
            corrected_mask = (
                (dates.dt.minute != snapped_mins)
                | (dates.dt.second != 0)
                | (dates.dt.microsecond != 0)
            )
            corrected_count = int(corrected_mask.sum())

            self.processed_df[self.date_column] = new_dates

            return (
                True,
                f"시간 정규화 완료: {corrected_count}개 시간 보정 ({interval_minutes}분 간격)",
            )

        except (ValueError, TypeError) as e:
            return False, f"시간 정규화 실패: {str(e)}"

    def realign_timestamps(
        self, start_time: str, interval_minutes: int = 2
    ) -> Tuple[bool, str]:
        """
        시간을 재정렬합니다. 지정된 시작 시간부터 일정 간격으로 재배열.

        Args:
            start_time: 시작 시간 (yyyy-mm-dd hh:mm:ss 형식)
            interval_minutes: 간격 (분), 기본값 2분

        Returns:
            (성공 여부, 메시지)
        """
        try:
            if self.processed_df is None or self.date_column is None:
                return False, "데이터 또는 날짜 컬럼이 없습니다."

            # 시작 시간 파싱
            start_dt = pd.to_datetime(start_time)

            # 새로운 시간 생성
            num_rows = len(self.processed_df)
            new_times = [
                start_dt + timedelta(minutes=interval_minutes * i)
                for i in range(num_rows)
            ]

            # 날짜 컬럼 업데이트
            self.processed_df[self.date_column] = new_times

            return (
                True,
                f"시간 재정렬 완료: {start_time}부터 {interval_minutes}분 간격, {num_rows}행",
            )

        except Exception as e:
            return False, f"시간 재정렬 실패: {str(e)}"

    def save_data(
        self,
        output_path: Optional[str] = None,
        original_path: Optional[str] = None,
        date_format: str = "%Y-%m-%d %H:%M:%S",
    ) -> Tuple[bool, str]:
        """
        전처리된 데이터를 저장합니다. 날짜 형식을 보존합니다.

        Args:
            output_path: 저장 경로 (None이면 자동 생성)
            original_path: 원본 파일 경로 (파일명 생성용)
            date_format: 날짜 저장 형식

        Returns:
            (성공 여부, 메시지 또는 저장 경로)
        """
        try:
            if self.processed_df is None:
                return False, "저장할 데이터가 없습니다."

            # 저장용 복사본 생성
            save_df = self.processed_df.copy()

            # 날짜 컬럼 형식 변환 (저장 시 문자열로)
            if self.date_column and self.date_column in save_df.columns:
                try:
                    save_df[self.date_column] = pd.to_datetime(
                        save_df[self.date_column]
                    ).dt.strftime(date_format)
                except (ValueError, TypeError):
                    pass  # 변환 실패 시 그대로 저장

            if output_path is None:
                if original_path:
                    orig_path = Path(original_path)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    # 기본적으로 Excel 형식으로 저장
                    output_path = (
                        orig_path.parent
                        / f"{orig_path.stem}_processed_{timestamp}.xlsx"
                    )
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = f"processed_data_{timestamp}.xlsx"  # 기본 Excel

            output_path = Path(output_path)
            self._save_dataframe(save_df, output_path, date_format=date_format)

            return True, str(output_path)

        except Exception as e:
            return False, f"저장 실패: {str(e)}"

    def generate_simulation_data(
        self,
        target_columns: List[str],
        normal_minutes: int = 30,
        abnormal_minutes: int = 60,
        transition_minutes: int = 10,
        interval_minutes: int = 2,
        output_path: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        시뮬레이션용 데이터를 생성합니다.
        전처리 중 제거된 이상값들을 활용하여 ML 모델 테스트용 데이터 생성.

        구조: [정상 데이터] → [점진적 전환] → [비정상 데이터]

        ※ target_columns만 이상값으로 변화하고, 다른 모든 컬럼은 정상값 유지
        ※ 원본 컬럼 순서와 형식이 보존됨

        Args:
            target_columns: 이상값 발생 컬럼 목록 (이 컬럼들만 정상→이상으로 변화)
            normal_minutes: 정상 데이터 시간 (분)
            abnormal_minutes: 비정상 데이터 시간 (분)
            transition_minutes: 전환 구간 시간 (분)
            interval_minutes: 데이터 간격 (분)
            output_path: 저장 경로 (None이면 자동 생성)

        Returns:
            (성공 여부, 메시지 또는 경로)
        """
        try:
            if self.processed_df is None:
                return False, "먼저 데이터를 전처리해주세요."

            if not self.removed_rows:
                return (
                    False,
                    "제거된 이상값이 없습니다. 필터링/이상값 처리를 먼저 실행하세요.",
                )

            # target_columns 유효성 검사
            if not target_columns:
                return False, "대상 컬럼을 1개 이상 선택하세요."

            invalid_cols = [c for c in target_columns if c not in self.numeric_columns]
            if invalid_cols:
                return False, f"유효하지 않은 컬럼: {', '.join(invalid_cols)}"

            # 제거된 행 통합
            all_removed = pd.concat(self.removed_rows, ignore_index=True)

            # 내부 메타 컬럼 제거
            meta_cols = [c for c in all_removed.columns if c.startswith("_")]
            target_outliers = all_removed.drop(columns=meta_cols, errors="ignore")

            if len(target_outliers) == 0:
                return False, "시뮬레이션에 사용할 이상값 데이터가 없습니다."

            # 행 수 계산
            normal_rows = normal_minutes // interval_minutes
            transition_rows = transition_minutes // interval_minutes
            abnormal_rows = abnormal_minutes // interval_minutes

            # 1. 정상 데이터 추출 (processed_df 마지막 N행)
            total_rows = normal_rows + transition_rows + abnormal_rows

            if len(self.processed_df) < total_rows:
                base_data = self.processed_df.copy()
            else:
                base_data = self.processed_df.tail(total_rows).copy()

            # 정상 데이터 기준으로 전체 행 생성 (다른 컬럼 값 유지)
            if len(base_data) < total_rows:
                repeat_times = (total_rows // len(base_data)) + 1
                base_data = pd.concat([base_data] * repeat_times, ignore_index=True)
            simulation_df = base_data.head(total_rows).reset_index(drop=True)

            # 2. 각 target_column에 대해 이상값 적용
            for target_column in target_columns:
                if target_column not in target_outliers.columns:
                    continue

                # 해당 컬럼의 이상값 추출
                normal_mean = simulation_df[target_column].iloc[:normal_rows].mean()
                abnormal_mean = target_outliers[target_column].mean()

                # 이상값 정렬 (정상보다 높으면 오름차순, 낮으면 내림차순)
                if abnormal_mean > normal_mean:
                    sorted_values = (
                        target_outliers[target_column]
                        .sort_values(ascending=True)
                        .values
                    )
                else:
                    sorted_values = (
                        target_outliers[target_column]
                        .sort_values(ascending=False)
                        .values
                    )

                # 필요한 만큼 이상값 확보
                if len(sorted_values) < abnormal_rows:
                    repeat_times = (abnormal_rows // len(sorted_values)) + 1
                    sorted_values = np.tile(sorted_values, repeat_times)
                outlier_values = sorted_values[:abnormal_rows]

                # 전환 구간: 선형 보간
                last_normal_val = simulation_df[target_column].iloc[normal_rows - 1]
                first_abnormal_val = (
                    outlier_values[0] if len(outlier_values) > 0 else last_normal_val
                )

                for i in range(transition_rows):
                    ratio = (i + 1) / (transition_rows + 1)
                    interpolated_val = (
                        last_normal_val + (first_abnormal_val - last_normal_val) * ratio
                    )
                    simulation_df.loc[normal_rows + i, target_column] = interpolated_val

                # 비정상 구간: 이상값으로 교체
                for i in range(abnormal_rows):
                    row_idx = normal_rows + transition_rows + i
                    if row_idx < len(simulation_df):
                        simulation_df.loc[row_idx, target_column] = outlier_values[i]

            # 4. 시간 컬럼 재생성 (원본 컬럼 순서 유지)

            # 5. 시간 컬럼 재생성 (2분 배수로 맞춤)
            if self.date_column and self.date_column in simulation_df.columns:
                # 현재 시간을 2분 단위로 반올림
                now = datetime.now()
                minutes = (now.minute // 2) * 2  # 2분 배수로 맞춤
                start_time = now.replace(minute=minutes, second=0, microsecond=0)
                times = [
                    start_time + timedelta(minutes=i * interval_minutes)
                    for i in range(len(simulation_df))
                ]
                simulation_df[self.date_column] = times

            # 6. 저장 (원본 형식 유지, 추가 컬럼 없음)
            if output_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"Simulation_Data_{timestamp}.xlsx"

            output_path = Path(output_path)
            self._save_dataframe(simulation_df, output_path, sheet_name="Simulation")

            return (
                True,
                f"시뮬레이션 데이터 생성 완료: {str(output_path)}\n"
                f"- 대상 컬럼: {', '.join(target_columns)}\n"
                f"- 정상: {normal_rows}행 ({normal_minutes}분)\n"
                f"- 전환: {transition_rows}행 ({transition_minutes}분)\n"
                f"- 비정상: {abnormal_rows}행 ({abnormal_minutes}분)",
            )

        except Exception as e:
            import traceback

            return (
                False,
                f"시뮬레이션 데이터 생성 실패: {str(e)}\n{traceback.format_exc()}",
            )

    def get_removed_rows_summary(self) -> Dict[str, Any]:
        """제거된 행 요약 정보 반환"""
        if not self.removed_rows:
            return {"total": 0, "by_reason": {}}

        all_removed = pd.concat(self.removed_rows, ignore_index=True)

        summary = {"total": len(all_removed), "by_reason": {}}

        if "_removal_reason" in all_removed.columns:
            summary["by_reason"] = (
                all_removed["_removal_reason"].value_counts().to_dict()
            )

        return summary

    def get_preview(self, rows: int = 10) -> pd.DataFrame:
        """미리보기용 데이터 반환 (실제 컬럼만)"""
        if self.processed_df is not None:
            return self.processed_df.head(rows)
        return pd.DataFrame()

    def get_summary(self) -> str:
        """처리 결과 요약 문자열 반환"""
        lines = []
        lines.append("📊 전처리 결과 요약")
        lines.append(f"{'─' * 40}")

        if "original_rows" in self.stats:
            lines.append(f"원본 데이터: {self.stats['original_rows']:,}행")

        if "filtered_rows" in self.stats:
            removed = self.stats.get("filter_removed", 0)
            lines.append(f"필터링 후: {self.stats['filtered_rows']:,}행 (-{removed:,})")

        if "outliers_removed" in self.stats:
            lines.append(f"이상값 처리: {self.stats['outliers_removed']:,}개")

        if "rows_after_outlier" in self.stats:
            lines.append(f"최종 데이터: {self.stats['rows_after_outlier']:,}행")

        return "\n".join(lines)


# 테스트용 샘플 데이터 생성 함수
def create_sample_data(output_path: str = "sample_data.csv"):
    """테스트용 샘플 데이터 생성"""
    np.random.seed(42)
    n = 1000

    dates = pd.date_range(start="2025-11-27", periods=n, freq="h")

    data = {
        "Date": dates,
        "AMBIENT_TEMP": np.random.normal(20, 5, n),
        "FAN_CURRENT": np.random.normal(45, 10, n),
        "GEARBOX_OIL_TEMP": np.random.normal(65, 8, n),
        "CWP_INTK_PIT_TEMP": np.random.normal(30, 3, n),
        "CONDR_TEMP_RISE": np.random.normal(10, 2, n),
    }

    # 이상값 추가
    data["FAN_CURRENT"][50] = 150  # 극단적 이상값
    data["FAN_CURRENT"][100] = -20
    data["AMBIENT_TEMP"][200] = 60

    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    print(f"샘플 데이터 생성 완료: {output_path}")
    return output_path


if __name__ == "__main__":
    # 테스트
    sample_path = create_sample_data()

    preprocessor = DataPreprocessor()

    # 1. 데이터 로드
    success, msg = preprocessor.load_data(sample_path)
    print(msg)
    print(f"감지된 숫자 컬럼: {preprocessor.numeric_columns}")

    # 2. 필터링
    filters = [
        {"column": "AMBIENT_TEMP", "operator": ">=", "value": 15},
        {"column": "FAN_CURRENT", "operator": "range", "min": 30, "max": 60},
    ]
    success, msg = preprocessor.apply_filters(filters)
    print(msg)

    # 3. 이상값 제거 (기본값: 행 전체 삭제)
    success, msg = preprocessor.remove_outliers(method="2.5sigma", action="drop")
    print(msg)

    # 4. 저장
    success, output = preprocessor.save_data(original_path=sample_path)
    print(f"저장 완료: {output}")

    # 5. 요약
    print("\n" + preprocessor.get_summary())
