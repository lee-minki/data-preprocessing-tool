@echo off
REM ================================================
REM  σ 조기경보 시계열 데이터 전처리 - 웹 서버 실행
REM  Windows Server용 배치 파일
REM ================================================
REM
REM 사용법:
REM   start_web_server.bat          (기본 포트 8080)
REM   start_web_server.bat 9090     (포트 9090)
REM

SET PORT=%1
IF "%PORT%"=="" SET PORT=8511

echo.
echo ================================================
echo   σ 데이터 전처리 웹 서버 시작
echo   서버 주소: http://192.9.88.241:%PORT%
echo   포트: %PORT%
echo ================================================
echo.

REM Python 가상환경이 있으면 활성화
IF EXIST ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [INFO] 가상환경 활성화됨
)

REM 의존성 확인
pip show flask >nul 2>&1
IF ERRORLEVEL 1 (
    echo [INFO] 의존성 설치 중...
    pip install -r requirements_web.txt
)

echo.
echo [INFO] 서버 시작: http://0.0.0.0:%PORT%
echo [INFO] 브라우저에서 http://192.9.88.241:%PORT% 로 접속하세요
echo [INFO] 종료하려면 Ctrl+C 를 누르세요
echo.

python web_server.py --port %PORT% --host 0.0.0.0

pause
