@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 launcher.py
    pause
    exit /b
)
where python >nul 2>nul
if %errorlevel% equ 0 (
    python launcher.py
    pause
    exit /b
)
echo 请从 https://www.python.org/downloads/ 安装 Python 3.11 或以上版本。
echo Windows 安装时勾选 Add Python to PATH，然后重新双击 Start.bat。
pause
