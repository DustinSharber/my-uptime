#!/bin/bash
echo "Building agent executable for Linux..."

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Check if arguments are provided
if [ -z "$1" ]; then
    echo "Error: No input script specified."
    exit 1
fi
if [ -z "$2" ]; then
    echo "Error: No output name specified."
    exit 1
fi

# Build the executable using provided arguments
pyinstaller --onefile --name "$2" "$1" --distpath dist

# Deactivate the virtual environment
deactivate

echo ""
echo "Build complete! The executable can be found in the 'dist' folder."
