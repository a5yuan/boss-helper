@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BOSS-Helper 调试模式

echo ==============================================
echo   BOSS-Helper 调试模式（关闭窗口即退出）
echo ==============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo 找不到虚拟环境，请先在项目目录执行:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" run_gui.py

echo.
echo 程序已退出（退出码 %ERRORLEVEL%），按任意键关闭
pause >nul
