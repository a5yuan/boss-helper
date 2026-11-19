@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 端口已被占用说明程序已经开着，不要起第二个实例
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8848 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }" >nul 2>&1
if errorlevel 1 (
    echo BOSS-Helper 已经在运行了（端口 8848）
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo 找不到虚拟环境，请先在项目目录执行:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" run_gui.py
exit /b 0
