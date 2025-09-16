@echo off
echo Building Windows agent...
pyinstaller --onefile --name uptime_agent agent_parameterized.py
echo Done. Check the dist folder for the executable.
pause
