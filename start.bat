@echo off
cd /d %~dp0

:: Kill old instances on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo ========================================
echo   术数预测系统
echo   http://localhost:8000
echo ========================================
echo 正在启动...
start http://localhost:8000
venv\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
if %errorlevel% neq 0 (
    echo.
    echo 端口8000被占用，尝试8001...
    start http://localhost:8001
    venv\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8001
)
if %errorlevel% neq 0 pause
