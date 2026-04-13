import pandas as pd
import time
from data_preprocessor import DataPreprocessor

# 가상의 시계열 데이터 10만건 생성
dates = pd.date_range(start='2026-03-01', periods=100000, freq='61s') # 61초 간격으로 밀린 시간 생성
df = pd.DataFrame({'Date': dates, 'Value': range(100000)})

preprocessor = DataPreprocessor()
preprocessor.processed_df = df
preprocessor.date_column = 'Date'

start_time = time.time()
success, msg = preprocessor.normalize_timestamps(interval_minutes=2)
end_time = time.time()

print(f"결과: {msg}")
print(f"소요 시간: {end_time - start_time:.4f}초")
print(preprocessor.processed_df.head(5))
