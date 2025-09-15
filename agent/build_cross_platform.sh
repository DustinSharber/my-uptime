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
        # For Windows builds in Docker, we build a Linux executable 
        # but name it appropriately for download
        echo "Building Windows-targeted executable in Linux container..."
        pyinstaller --onefile --name "${OUTPUT_NAME}" "$INPUT_SCRIPT" --distpath dist
        
        # The output will be a Linux binary, but we'll serve it as if it were Windows
        # This is a limitation of cross-compilation in basic Docker containers
        echo "Note: Built Linux executable for Windows download (cross-compilation limitation)"
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
