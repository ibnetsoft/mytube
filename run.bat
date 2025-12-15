@echo off
chcp 65001 > nul
echo.
echo ========================================
echo   wingsAIStudio 서버 시작
echo ========================================
echo.

REM 가상환경 확인 및 생성
if not exist "venv" (
    echo [1/3] 가상환경 생성 중...
    python -m venv venv
    echo      완료!
) else (
    echo [1/3] 가상환경 확인됨
)

REM 가상환경 활성화
echo [2/3] 가상환경 활성화 중...
call venv\Scripts\activate.bat

REM 패키지 설치 확인
if not exist "venv\Lib\site-packages\fastapi" (
    echo [3/3] 패키지 설치 중... (최초 1회)
    pip install -r requirements.txt
    echo      완료!
) else (
    echo [3/3] 패키지 확인됨
)

echo.
echo ========================================
echo   서버 시작: http://127.0.0.1:8000
echo   종료: Ctrl+C
echo ========================================
echo.

REM 서버 실행
python main.py
