@echo off
echo Building agent executable...

REM Create a virtual environment
python -m venv .venv
call .venv\Scripts\activate.bat

REM Install dependencies
pip install -r requirements.txt
pip install pyinstaller

REM Build the executable
pyinstaller --onefile --name uptime_agent agent.py

REM Deactivate the virtual environment
deactivate

echo.
echo Build complete! The executable can be found in the 'dist' folder.
pause
