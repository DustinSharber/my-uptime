# Linux Uptime Agent - Deployment Guide

## Overview
The Linux uptime agent is a native Bash shell script that eliminates SSL certificate issues and dependency complications. It uses built-in Linux commands and utilities for system monitoring and HTTP communication.

## Features
- **Native Linux Integration**: Uses standard commands like `curl`, `df`, `free`, `/proc` filesystem
- **SSL Certificate Bypass**: Handles self-signed certificates automatically with `curl -k`
- **Zero Dependencies**: Runs on any Linux system with bash and curl (standard on all distributions)
- **System Monitoring**: CPU, RAM, disk usage, and network statistics
- **Log File Monitoring**: Reads and sends log file contents
- **Command Execution**: Execute bash/shell commands remotely
- **Error Recovery**: Automatic retry logic and detailed logging

## Requirements
- **Linux Distribution**: Any (Ubuntu, CentOS, RHEL, Debian, Alpine, etc.)
- **Shell**: Bash 3.0+ (included in all modern Linux distributions)
- **Commands**: curl, df, free (standard utilities on all Linux systems)
- **Network**: Connectivity to your monitoring server
- **No additional software installation required**

## Quick Start

### 1. Basic Usage
```bash
# Download and make executable
wget https://your-server.com/download-prebuilt-agent?platform=linux -O uptime-agent.sh
chmod +x uptime-agent.sh

# Run the agent
./uptime-agent.sh -m 1 -a "https://monitor.sharber.me/api"
```

### 2. Test Mode (Single Run)
```bash
# Test the agent with a single data collection cycle
./uptime-agent.sh -m 1 -a "https://monitor.sharber.me/api" --run-once
```

### 3. Verbose Logging
```bash
# Enable detailed logging for troubleshooting
./uptime-agent.sh -m 1 -a "https://monitor.sharber.me/api" --verbose
```

## Command Line Parameters

| Parameter | Short | Required | Default | Description |
|-----------|-------|----------|---------|-------------|
| `--monitor-id` | `-m` | Yes | - | Monitor ID from your dashboard |
| `--api-endpoint` | `-a` | Yes | - | Your monitoring server URL |
| `--interval` | `-i` | No | 60 | Check interval in seconds |
| `--log-lines` | `-l` | No | 100 | Number of log lines to read |
| `--skip-ssl` | `-s` | No | true | Skip SSL certificate validation |
| `--run-once` | `-o` | No | false | Run once and exit (for testing) |
| `--verbose` | `-v` | No | false | Enable verbose logging |
| `--help` | `-h` | No | - | Show help message |

## Deployment Methods

### Method 1: Manual Execution
```bash
# Download the script
curl -O https://your-server.com/download-prebuilt-agent?platform=linux
mv uptime-agent.sh /usr/local/bin/
chmod +x /usr/local/bin/uptime-agent.sh

# Run directly
/usr/local/bin/uptime-agent.sh -m 1 -a "https://your-server.com/api"
```

### Method 2: Systemd Service (Recommended)
Create a systemd service for automatic startup and management:

```bash
# Create service file
sudo tee /etc/systemd/system/uptime-agent.service > /dev/null <<EOF
[Unit]
Description=Uptime Monitoring Agent
After=network.target
Wants=network.target

[Service]
Type=simple
User=nobody
Group=nogroup
ExecStart=/usr/local/bin/uptime-agent.sh -m 1 -a "https://monitor.sharber.me/api"
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable uptime-agent
sudo systemctl start uptime-agent

# Check status
sudo systemctl status uptime-agent
```

### Method 3: Cron Job
Run the agent periodically using cron (for less frequent checks):

```bash
# Add to crontab (run every 5 minutes)
echo "*/5 * * * * /usr/local/bin/uptime-agent.sh -m 1 -a 'https://monitor.sharber.me/api' --run-once" | crontab -

# View current crontab
crontab -l
```

### Method 4: Screen/Tmux Session
For development or temporary monitoring:

```bash
# Using screen
screen -S uptime-agent
./uptime-agent.sh -m 1 -a "https://monitor.sharber.me/api"
# Press Ctrl+A, D to detach

# Using tmux
tmux new-session -s uptime-agent
./uptime-agent.sh -m 1 -a "https://monitor.sharber.me/api"
# Press Ctrl+B, D to detach
```

### Method 5: Docker Container
Create a lightweight container:

```bash
# Create Dockerfile
cat > Dockerfile <<EOF
FROM alpine:latest
RUN apk add --no-cache bash curl
COPY uptime-agent.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/uptime-agent.sh
ENTRYPOINT ["/usr/local/bin/uptime-agent.sh"]
EOF

# Build and run
docker build -t uptime-agent .
docker run -d --name uptime-agent uptime-agent -m 1 -a "https://monitor.sharber.me/api"
```

## Configuration Examples

### Example 1: Basic Server Monitoring
```bash
./uptime-agent.sh -m 5 -a "https://monitor.company.com/api"
```

### Example 2: High-Frequency Monitoring
```bash
./uptime-agent.sh -m 10 -a "https://monitor.company.com/api" -i 30
```

### Example 3: Development/Testing
```bash
./uptime-agent.sh -m 1 -a "http://localhost:5000/api" --run-once --verbose
```

### Example 4: Custom Log Lines
```bash
./uptime-agent.sh -m 1 -a "https://monitor.company.com/api" -l 200
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Permission Denied
```
Error: Permission denied
```

**Solution:**
```bash
chmod +x uptime-agent.sh
# OR if downloaded to system directory
sudo chmod +x /usr/local/bin/uptime-agent.sh
```

#### 2. Command Not Found
```
Error: curl: command not found
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install curl

# CentOS/RHEL
sudo yum install curl

# Alpine
apk add curl

# Arch Linux
sudo pacman -S curl
```

#### 3. SSL Certificate Errors
The script automatically bypasses SSL certificate validation, but if you encounter issues:

```bash
# Force SSL bypass (already enabled by default)
./uptime-agent.sh -m 1 -a "https://your-server.com/api" --skip-ssl
```

#### 4. Network Connectivity Issues
```bash
# Test connectivity manually
curl -k "https://monitor.sharber.me/api/monitors/1"

# Check if ports are accessible
nc -zv monitor.sharber.me 443

# Test with wget
wget --no-check-certificate "https://monitor.sharber.me/api"
```

#### 5. Missing System Commands
If basic commands are missing:

```bash
# Check if required commands exist
which curl df free bash

# Install missing packages
# Ubuntu/Debian
sudo apt install coreutils curl bash

# CentOS/RHEL
sudo yum install coreutils curl bash

# Alpine (minimal install)
apk add coreutils curl bash
```

### Debug Mode
Enable verbose logging to troubleshoot issues:

```bash
./uptime-agent.sh -m 1 -a "https://monitor.sharber.me/api" --verbose --run-once
```

This will:
- Show detailed HTTP request/response information
- Display system metrics collection details
- Log all API interactions
- Write events to system log (syslog)

## Security Considerations

### File Permissions
The script should have appropriate permissions:

```bash
# Make executable for owner and group
chmod 755 uptime-agent.sh

# For system installation
sudo chown root:root /usr/local/bin/uptime-agent.sh
sudo chmod 755 /usr/local/bin/uptime-agent.sh
```

### Network Security
- Agent communicates over HTTPS (SSL bypass only for certificate validation)
- Uses Bearer token authentication
- No sensitive data stored locally

### User Permissions
- Standard user permissions sufficient for basic monitoring
- Root permissions required for:
  - Installing as system service
  - Writing to system directories
  - Reading certain system files

## Performance Impact

The Linux shell agent is designed to be extremely lightweight:
- **Memory usage**: ~5-15 MB
- **CPU usage**: <0.5% during data collection
- **Network usage**: ~1-3 KB per check cycle
- **Disk I/O**: Minimal (only for log file reading)

## Monitoring Capabilities

### System Metrics Collected:
- **CPU Usage**: Processor utilization from `/proc/stat`
- **Memory Usage**: RAM utilization from `/proc/meminfo`
- **Disk Usage**: Free/used space for all mounted filesystems
- **Network Statistics**: Bytes/packets from `/proc/net/dev`

### Log File Monitoring:
- Configurable in the web interface
- Reads last N lines (default: 100)
- Supports multiple log files
- Handles file access errors gracefully

### Command Execution:
- Bash/shell commands (default)
- Output capture and error handling
- Configurable timeout
- Full stderr/stdout capture

## Comparison: Shell Script vs Python Agent

| Feature | Shell Script Agent | Python Agent |
|---------|-------------------|--------------|
| **Installation** | No installation needed | Requires Python + packages |
| **SSL Issues** | Auto-handled with curl -k | Compilation needed |
| **Performance** | Minimal resource usage | Higher memory usage |
| **Deployment** | Copy single file | Build executable |
| **Maintenance** | Edit text file directly | Recompile executable |
| **Debugging** | Plain text, easy to debug | Compiled binary |
| **Linux Integration** | Excellent (native commands) | Good (via libraries) |
| **Compatibility** | Any Linux with bash/curl | Specific Python versions |

## Advanced Usage

### Environment Variables
Set default values using environment variables:

```bash
export UPTIME_MONITOR_ID=123
export UPTIME_API_ENDPOINT=https://monitor.sharber.me/api
export UPTIME_INTERVAL=60

# Run with environment defaults
./uptime-agent.sh
```

### Custom Configuration File
Create a configuration file:

```bash
# Create config file
cat > /etc/uptime-agent.conf <<EOF
MONITOR_ID=123
API_ENDPOINT=https://monitor.sharber.me/api
INTERVAL=60
VERBOSE=true
EOF

# Modify script to source config (or create wrapper)
#!/bin/bash
source /etc/uptime-agent.conf
exec ./uptime-agent.sh -m "$MONITOR_ID" -a "$API_ENDPOINT" -i "$INTERVAL" $([ "$VERBOSE" = "true" ] && echo "--verbose")
```

### Integration with Monitoring Systems
The script can be integrated with other monitoring systems:

```bash
# Send metrics to multiple systems
./uptime-agent.sh -m 1 -a "https://primary-monitor.com/api" &
./uptime-agent.sh -m 2 -a "https://backup-monitor.com/api" &
```

### Log Rotation
For continuous operation, consider log rotation:

```bash
# Add to /etc/logrotate.d/uptime-agent
/var/log/uptime-agent.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 nobody nogroup
    postrotate
        systemctl reload uptime-agent
    endscript
}
```

## Migration from Python Agent

To switch from the Python agent to the shell script:

1. **Stop the Python agent**
2. **Download the shell script**:
   ```bash
   wget https://your-server.com/download-prebuilt-agent?platform=linux -O uptime-agent.sh
   chmod +x uptime-agent.sh
   ```
3. **Test the connection**:
   ```bash
   ./uptime-agent.sh -m YOUR_ID -a "YOUR_SERVER/api" --run-once --verbose
   ```
4. **Deploy using your preferred method** (systemd service, cron, etc.)
5. **Verify monitoring** in your dashboard

## Support and Updates

### Getting Help
- Check the verbose logs: `--verbose` parameter
- Test connectivity: `--run-once` parameter
- Verify server reachability independently
- Check system requirements with standard Linux commands

### Script Updates
The shell script can be updated by simply replacing the file. No recompilation needed.

### Common Commands for Management
```bash
# View running agents
ps aux | grep uptime-agent

# Kill running agent
pkill -f uptime-agent

# Check systemd service status
systemctl status uptime-agent

# View service logs
journalctl -u uptime-agent -f

# Restart service
systemctl restart uptime-agent
```

---

*Linux Uptime Agent - Native Shell Script Monitoring Solution*
