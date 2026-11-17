@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
python check_environment.py
if errorlevel 1 (
  echo.
  echo The environment is not ready. Run install_dependencies.bat from Anaconda Prompt first.
  pause
  exit /b 1
)
python -m streamlit run app.py
if errorlevel 1 pause

