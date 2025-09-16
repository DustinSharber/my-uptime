# GLIBC Compatibility Guide for Linux Agent

## Problem
The error `GLIBC_2.38' not found` occurs when running a Linux binary compiled on a newer system (with newer GLIBC) on an older system (with older GLIBC).

## Solution Overview
We provide three different approaches to build compatible Linux binaries:

### 1. Quick Docker Fix (Recommended)
Build using Ubuntu 18.04 base image for GLIBC 2.27 compatibility:

```bash
# Navigate to agent directory
cd agent

# Build compatible binary using Docker
docker build -f Dockerfile.compatible -t uptime-agent-compatible .
docker run --rm -v "$(pwd)/dist:/app/dist" uptime-agent-compatible

# The compatible binary will be in dist/uptime_agent_linux_compatible
```

### 2. Comprehensive Build Script
Use the automated build script that tries multiple compatibility approaches:

```bash
# Navigate to agent directory
cd agent

# Make the script executable
chmod +x build_compatible_linux.sh

# Run the comprehensive build
./build_compatible_linux.sh
```

This script will attempt:
- Docker build with older base image (most reliable)
- StaticX build for maximum portability
- Build with older Python versions

### 3. Manual Compatibility Build
If you prefer to build manually:

```bash
# Use older Python version if available
python3.8 -m venv .venv_compat
source .venv_compat/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build with compatibility options
pyinstaller \
    --onefile \
    --name uptime_agent_linux_compat \
    --strip \
    --exclude-module tkinter \
    --exclude-module unittest \
    agent.py \
    --distpath dist

chmod +x dist/uptime_agent_linux_compat
deactivate
```

## Compatibility Matrix

| Binary Name | GLIBC Required | Compatible Systems |
|-------------|----------------|-------------------|
| `uptime_agent_linux_static` | Any | Most Linux distributions |
| `uptime_agent_linux_compatible` | GLIBC 2.27+ | Ubuntu 18.04+, CentOS 8+, Debian 10+ |
| `uptime_agent_linux_compat` | System dependent | Depends on build system |

## Testing Compatibility

Check your system's GLIBC version:
```bash
ldd --version
# or
/lib/x86_64-linux-gnu/libc.so.6
```

Test the binary:
```bash
# Try the most compatible version first
./dist/uptime_agent_linux_static

# If not available, try the compatible version
./dist/uptime_agent_linux_compatible

# Set environment variables for testing
export UPTIME_API_KEY="your_api_key"
export UPTIME_API_ENDPOINT="http://your-server:5000/api"
./dist/uptime_agent_linux_compatible
```

## Environment Variables

The agent requires these environment variables:
- `UPTIME_API_KEY`: Your unique monitor API key
- `UPTIME_API_ENDPOINT`: Your monitoring server's API endpoint (e.g., `http://localhost:5000/api`)
- `UPTIME_LOG_LINES`: Number of log lines to read (default: 100)

## Troubleshooting

### Still getting GLIBC errors?
1. Check if you have the static version: `ls -la dist/uptime_agent_linux_static`
2. Try building on the target system directly
3. Use a VM or container with the same OS as your target system

### Build fails?
1. Ensure Docker is installed and running
2. Check that you have sufficient disk space
3. Try the manual build method with system Python

### Agent not connecting?
1. Verify the API endpoint is reachable: `curl $UPTIME_API_ENDPOINT/health`
2. Check that the API key is correct
3. Review firewall settings

## Quick Fix Commands

```bash
# Navigate to agent directory
cd agent

# Option 1: Quick Docker build (recommended)
docker build -f Dockerfile.compatible -t uptime-agent-compatible .
docker run --rm -v "$(pwd)/dist:/app/dist" uptime-agent-compatible
chmod +x dist/uptime_agent_linux_compatible

# Option 2: Use the comprehensive script
chmod +x build_compatible_linux.sh
./build_compatible_linux.sh

# Test the binary
export UPTIME_API_KEY="your_api_key"
export UPTIME_API_ENDPOINT="http://your-server:5000/api"
./dist/uptime_agent_linux_compatible
