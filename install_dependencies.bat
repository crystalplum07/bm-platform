@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Installing the verified dependency versions into the current Python environment...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Please use Anaconda Prompt and confirm that the company network allows Python package downloads.
  pause
  exit /b 1
)
echo.
python check_environment.py
pause

