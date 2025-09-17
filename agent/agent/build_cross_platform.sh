#!/bin/bash

# Cross-platform build script for Docker containers
# This script can build both Linux and Windows executables

echo "Cross-platform agent build script"

# Check if arguments are provided
if [ -z "$1" ]; then
    echo "Error: No input script specified."
    echo "Usage: $0 <input_script> <output_name> [platform]"
    exit 1
fi

if [ -z "$2" ]; then
    echo "Error: No output name specified."
    echo "Usage: $0 <input_script> <output_name> [platform]"
    exit 1
fi

INPUT_SCRIPT="$1"
OUTPUT_NAME="$2"
PLATFORM="${3:-linux}"  # Default to linux if not specified

echo "Building agent: $OUTPUT_NAME for platform: $PLATFORM"
echo "Input script: $INPUT_SCRIPT"

# Check if we're in a Docker container
if [ -f /.dockerenv ]; then
    echo "Detected Docker environment"
    
    # In Docker, PyInstaller should already be installed via Dockerfile
    # Install it anyway to be safe
    pip install --no-cache-dir pyinstaller
    
    # Build the executable with appropriate naming
    if [ "$PLATFORM" = "windows" ]; then
        echo "Building Windows executable in Linux container using Wine..."
        
        # Initialize Wine if not already done
        if [ ! -d "$HOME/.wine" ]; then
            echo "Initializing Wine..."
            wineboot --init
            sleep 5
        fi
        
        # Install Python for Windows via Wine
        if [ ! -f "$HOME/.wine/drive_c/Python311/python.exe" ]; then
            echo "Installing Python for Windows via Wine..."
            wget -q https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe -O /tmp/python-installer.exe
            wine /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=1
            sleep 10
        fi
        
        # Install PyInstaller in Wine Python
        wine /root/.wine/drive_c/Python311/python.exe -m pip install pyinstaller
        
        # Copy the script to Wine's drive
        cp "$INPUT_SCRIPT" "$HOME/.wine/drive_c/temp_script.py"
        
        # Build Windows executable using Wine
        wine /root/.wine/drive_c/Python311/python.exe -m PyInstaller --onefile --name "${OUTPUT_NAME}" "c:/temp_script.py" --distpath "c:/dist"
        
        # Copy the built executable back to the host filesystem
        cp "$HOME/.wine/drive_c/dist/${OUTPUT_NAME}.exe" "dist/${OUTPUT_NAME}.exe"
        
        # Clean up
        rm -f "$HOME/.wine/drive_c/temp_script.py"
        rm -rf "$HOME/.wine/drive_c/build"
        
        echo "Windows executable built successfully!"
    else
        # Linux build
        echo "Building Linux executable..."
        pyinstaller --onefile --name "$OUTPUT_NAME" "$INPUT_SCRIPT" --distpath dist
        
        # Make sure the executable is executable
        chmod +x "dist/$OUTPUT_NAME"
    fi
    
else
    echo "Detected native environment"
    
    # Create a virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv .venv
    fi
    
    # Activate the virtual environment
    echo "Activating virtual environment..."
    source .venv/bin/activate
    
    # Install dependencies
    echo "Installing dependencies..."
    pip install -r requirements.txt
    pip install pyinstaller
    
    # Build the executable
    if [ "$PLATFORM" = "windows" ]; then
        echo "Building Windows executable (requires Wine for cross-compilation)..."
        # This would require Wine to be installed for true cross-compilation
        pyinstaller --onefile --name "${OUTPUT_NAME}" "$INPUT_SCRIPT" --distpath dist
    else
        echo "Building Linux executable..."
        pyinstaller --onefile --name "$OUTPUT_NAME" "$INPUT_SCRIPT" --distpath dist
        chmod +x "dist/$OUTPUT_NAME"
    fi
    
    # Deactivate the virtual environment
    deactivate
fi

# Check if build was successful
if [ -f "dist/$OUTPUT_NAME" ]; then
    echo "Build complete! Executable: dist/$OUTPUT_NAME"
else
    echo "Error: Build failed - executable not found"
    exit 1
fi
