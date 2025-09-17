#!/bin/bash
echo "Building Linux uptime agent executable..."

# This script serves as a wrapper for the compatible Linux build
# It calls the more comprehensive build_compatible_linux.sh script

# Make sure we're in the correct directory
cd "$(dirname "$0")"

# Create dist directory if it doesn't exist
mkdir -p dist

# Call the compatible Linux build script
chmod +x build_compatible_linux.sh
./build_compatible_linux.sh

# Check if any builds were successful
if ls dist/uptime_agent_linux* 1> /dev/null 2>&1; then
    echo "Linux agent build completed successfully"
    echo "Available executables:"
    ls -la dist/uptime_agent_linux*
    exit 0
else
    echo "Linux agent build failed - no executables were created"
    exit 1
fi
