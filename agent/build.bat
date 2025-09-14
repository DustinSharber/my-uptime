@echo off
echo Building agent executable...

REM Create a virtual environment
python -m venv .venv
call .venv\Scripts\activate.bat

REM Install dependencies
pip install -r requirements.txt
pip install pyinstaller

REM Check if arguments are provided
if "%~1"=="" (
    echo "Error: No input script specified."
    exit /b 1
)
if "%~2"=="" (
    echo "Error: No output name specified."
    exit /b 1
)

REM Build the executable using the provided arguments
pyinstaller --onefile --name %2 %1 --distpath dist

REM Deactivate the virtual environment
deactivate

echo.
echo Build complete! The executable can be found in the 'dist' folder.
