@echo off
REM FX Option Pricer Launcher
REM Activates virtual environment (if present) and runs the application

cd /d "%~dp0"

REM Check for virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Run the application
python -m src.main

pause
