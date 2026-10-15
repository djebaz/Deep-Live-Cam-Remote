@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" ".\scripts\start_web_controller.py" %*
) else (
  python ".\scripts\start_web_controller.py" %*
)
