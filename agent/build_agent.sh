#!/bin/bash

# Comprehensive agent build script
# Usage: ./build_agent.sh [linux|windows|docker]

BUILD_TYPE=${1:-"linux"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "===== Uptime Agent Builder ====="
echo "Build type: $BUILD_TYPE"
echo "Working directory: $PWD"
echo ""

case $BUILD_TYPE in
    "linux")
        echo "Building Linux executable..."
        if [ ! -f "build_linux.sh" ]; then
            echo "Error: build_linux.sh not found!"
            exit 1
        fi
        chmod +x build_linux.sh
        ./build_linux.sh
        if [ -f "dist/uptime_agent_linux" ]; then
            echo "✅ Linux build successful: dist/uptime_agent_linux"
        else
            echo "❌ Linux build failed!"
            exit 1
        fi
        ;;
    
    "windows")
        echo "Building Windows executable..."
        if [ ! -f "build_windows.bat" ]; then
            echo "Error: build_windows.bat not found!"
            exit 1
        fi
        # On Linux/macOS, we can't run .bat files directly
        if command -v wine >/dev/null 2>&1; then
            echo "Using Wine to run Windows build script..."
            wine cmd /c build_windows.bat
        else
            echo "Cannot build Windows executable on this system."
            echo "Please run build_windows.bat on a Windows machine."
            exit 1
        fi
        ;;
    
    "docker")
        echo "Building using Docker..."
        if [ ! -f "Dockerfile" ]; then
            echo "Error: Dockerfile not found!"
            exit 1
        fi
        
        # Create dist directory if it doesn't exist
        mkdir -p dist
        
        # Build the Docker image
        echo "Building Docker image..."
        docker build -t uptime-agent-builder .
        
        if [ $? -ne 0 ]; then
            echo "❌ Docker build failed!"
            exit 1
        fi
        
        # Run the container to extract the executable
        echo "Extracting executable from Docker container..."
        docker run --rm -v "$(pwd)/dist:/app/dist" uptime-agent-builder
        
        if [ -f "dist/uptime_agent_linux" ]; then
            echo "✅ Docker build successful: dist/uptime_agent_linux"
        else
            echo "❌ Docker build failed - executable not found!"
            exit 1
        fi
        ;;
    
    *)
        echo "Usage: $0 [linux|windows|docker]"
        echo ""
        echo "Build types:"
        echo "  linux   - Build Linux executable (native or in Docker)"
        echo "  windows - Build Windows executable (requires Windows or Wine)"
        echo "  docker  - Build Linux executable using Docker"
        echo ""
        exit 1
        ;;
esac

echo ""
echo "===== Build Complete ====="
echo "Check the 'dist' directory for your executable."
