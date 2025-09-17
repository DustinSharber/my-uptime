# PowerShell Uptime Agent - Deployment Guide

## Overview
The PowerShell uptime agent is a native Windows monitoring solution that eliminates SSL certificate issues and Python dependency requirements. It uses built-in Windows capabilities for system monitoring and HTTP communication.

## Features
- **Native Windows Integration**: Uses PowerShell and Windows Performance Counters
- **SSL Certificate Bypass**: Handles self-signed certificates automatically
- **No Dependencies**: Runs on any Windows machine with PowerShell (built into Windows)
- **System Monitoring**: CPU, RAM, disk usage, and network statistics
- **Log File Monitoring**: Reads and sends log file contents
- **Command Execution**: Execute PowerShell or CMD commands remotely
- **Error Recovery**: Automatic retry logic and detailed logging

## Requirements
- Windows 7/2008 R2 or newer
- PowerShell 3.0+ (included in Windows 8/2012+)
- Network connectivity to your monitoring server
- No additional software installation required

## Quick Start

### 1. Basic Usage
```powershell
# Run the agent (replace values with your actual settings)
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "https://monitor.sharber.me"
```

### 2. Test Mode (Single Run)
```powershell
# Test the agent with a single data collection cycle
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "https://monitor.sharber.me" -RunOnce
```

### 3. Verbose Logging
```powershell
# Enable detailed logging for troubleshooting
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "https://monitor.sharber.me" -Verbose
```

## Command Line Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `-MonitorId` | Yes | - | Monitor ID from your dashboard |
| `-ApiEndpoint` | Yes | - | Your monitoring server URL |
| `-Interval` | No | 60 | Check interval in seconds |
| `-LogLines` | No | 100 | Number of log lines to read |
| `-SkipSSLCheck` | No | $true | Bypass SSL certificate validation |
| `-RunOnce` | No | $false | Run once and exit (for testing) |
| `-Verbose` | No | $false | Enable verbose logging |

## Deployment Methods

### Method 1: Manual Execution
```powershell
# Download the script to a folder
# Run directly
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "https://your-server.com"
```

### Method 2: Windows Scheduled Task
Create a scheduled task to run the agent automatically:

```powershell
# Create scheduled task (run as Administrator)
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -File `"C:\Tools\uptime-agent.ps1`" -MonitorId 1 -ApiEndpoint `"https://monitor.sharber.me`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "UptimeAgent" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Uptime Monitoring Agent"
```

### Method 3: Windows Service (Advanced)
For production environments, wrap the PowerShell script in a Windows service:

1. Install NSSM (Non-Sucking Service Manager): https://nssm.cc/
2. Create service:
```cmd
nssm install UptimeAgent
# Set Application: C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
# Set Arguments: -ExecutionPolicy Bypass -File "C:\Tools\uptime-agent.ps1" -MonitorId 1 -ApiEndpoint "https://monitor.sharber.me"
# Set working directory: C:\Tools
nssm start UptimeAgent
```

### Method 4: Background Process
```powershell
# Run in background (keeps running until you close PowerShell)
Start-Job -ScriptBlock { 
    & "C:\Tools\uptime-agent.ps1" -MonitorId 1 -ApiEndpoint "https://monitor.sharber.me" 
}
```

## Configuration Examples

### Example 1: Basic Server Monitoring
```powershell
.\uptime-agent.ps1 -MonitorId 5 -ApiEndpoint "https://monitor.company.com"
```

### Example 2: High-Frequency Monitoring
```powershell
.\uptime-agent.ps1 -MonitorId 10 -ApiEndpoint "https://monitor.company.com" -Interval 30
```

### Example 3: Development/Testing
```powershell
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "http://localhost:5000" -RunOnce -Verbose
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Execution Policy Error
```
Error: cannot be loaded because running scripts is disabled on this system
```

**Solution:**
```powershell
# Run as Administrator
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
# OR run with bypass
powershell -ExecutionPolicy Bypass -File .\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "https://your-server.com"
```

#### 2. SSL Certificate Errors
The script automatically bypasses SSL certificate validation, but if you encounter issues:

```powershell
# Force SSL bypass
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "https://your-server.com" -SkipSSLCheck
```

#### 3. Docker Container Connectivity Issues
When connecting from Windows to a server running in Docker, the agent automatically handles hostname conversion:

```powershell
# ✅ These work automatically (converted internally):
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "http://localhost:5000"
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "http://127.0.0.1:5000"

# ✅ Or use Docker networking directly:
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "http://host.docker.internal:5000"
```

**Docker Fixes Included:**
- Automatic `localhost` → `host.docker.internal` conversion
- Enhanced retry logic (3 attempts with progressive backoff)
- Better error handling for Docker networking timeouts
- JSON serialization improvements for Docker API compatibility

#### 4. Network Connectivity Issues
```powershell
# Test connectivity manually
Test-NetConnection -ComputerName "monitor.sharber.me" -Port 443
# OR test HTTP
Invoke-RestMethod -Uri "https://monitor.sharber.me/api" -Method GET -SkipCertificateCheck
```

#### 4. Performance Counter Access Issues
If running as a service, ensure the service account has performance counter access:

```powershell
# Add user to Performance Monitor Users group
net localgroup "Performance Monitor Users" "YOUR_SERVICE_ACCOUNT" /add
```

### Debug Mode
Enable verbose logging to troubleshoot issues:

```powershell
.\uptime-agent.ps1 -MonitorId 1 -ApiEndpoint "https://monitor.sharber.me" -Verbose -RunOnce
```

This will:
- Show detailed HTTP request/response information
- Display system metrics collection details
- Log all API interactions
- Write events to Windows Event Log

## Security Considerations

### Execution Policy
The script may require relaxed execution policy. Options:
1. `Set-ExecutionPolicy RemoteSigned` (recommended)
2. Use `-ExecutionPolicy Bypass` parameter
3. Sign the script with a code signing certificate

### Network Security
- Agent communicates over HTTPS (SSL bypass only for certificate validation)
- Uses Bearer token authentication
- No sensitive data stored locally

### Permissions
- Standard user permissions sufficient for basic monitoring
- Administrator permissions required for:
  - Creating scheduled tasks
  - Installing as Windows service
  - Writing to Event Log

## Performance Impact

The PowerShell agent is designed to be lightweight:
- **Memory usage**: ~20-50 MB
- **CPU usage**: <1% during data collection
- **Network usage**: ~1-5 KB per check cycle
- **Disk I/O**: Minimal (only for log file reading)

## Monitoring Capabilities

### System Metrics Collected:
- **CPU Usage**: Processor utilization percentage
- **Memory Usage**: RAM utilization percentage  
- **Disk Usage**: Free/used space for all drives
- **Network Statistics**: Bytes/packets sent and received

### Log File Monitoring:
- Configurable in the web interface
- Reads last N lines (default: 100)
- Supports multiple log files
- Handles file access errors gracefully

### Command Execution:
- PowerShell commands (default)
- CMD/Batch commands
- Output capture and error handling
- Configurable timeout (5 minutes)

## Comparison: PowerShell vs Python Agent

| Feature | PowerShell Agent | Python Agent |
|---------|------------------|--------------|
| **Installation** | No installation needed | Requires Python + packages |
| **SSL Issues** | Auto-handled | Compilation needed |
| **Performance** | Native Windows optimization | Generic cross-platform |
| **Deployment** | Copy single file | Build executable |
| **Maintenance** | Edit text file | Recompile executable |
| **Debugging** | Plain text, easy to modify | Compiled binary |
| **Windows Integration** | Excellent (native WMI/CIM) | Good (via libraries) |

## Migration from Python Agent

To switch from the Python agent to PowerShell:

1. **Stop the Python agent**
2. **Copy the PowerShell script** to your target machine
3. **Test the connection**:
   ```powershell
   .\uptime-agent.ps1 -MonitorId YOUR_ID -ApiEndpoint "YOUR_SERVER" -RunOnce
   ```
4. **Deploy using your preferred method** (scheduled task, service, etc.)
5. **Verify monitoring** in your dashboard

## Support and Updates

### Getting Help
- Check the verbose logs: `-Verbose` parameter
- Test connectivity: `-RunOnce` parameter  
- Verify server reachability independently

### Script Updates
The PowerShell script can be updated by simply replacing the file. No recompilation needed.

---

*PowerShell Uptime Agent - Native Windows Monitoring Solution*
