@echo off
chcp 65001 >nul
title AI 업무도우미 서버

echo ========================================
echo   AI 업무도우미 서버 시작
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo ========================================
echo.

:: ── 1) 포트 점유 프로세스 강제 종료 ──
echo [1/3] 포트 정리 중...

for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":5173 "') do (
    echo   - 5173 포트 점유 프로세스 종료 (PID: %%p)
    taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8000 "') do (
    echo   - 8000 포트 점유 프로세스 종료 (PID: %%p)
    taskkill /PID %%p /F >nul 2>&1
)

timeout /t 1 /nobreak >nul
echo   포트 정리 완료
echo.

:: ── 2) Backend 시작 ──
echo [2/3] Backend 시작 (port 8000)...
cd /d "%~dp0backend"
start "AI-Backend" cmd /c "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
cd /d "%~dp0"
echo   Backend 시작됨
echo.

:: ── 3) Frontend 시작 ──
echo [3/3] Frontend 시작 (port 5173, strictPort)...
cd /d "%~dp0frontend"
start "AI-Frontend" cmd /c "npm run dev"
cd /d "%~dp0"
echo   Frontend 시작됨
echo.

echo ========================================
echo   서버 실행 완료!
echo   브라우저: http://localhost:5173
echo ========================================
echo.
echo   종료하려면 아무 키나 누르세요...
pause >nul
