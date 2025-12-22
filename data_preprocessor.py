"""
데이터 전처리 모듈 (Data Preprocessing Module)
- 시계열 데이터 로드, 필터링, 이상값 처리, 정규화
- Date 형식 보존 및 시간 재정렬 기능
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any


class DataPreprocessor:
    """시계열 데이터 전처리 클래스"""
    
    # 용어 도움말
    HELP_TEXTS = {
        '2sigma': '2σ (2 표준편차): 평균에서 ±2 표준편차 범위. 정규분포 기준 약 95.4%의 데이터 포함. 엄격한 필터링에 적합.',
        '2.5sigma': '2.5σ (2.5 표준편차): 평균에서 ±2.5 표준편차 범위. 정규분포 기준 약 98.8%의 데이터 포함. [권장]',
        '3sigma': '3σ (3 표준편차): 평균에서 ±3 표준편차 범위. 정규분포 기준 약 99.7%의 데이터 포함. 느슨한 필터링에 적합.',
        'iqr': 'IQR (사분위 범위): Q1-1.5×IQR ~ Q3+1.5×IQR 범위. 비대칭 분포에 적합. 극단적 이상값 탐지에 효과적.',
        'zscore': 'Z-Score 정규화: (값 - 평균) / 표준편차. 평균=0, 표준편차=1로 변환. 데이터 비교 시 유용.',
        'minmax': 'Min-Max 정규화: (값 - 최소) / (최대 - 최소). 0~1 범위로 변환. 신경망 입력에 적합.'
    }
    
    def __init__(self):
        self.original_df: Optional[pd.DataFrame] = None
        self.processed_df: Optional[pd.DataFrame] = None
        self.columns: List[str] = []
        self.numeric_columns: List[str] = []
        self.date_column: Optional[str] = None
        self.original_date_format: Optional[str] = None  # 원본 날짜 형식 저장
        self.stats: Dict[str, Any] = {}
    
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
            
            if path.suffix.lower() in ['.xlsx', '.xls']:
                self.original_df = pd.read_excel(file_path)
            elif path.suffix.lower() == '.csv':
                # 인코딩 자동 감지 시도
                try:
                    self.original_df = pd.read_csv(file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    try:
                        self.original_df = pd.read_csv(file_path, encoding='cp949')
                    except UnicodeDecodeError:
                        self.original_df = pd.read_csv(file_path, encoding='euc-kr')
            else:
                return False, f"지원하지 않는 파일 형식입니다: {path.suffix}"
            
            self.processed_df = self.original_df.copy()
            self.columns = list(self.original_df.columns)
            
            # 날짜 컬럼 자동 감지 (형식 보존)
            self._detect_date_column()
            
            # 숫자 컬럼 감지 (최대 30개)
            self._detect_numeric_columns()
            
            self.stats['original_rows'] = len(self.original_df)
            self.stats['columns'] = len(self.columns)
            self.stats['numeric_columns'] = len(self.numeric_columns)
            
            return True, f"파일 로드 완료: {len(self.original_df)}행, {len(self.columns)}열"
            
        except Exception as e:
            return False, f"파일 로드 실패: {str(e)}"
    
    def _detect_date_column(self):
        """날짜 컬럼을 자동 감지합니다. 원본 형식을 보존합니다."""
        date_keywords = ['date', 'time', 'datetime', '날짜', '시간', 'timestamp']
        
        for col in self.columns:
            if any(keyword in col.lower() for keyword in date_keywords):
                self.date_column = col
                
                # 원본 형식 샘플 저장 (첫 번째 유효한 값)
                sample_value = self.original_df[col].dropna().iloc[0] if len(self.original_df[col].dropna()) > 0 else None
                if sample_value is not None:
                    self.original_date_format = str(sample_value)
                
                # 날짜 형식으로 변환 시도 (내부 처리용)
                try:
                    self.original_df[col] = pd.to_datetime(self.original_df[col])
                    self.processed_df[col] = pd.to_datetime(self.processed_df[col])
                except:
                    pass
                break
    
    def _detect_numeric_columns(self):
        """숫자 컬럼을 감지합니다. 최대 30개까지 지원."""
        self.numeric_columns = []
        for col in self.columns:
            if col != self.date_column:
                if pd.api.types.is_numeric_dtype(self.original_df[col]):
                    self.numeric_columns.append(col)
                    if len(self.numeric_columns) >= 30:  # 최대 30개
                        break
    
    def get_column_stats(self, column: str) -> Dict[str, float]:
        """특정 컬럼의 통계 정보를 반환합니다."""
        if column not in self.numeric_columns:
            return {}
        
        data = self.processed_df[column].dropna()
        
        return {
            'count': len(data),
            'mean': data.mean(),
            'std': data.std(),
            'min': data.min(),
            'max': data.max(),
            'q1': data.quantile(0.25),
            'median': data.median(),
            'q3': data.quantile(0.75)
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
                column = f.get('column')
                operator = f.get('operator')
                
                if column not in self.columns:
                    continue
                
                col_data = self.processed_df[column]
                
                if operator == '>=':
                    mask &= col_data >= f.get('value', 0)
                elif operator == '<=':
                    mask &= col_data <= f.get('value', 0)
                elif operator == '>':
                    mask &= col_data > f.get('value', 0)
                elif operator == '<':
                    mask &= col_data < f.get('value', 0)
                elif operator == '=':
                    mask &= col_data == f.get('value', 0)
                elif operator == '!=':
                    mask &= col_data != f.get('value', 0)
                elif operator == 'range':
                    min_val = f.get('min', float('-inf'))
                    max_val = f.get('max', float('inf'))
                    mask &= (col_data >= min_val) & (col_data <= max_val)
            
            self.processed_df = self.processed_df[mask].reset_index(drop=True)
            
            after_count = len(self.processed_df)
            self.stats['filtered_rows'] = after_count
            self.stats['filter_removed'] = before_count - after_count
            
            return True, f"필터링 완료: {before_count} → {after_count}행 ({after_count/before_count*100:.1f}%)"
            
        except Exception as e:
            return False, f"필터링 실패: {str(e)}"
    
    def remove_outliers(self, 
                       method: str = '2.5sigma',
                       columns: Optional[List[str]] = None,
                       action: str = 'drop') -> Tuple[bool, str]:
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
            
            target_columns = columns if columns else self.numeric_columns
            outlier_count = 0
            
            for col in target_columns:
                if col not in self.numeric_columns:
                    continue
                
                data = self.processed_df[col]
                
                if method == 'iqr':
                    q1 = data.quantile(0.25)
                    q3 = data.quantile(0.75)
                    iqr = q3 - q1
                    lower = q1 - 1.5 * iqr
                    upper = q3 + 1.5 * iqr
                else:
                    # 표준편차 기반
                    sigma_map = {
                        '2sigma': 2.0,
                        '2.5sigma': 2.5,
                        '3sigma': 3.0
                    }
                    n = sigma_map.get(method, 2.5)
                    
                    mean = data.mean()
                    std = data.std()
                    lower = mean - n * std
                    upper = mean + n * std
                
                # 이상값 마스크
                outlier_mask = (data < lower) | (data > upper)
                col_outliers = outlier_mask.sum()
                outlier_count += col_outliers
                
                if action == 'nan':
                    self.processed_df.loc[outlier_mask, col] = np.nan
                elif action == 'drop':
                    self.processed_df = self.processed_df[~outlier_mask]
            
            if action == 'drop':
                self.processed_df = self.processed_df.reset_index(drop=True)
            
            self.stats['outliers_removed'] = outlier_count
            self.stats['rows_after_outlier'] = len(self.processed_df)
            
            method_names = {
                '2sigma': '2σ (95.4%)',
                '2.5sigma': '2.5σ (98.8%)',
                '3sigma': '3σ (99.7%)',
                'iqr': 'IQR'
            }
            
            return True, f"이상값 처리 완료 ({method_names.get(method, method)}): {outlier_count}개 처리"
            
        except Exception as e:
            return False, f"이상값 처리 실패: {str(e)}"
    
    def normalize_data(self, 
                      method: str = 'zscore',
                      columns: Optional[List[str]] = None) -> Tuple[bool, str]:
        """
        데이터를 정규화합니다.
        
        Args:
            method: 정규화 방법
                - 'zscore': Z-Score 정규화 (x - μ) / σ
                - 'minmax': Min-Max 정규화 (0~1 범위)
            columns: 적용할 컬럼 목록 (None이면 모든 숫자 컬럼)
        
        Returns:
            (성공 여부, 메시지)
        """
        try:
            if self.processed_df is None:
                return False, "먼저 데이터를 로드해주세요."
            
            target_columns = columns if columns else self.numeric_columns
            normalized_count = 0
            
            for col in target_columns:
                if col not in self.numeric_columns:
                    continue
                
                data = self.processed_df[col]
                
                if method == 'zscore':
                    mean = data.mean()
                    std = data.std()
                    if std != 0:
                        self.processed_df[col] = (data - mean) / std
                        normalized_count += 1
                        
                elif method == 'minmax':
                    min_val = data.min()
                    max_val = data.max()
                    if max_val != min_val:
                        self.processed_df[col] = (data - min_val) / (max_val - min_val)
                        normalized_count += 1
            
            method_names = {
                'zscore': 'Z-Score',
                'minmax': 'Min-Max'
            }
            
            return True, f"정규화 완료 ({method_names.get(method, method)}): {normalized_count}개 컬럼"
            
        except Exception as e:
            return False, f"정규화 실패: {str(e)}"
    
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
            
            # 날짜 컬럼을 datetime으로 변환
            dates = pd.to_datetime(self.processed_df[self.date_column])
            
            corrected_count = 0
            new_times = []
            
            for dt in dates:
                # 원본 시간의 총 분 계산 (초 포함)
                total_minutes = dt.hour * 60 + dt.minute + dt.second / 60 + dt.microsecond / 60000000
                
                # 가장 가까운 간격으로 반올림
                snapped_minutes = round(total_minutes / interval_minutes) * interval_minutes
                
                # 24시간 넘어가면 다음 날로
                days_add = int(snapped_minutes // (24 * 60))
                snapped_minutes = snapped_minutes % (24 * 60)
                
                snapped_hour = int(snapped_minutes // 60)
                snapped_min = int(snapped_minutes % 60)
                
                # 새 시간 생성
                try:
                    new_dt = dt.replace(hour=snapped_hour, minute=snapped_min, second=0, microsecond=0)
                    if days_add > 0:
                        new_dt = new_dt + timedelta(days=days_add)
                except:
                    new_dt = dt
                
                # 변경 여부 확인
                if dt.minute != snapped_min or dt.second != 0 or dt.microsecond != 0:
                    corrected_count += 1
                
                new_times.append(new_dt)
            
            # 날짜 컬럼 업데이트
            self.processed_df[self.date_column] = new_times
            
            return True, f"시간 정규화 완료: {corrected_count}개 시간 보정 ({interval_minutes}분 간격)"
            
        except Exception as e:
            return False, f"시간 정규화 실패: {str(e)}"
    
    def realign_timestamps(self, 
                          start_time: str,
                          interval_minutes: int = 2) -> Tuple[bool, str]:
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
            new_times = [start_dt + timedelta(minutes=interval_minutes * i) for i in range(num_rows)]
            
            # 날짜 컬럼 업데이트
            self.processed_df[self.date_column] = new_times
            
            return True, f"시간 재정렬 완료: {start_time}부터 {interval_minutes}분 간격, {num_rows}행"
            
        except Exception as e:
            return False, f"시간 재정렬 실패: {str(e)}"
    
    def save_data(self, 
                 output_path: Optional[str] = None,
                 original_path: Optional[str] = None,
                 date_format: str = '%Y-%m-%d %H:%M:%S') -> Tuple[bool, str]:
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
                    save_df[self.date_column] = pd.to_datetime(save_df[self.date_column]).dt.strftime(date_format)
                except:
                    pass  # 변환 실패 시 그대로 저장
            
            if output_path is None:
                if original_path:
                    orig_path = Path(original_path)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_path = orig_path.parent / f"{orig_path.stem}_processed_{timestamp}{orig_path.suffix}"
                else:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_path = f"processed_data_{timestamp}.csv"
            
            output_path = Path(output_path)
            
            if output_path.suffix.lower() in ['.xlsx', '.xls']:
                save_df.to_excel(output_path, index=False)
            else:
                save_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            
            return True, str(output_path)
            
        except Exception as e:
            return False, f"저장 실패: {str(e)}"
    
    def get_preview(self, rows: int = 10) -> pd.DataFrame:
        """미리보기용 데이터 반환 (실제 컬럼만)"""
        if self.processed_df is not None:
            return self.processed_df.head(rows)
        return pd.DataFrame()
    
    def get_summary(self) -> str:
        """처리 결과 요약 문자열 반환"""
        lines = []
        lines.append(f"📊 전처리 결과 요약")
        lines.append(f"{'─' * 40}")
        
        if 'original_rows' in self.stats:
            lines.append(f"원본 데이터: {self.stats['original_rows']:,}행")
        
        if 'filtered_rows' in self.stats:
            removed = self.stats.get('filter_removed', 0)
            lines.append(f"필터링 후: {self.stats['filtered_rows']:,}행 (-{removed:,})")
        
        if 'outliers_removed' in self.stats:
            lines.append(f"이상값 처리: {self.stats['outliers_removed']:,}개")
        
        if 'rows_after_outlier' in self.stats:
            lines.append(f"최종 데이터: {self.stats['rows_after_outlier']:,}행")
        
        return "\n".join(lines)


# 테스트용 샘플 데이터 생성 함수
def create_sample_data(output_path: str = "sample_data.csv"):
    """테스트용 샘플 데이터 생성"""
    np.random.seed(42)
    n = 1000
    
    dates = pd.date_range(start='2025-11-27', periods=n, freq='h')
    
    data = {
        'Date': dates,
        'AMBIENT_TEMP': np.random.normal(20, 5, n),
        'FAN_CURRENT': np.random.normal(45, 10, n),
        'GEARBOX_OIL_TEMP': np.random.normal(65, 8, n),
        'CWP_INTK_PIT_TEMP': np.random.normal(30, 3, n),
        'CONDR_TEMP_RISE': np.random.normal(10, 2, n)
    }
    
    # 이상값 추가
    data['FAN_CURRENT'][50] = 150  # 극단적 이상값
    data['FAN_CURRENT'][100] = -20
    data['AMBIENT_TEMP'][200] = 60
    
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
        {'column': 'AMBIENT_TEMP', 'operator': '>=', 'value': 15},
        {'column': 'FAN_CURRENT', 'operator': 'range', 'min': 30, 'max': 60}
    ]
    success, msg = preprocessor.apply_filters(filters)
    print(msg)
    
    # 3. 이상값 제거 (기본값: 행 전체 삭제)
    success, msg = preprocessor.remove_outliers(method='2.5sigma', action='drop')
    print(msg)
    
    # 4. 저장
    success, output = preprocessor.save_data(original_path=sample_path)
    print(f"저장 완료: {output}")
    
    # 5. 요약
    print("\n" + preprocessor.get_summary())
