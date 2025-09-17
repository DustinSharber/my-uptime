# Uptime Agent Builder

This directory contains the uptime monitoring agent and build scripts to create executables for different platforms.

## Quick Start

### Option 1: Use the comprehensive build script (Recommended)
```bash
# Build for Linux (native or in Docker environment)
./build_agent.sh linux

# Build for Linux using Docker (recommended for consistent builds)
./build_agent.sh docker

# Build for Windows (on Windows only)
./build_agent.sh windows
```

### Option 2: Use platform-specific scripts

**Linux:**
```bash
chmod +x build_linux.sh
./build_linux.sh
```

**Windows:**
```cmd
build_windows.bat
```

**Docker:**
```bash
# Build the Docker image and extract executable
docker build -t uptime-agent-builder .
mkdir -p dist
docker run --rm -v $(pwd)/dist:/app/dist uptime-agent-builder
```

## Build Outputs

After a successful build, you'll find the executables in the `dist/` directory:

- **Linux**: `dist/uptime_agent_linux`
- **Windows**: `dist/uptime_agent_windows.exe`

## Troubleshooting

### "Build process completed but the executable was not found"

This error occurs when:
1. The build script couldn't find the required files
2. PyInstaller failed to create the executable
3. The executable was created with a different name than expected

**Solutions:**
1. Use the new build scripts (`build_agent.sh`, `build_linux.sh`, or `build_windows.bat`)
2. Check that all required files are present (`agent.py`, `requirements.txt`)
3. Make sure Python and pip are properly installed
4. Try the Docker build method for consistent results

### "Permission denied" on Windows

This happens when:
1. The script doesn't have execution permissions
2. Antivirus software is blocking the build process
3. Python/PyInstaller isn't properly installed

**Solutions:**
1. Run Command Prompt as Administrator
2. Temporarily disable antivirus during the build
3. Make sure Python is installed and in your PATH
4. Use the comprehensive build script: `build_agent.sh windows`

### Docker build issues

**Solutions:**
1. Make sure Docker is running
2. Ensure you have enough disk space
3. Try building with: `./build_agent.sh docker`

## Configuration

The agent uses these environment variables:

- `UPTIME_API_KEY`: API key for authentication
- `UPTIME_API_ENDPOINT`: URL of the monitoring application (default: http://localhost:5000/api)
- `UPTIME_LOG_LINES`: Number of log lines to read (default: 100)

## Usage

Once built, run the agent with:

```bash
# Linux
export UPTIME_API_KEY="your-api-key"
export UPTIME_API_ENDPOINT="http://your-monitoring-app:5000/api"
./dist/uptime_agent_linux
```

```cmd
# Windows
set UPTIME_API_KEY=your-api-key
set UPTIME_API_ENDPOINT=http://your-monitoring-app:5000/api
dist\uptime_agent_windows.exe
```

## Files Explanation

- `agent.py`: Main agent source code
- `requirements.txt`: Python dependencies
- `build_agent.sh`: Comprehensive build script (recommended)
- `build_linux.sh`: Linux-specific build script
- `build_windows.bat`: Windows-specific build script
- `Dockerfile`: For building Linux executable in Docker
- `*.spec`: PyInstaller specification files (auto-generated)
- `build/`: PyInstaller build cache (auto-generated)
- `dist/`: Output directory for built executables
