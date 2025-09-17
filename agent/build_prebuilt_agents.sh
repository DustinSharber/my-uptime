#!/bin/bash
echo "Building pre-built uptime agents..."

# Create dist directory if it doesn't exist
mkdir -p dist

# Function to build agent for a specific platform
build_agent() {
    local platform="$1"
    local script_name="agent_parameterized.py"
    
    echo "Building agent for $platform..."
    
    if [ "$platform" = "windows" ]; then
        agent_name="uptime_agent.exe"
        
        # Try different build approaches for Windows
        if command -v docker &> /dev/null; then
            echo "Using Docker to build Windows agent..."
            # Create temporary Dockerfile for Windows build
            cat > Dockerfile.windows << 'EOF'
# Use Ubuntu with Wine for Windows builds
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Wine and dependencies
RUN apt-get update && apt-get install -y \
    wine \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Set up Wine
ENV WINEPREFIX=/root/.wine
ENV WINEARCH=win64

# Initialize Wine
RUN wine wineboot --init

# Download and install Python for Windows
RUN wget -q https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe -O /tmp/python-installer.exe
RUN wine /tmp/python-installer.exe /quiet InstallAllUsers=1 PrependPath=1

# Set working directory
WORKDIR /app/agent

# Copy agent files
COPY requirements.txt .
COPY agent_parameterized.py .

# Install dependencies in Wine Python
RUN wine /root/.wine/drive_c/users/root/AppData/Local/Programs/Python/Python311/python.exe -m pip install -r requirements.txt
RUN wine /root/.wine/drive_c/users/root/AppData/Local/Programs/Python/Python311/python.exe -m pip install pyinstaller

# Build the agent
RUN wine /root/.wine/drive_c/users/root/AppData/Local/Programs/Python/Python311/python.exe -m PyInstaller \
    --onefile \
    --name uptime_agent \
    --distpath dist \
    agent_parameterized.py

CMD ["cp", "dist/uptime_agent.exe", "/output/"]
EOF
            
            # Build the Docker image and extract the binary
            docker build -f Dockerfile.windows -t uptime-agent-windows-builder .
            docker run --rm -v "$(pwd)/dist:/output" uptime-agent-windows-builder
            
            # Clean up
            rm Dockerfile.windows
            
        elif [ "$OS" = "Windows_NT" ]; then
            # Native Windows build
            echo "Building on native Windows..."
            python -m pip install pyinstaller
            pyinstaller --onefile --name uptime_agent "$script_name" --distpath dist
        else
            echo "Warning: Cannot build Windows agent on this platform without Docker"
            return 1
        fi
        
    elif [ "$platform" = "linux" ]; then
        agent_name="uptime_agent"
        
        # Check if we should use Docker for compatibility
        if command -v docker &> /dev/null; then
            echo "Using Docker for compatible Linux build..."
            # Use the compatible Dockerfile
            if [ -f "Dockerfile.compatible" ]; then
                # Modify the Dockerfile to build from agent_parameterized.py
                cat > Dockerfile.prebuilt << 'EOF'
# Use Ubuntu 18.04 for older GLIBC compatibility (GLIBC 2.27)
FROM ubuntu:18.04

# Install Python 3.8 and build tools
RUN apt-get update && apt-get install -y \
    python3.8 \
    python3.8-dev \
    python3.8-distutils \
    python3-pip \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Update pip
RUN python3.8 -m pip install --upgrade pip

# Set working directory
WORKDIR /app/agent

# Copy agent files
COPY requirements.txt .
COPY agent_parameterized.py .

# Install Python dependencies
RUN python3.8 -m pip install --no-cache-dir -r requirements.txt
RUN python3.8 -m pip install pyinstaller

# Build the agent executable
RUN python3.8 -m PyInstaller \
    --onefile \
    --name uptime_agent \
    --strip \
    --noupx \
    --exclude-module tkinter \
    --exclude-module unittest \
    agent_parameterized.py \
    --distpath dist

# Make the executable runnable
RUN chmod +x dist/uptime_agent

# Create output directory and copy executable
RUN mkdir -p /output && cp dist/uptime_agent /output/
EOF
                
                docker build -f Dockerfile.prebuilt -t uptime-agent-prebuilt .
                docker run --rm -v "$(pwd)/dist:/output" uptime-agent-prebuilt cp /output/uptime_agent /output/
                
                # Clean up
                rm Dockerfile.prebuilt
            else
                echo "Dockerfile.compatible not found, using native build..."
                build_native_linux
            fi
        else
            build_native_linux
        fi
    fi
    
    # Check if build was successful
    if [ -f "dist/$agent_name" ]; then
        echo "✓ Successfully built $platform agent: dist/$agent_name"
        return 0
    else
        echo "✗ Failed to build $platform agent"
        return 1
    fi
}

build_native_linux() {
    echo "Building Linux agent natively..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv_prebuilt" ]; then
        python3 -m venv .venv_prebuilt
    fi
    
    # Activate virtual environment
    source .venv_prebuilt/bin/activate
    
    # Install dependencies
    pip install -r requirements.txt
    pip install pyinstaller
    
    # Build the agent
    pyinstaller \
        --onefile \
        --name uptime_agent \
        --strip \
        --exclude-module tkinter \
        --exclude-module unittest \
        agent_parameterized.py \
        --distpath dist
    
    # Make executable
    chmod +x dist/uptime_agent
    
    # Clean up
    deactivate
    rm -rf .venv_prebuilt build *.spec
}

# Main build process
echo "=== Building Pre-built Uptime Agents ==="

# Build for both platforms
build_agent "linux"
linux_result=$?

build_agent "windows" 
windows_result=$?

echo ""
echo "=== Build Results ==="
if [ $linux_result -eq 0 ]; then
    echo "✓ Linux agent: dist/uptime_agent"
    ls -la dist/uptime_agent 2>/dev/null
else
    echo "✗ Linux agent build failed"
fi

if [ $windows_result -eq 0 ]; then
    echo "✓ Windows agent: dist/uptime_agent.exe"
    ls -la dist/uptime_agent.exe 2>/dev/null
else
    echo "✗ Windows agent build failed"
fi

echo ""
echo "=== Usage Instructions ==="
echo "Linux: ./dist/uptime_agent --monitor-id <ID> [--api-endpoint <URL>]"
echo "Windows: dist/uptime_agent.exe --monitor-id <ID> [--api-endpoint <URL>]"
echo ""
echo "Example:"
echo "  ./dist/uptime_agent --monitor-id 3"
echo "  ./dist/uptime_agent --monitor-id 3 --api-endpoint http://myserver:5000/api"

# Exit with error if both builds failed
if [ $linux_result -ne 0 ] && [ $windows_result -ne 0 ]; then
    echo "Error: All builds failed"
    exit 1
fi
