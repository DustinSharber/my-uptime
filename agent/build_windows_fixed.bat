@echo off
echo Building uptime agent executable for Windows with SSL support...

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM Create a virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate the virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

if %errorlevel% neq 0 (
    echo Error: Failed to activate virtual environment
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

REM Build the executable using the parameterized agent with SSL support
echo Building executable from agent_parameterized.py...
pyinstaller --onefile --name uptime_agent agent_parameterized.py --distpath dist

REM Check if build was successful
if exist "dist\uptime_agent.exe" (
    echo Build complete! Executable: dist\uptime_agent.exe
    echo This version includes SSL support for self-signed certificates
) else (
    echo Error: Build failed - executable not found
    exit /b 1
)

REM Deactivate the virtual environment
deactivate

pause
