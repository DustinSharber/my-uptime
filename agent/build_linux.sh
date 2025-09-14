#!/bin/bash
echo "Building uptime agent executable for Linux..."

# Check if we're in a Docker container or native Linux
if [ -f /.dockerenv ]; then
    echo "Detected Docker environment"
    # In Docker, we don't need a virtual environment
    pip install -r requirements.txt
    pip install pyinstaller
    
    # Build the executable
    pyinstaller --onefile --name uptime_agent_linux agent.py --distpath dist
    
    # Make sure the executable is executable
    chmod +x dist/uptime_agent_linux
    
    echo "Build complete! Executable: dist/uptime_agent_linux"
else
    echo "Detected native Linux environment"
    # Create a virtual environment
    python3 -m venv .venv
    source .venv/bin/activate
    
    # Install dependencies
    pip install -r requirements.txt
    pip install pyinstaller
    
    # Build the executable
    pyinstaller --onefile --name uptime_agent_linux agent.py --distpath dist
    
    # Make sure the executable is executable
    chmod +x dist/uptime_agent_linux
    
    # Deactivate the virtual environment
    deactivate
    
    echo "Build complete! Executable: dist/uptime_agent_linux"
fi
