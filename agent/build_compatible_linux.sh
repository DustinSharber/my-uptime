#!/bin/bash
echo "Building compatible uptime agent executable for Linux (older GLIBC)..."

# Function to build using Docker with older base image
build_with_docker() {
    echo "Building with Docker using older base image for better compatibility..."
    
    # Create a temporary Dockerfile for compatible build
    cat > Dockerfile.compatible << 'EOF'
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
COPY agent.py .

# Install Python dependencies
RUN python3.8 -m pip install --no-cache-dir -r requirements.txt
RUN python3.8 -m pip install pyinstaller

# Build the agent executable with static linking options
RUN python3.8 -m PyInstaller \
    --onefile \
    --name uptime_agent_linux_compatible \
    --strip \
    --noupx \
    agent.py \
    --distpath dist

# Make the executable runnable
RUN chmod +x dist/uptime_agent_linux_compatible

# Create output directory and copy executable
RUN mkdir -p /output && cp dist/uptime_agent_linux_compatible /output/
EOF

    # Build the Docker image
    docker build -f Dockerfile.compatible -t uptime-agent-builder .
    
    # Run the container and extract the binary
    docker run --rm -v "$(pwd)/dist:/output" uptime-agent-builder cp /output/uptime_agent_linux_compatible /output/
    
    # Clean up
    rm Dockerfile.compatible
    
    if [ -f "dist/uptime_agent_linux_compatible" ]; then
        echo "Compatible Linux executable built successfully: dist/uptime_agent_linux_compatible"
        echo "This binary should work on systems with GLIBC 2.27 and newer (Ubuntu 18.04+, CentOS 8+)"
        return 0
    else
        echo "Docker build failed"
        return 1
    fi
}

# Function to build with static Python (if available)
build_with_staticx() {
    echo "Attempting to build with staticx for maximum compatibility..."
    
    # Create virtual environment
    python3 -m venv .venv_static
    source .venv_static/bin/activate
    
    # Install dependencies including staticx
    pip install -r requirements.txt
    pip install pyinstaller staticx patchelf
    
    # Build with PyInstaller first
    pyinstaller --onefile --name uptime_agent_linux_temp agent.py --distpath dist_temp
    
    # Use staticx to create a truly portable binary
    staticx dist_temp/uptime_agent_linux_temp dist/uptime_agent_linux_static
    
    # Clean up temporary files
    rm -rf dist_temp
    rm -rf build
    rm -f uptime_agent_linux_temp.spec
    
    # Make executable
    chmod +x dist/uptime_agent_linux_static
    
    deactivate
    rm -rf .venv_static
    
    if [ -f "dist/uptime_agent_linux_static" ]; then
        echo "Static Linux executable built successfully: dist/uptime_agent_linux_static"
        echo "This binary should work on most Linux systems regardless of GLIBC version"
        return 0
    else
        echo "Static build failed"
        return 1
    fi
}

# Function to build with older Python version
build_with_older_python() {
    echo "Building with system Python for better compatibility..."
    
    # Try to use system Python 3.6 or 3.7 if available
    for python_cmd in python3.6 python3.7 python3.8 python3; do
        if command -v $python_cmd &> /dev/null; then
            echo "Using $python_cmd"
            
            # Create virtual environment with older Python
            $python_cmd -m venv .venv_compat
            source .venv_compat/bin/activate
            
            # Upgrade pip and install dependencies
            pip install --upgrade pip
            pip install -r requirements.txt
            pip install pyinstaller
            
            # Build with additional compatibility options
            pyinstaller \
                --onefile \
                --name uptime_agent_linux_compat \
                --strip \
                --exclude-module tkinter \
                --exclude-module unittest \
                --exclude-module email \
                --exclude-module html \
                --exclude-module http \
                --exclude-module urllib3 \
                --exclude-module xml \
                agent.py \
                --distpath dist
            
            chmod +x dist/uptime_agent_linux_compat
            
            deactivate
            rm -rf .venv_compat
            
            if [ -f "dist/uptime_agent_linux_compat" ]; then
                echo "Compatible executable built with $python_cmd: dist/uptime_agent_linux_compat"
                return 0
            fi
            break
        fi
    done
    
    echo "Could not find suitable Python version for compatibility build"
    return 1
}

# Create dist directory if it doesn't exist
mkdir -p dist

# Try building methods in order of preference
echo "Attempting multiple build strategies for maximum compatibility..."

# Method 1: Docker with older base image (most reliable)
if command -v docker &> /dev/null; then
    echo "=== Attempting Docker build with older base image ==="
    if build_with_docker; then
        echo "✓ Docker build succeeded"
    else
        echo "✗ Docker build failed"
    fi
else
    echo "Docker not available, skipping Docker build"
fi

# Method 2: StaticX build (most portable)
echo "=== Attempting StaticX build ==="
if build_with_staticx; then
    echo "✓ StaticX build succeeded"
else
    echo "✗ StaticX build failed"
fi

# Method 3: Older Python version
echo "=== Attempting build with older Python ==="
if build_with_older_python; then
    echo "✓ Older Python build succeeded"
else
    echo "✗ Older Python build failed"
fi

# Show results
echo ""
echo "=== Build Results ==="
ls -la dist/uptime_agent_linux* 2>/dev/null || echo "No builds succeeded"

echo ""
echo "=== Compatibility Guide ==="
echo "uptime_agent_linux_compatible: Requires GLIBC 2.27+ (Ubuntu 18.04+, CentOS 8+)"
echo "uptime_agent_linux_static: Should work on most Linux systems (any GLIBC version)"
echo "uptime_agent_linux_compat: Built with older Python for better compatibility"
echo ""
echo "Try the executables in this order for best compatibility:"
echo "1. uptime_agent_linux_static (if available)"
echo "2. uptime_agent_linux_compatible (if available)" 
echo "3. uptime_agent_linux_compat (if available)"
