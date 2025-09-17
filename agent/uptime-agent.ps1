# Uptime Monitoring Agent - PowerShell Edition
# Native Windows monitoring agent with SSL bypass support

param(
    [Parameter(Mandatory=$true, HelpMessage="Monitor ID from your uptime dashboard")]
    [int]$MonitorId,
    
    [Parameter(Mandatory=$true, HelpMessage="API endpoint URL (e.g., https://monitor.sharber.me/api)")]
    [string]$ApiEndpoint,
    
    [Parameter(HelpMessage="Check interval in seconds")]
    [int]$Interval = 60,
    
    [Parameter(HelpMessage="Number of log lines to read")]
    [int]$LogLines = 100,
    
    [Parameter(HelpMessage="Skip SSL certificate validation")]
    [switch]$SkipSSLCheck = $true,
    
    [Parameter(HelpMessage="Run once and exit (for testing)")]
    [switch]$RunOnce = $false,
    
    [Parameter(HelpMessage="Enable verbose logging")]
    [switch]$VerboseLogging = $false
)

# Global configuration
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Ensure API endpoint ends with /api
if (-not $ApiEndpoint.EndsWith("/api")) {
    $ApiEndpoint = $ApiEndpoint.TrimEnd('/') + "/api"
}

# Function to write timestamped log messages
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    switch ($Level) {
        "ERROR" { Write-Host $logMessage -ForegroundColor Red }
        "WARNING" { Write-Host $logMessage -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logMessage -ForegroundColor Green }
        default { Write-Host $logMessage -ForegroundColor White }
    }
    
    if ($VerboseLogging) {
        # Also write to Windows Event Log if verbose
        try {
            Write-EventLog -LogName Application -Source "UptimeAgent" -EntryType Information -EventId 1000 -Message $logMessage -ErrorAction SilentlyContinue
        } catch {
            # Ignore event log errors
        }
    }
}

# Function to bypass SSL certificate validation
function Set-SSLBypass {
    if ($SkipSSLCheck) {
        Write-Log "Configuring SSL certificate bypass for self-signed certificates"
        
        # For PowerShell 5.1 and earlier
        if ($PSVersionTable.PSVersion.Major -le 5) {
            try {
                [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
                [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls11 -bor [System.Net.SecurityProtocolType]::Tls
                Write-Log "SSL bypass configured for PowerShell 5.1" "SUCCESS"
            } catch {
                Write-Log "Failed to configure SSL bypass: $($_.Exception.Message)" "WARNING"
            }
        }
    }
}

# Function to make HTTP requests with proper error handling
function Invoke-APIRequest {
    param(
        [string]$Uri,
        [string]$Method = "GET",
        [hashtable]$Headers = @{},
        [object]$Body = $null,
        [int]$TimeoutSec = 30
    )
    
    try {
        # Convert localhost to host.docker.internal for Docker compatibility
        $adjustedUri = $Uri
        if ($Uri -match "localhost|127\.0\.0\.1") {
            Write-Log "Converting localhost to host.docker.internal for Docker compatibility" "INFO"
            $adjustedUri = $Uri -replace "localhost", "host.docker.internal" -replace "127\.0\.0\.1", "host.docker.internal"
        }
        
        $requestParams = @{
            Uri = $adjustedUri
            Method = $Method
            Headers = $Headers
            TimeoutSec = $TimeoutSec
            UseBasicParsing = $true
            MaximumRedirection = 5
        }
        
        # Add SSL bypass for PowerShell Core/7+
        if ($PSVersionTable.PSVersion.Major -ge 6 -and $SkipSSLCheck) {
            $requestParams.SkipCertificateCheck = $true
        }
        
        if ($Body) {
            if ($Body -is [hashtable] -or $Body -is [pscustomobject]) {
                $jsonBody = $Body | ConvertTo-Json -Depth 10 -Compress
                $requestParams.Body = $jsonBody
                $requestParams.ContentType = "application/json; charset=utf-8"
                
                if ($VerboseLogging) {
                    Write-Log "Request body: $($jsonBody.Substring(0, [Math]::Min(200, $jsonBody.Length)))" "INFO"
                }
            } else {
                $requestParams.Body = $Body
            }
        }
        
        if ($VerboseLogging) {
            Write-Log "Making $Method request to: $adjustedUri" "INFO"
        }
        
        $response = Invoke-RestMethod @requestParams
        
        if ($VerboseLogging) {
            $responseType = if ($response) { $response.GetType().Name } else { "null" }
            Write-Log "Request successful. Response type: $responseType" "SUCCESS"
        }
        
        return @{ Success = $true; Data = $response; Error = $null }
    }
    catch {
        $errorMessage = $_.Exception.Message
        $statusCode = "Unknown"
        
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            
            # Try to read response body for more details
            try {
                $responseStream = $_.Exception.Response.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($responseStream)
                $responseBody = $reader.ReadToEnd()
                $reader.Close()
                $responseStream.Close()
                
                if ($responseBody) {
                    $errorMessage += " | Response: $responseBody"
                }
            } catch {
                # Ignore errors reading response body
            }
        }
        
        $fullError = "HTTP $statusCode - $errorMessage"
        
        if ($VerboseLogging) {
            Write-Log "Request failed: $fullError" "ERROR"
        }
        
        return @{ Success = $false; Data = $null; Error = $fullError }
    }
}

# Function to get monitor configuration from server
function Get-MonitorConfig {
    Write-Log "Fetching monitor configuration..."
    
    $headers = @{
        'Authorization' = "Bearer $MonitorId"
    }
    
    $result = Invoke-APIRequest -Uri "$ApiEndpoint/monitors/$MonitorId" -Headers $headers
    
    if ($result.Success) {
        Write-Log "Monitor configuration retrieved successfully" "SUCCESS"
        return $result.Data
    } else {
        Write-Log "Failed to fetch monitor config: $($result.Error)" "ERROR"
        return $null
    }
}

# Function to collect system metrics using native Windows commands
function Get-SystemMetrics {
    Write-Log "Collecting system metrics..." -Level "INFO"
    
    $metrics = @{
        cpu_percent = 0
        ram_percent = 0
        disks = @{}
        network = @{}
    }
    
    try {
        # Get CPU usage
        $cpu = Get-Counter "\Processor(_Total)\% Processor Time" -SampleInterval 1 -MaxSamples 2 -ErrorAction SilentlyContinue
        if ($cpu) {
            $metrics.cpu_percent = [math]::Round($cpu[-1].CounterSamples[0].CookedValue, 2)
        }
    }
    catch {
        Write-Log "Failed to get CPU metrics: $($_.Exception.Message)" "WARNING"
    }
    
    try {
        # Get memory usage
        $memory = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue
        if ($memory) {
            $totalMemory = $memory.TotalVisibleMemorySize * 1024
            $freeMemory = $memory.FreePhysicalMemory * 1024
            $usedMemory = $totalMemory - $freeMemory
            $metrics.ram_percent = [math]::Round(($usedMemory / $totalMemory) * 100, 2)
        }
    }
    catch {
        Write-Log "Failed to get memory metrics: $($_.Exception.Message)" "WARNING"
    }
    
    try {
        # Get disk usage
        $disks = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction SilentlyContinue
        foreach ($disk in $disks) {
            if ($disk.Size -gt 0) {
                $metrics.disks[$disk.DeviceID] = @{
                    total = $disk.Size
                    used = $disk.Size - $disk.FreeSpace
                    free = $disk.FreeSpace
                    percent = [math]::Round((($disk.Size - $disk.FreeSpace) / $disk.Size) * 100, 2)
                    mountpoint = $disk.DeviceID
                    fstype = $disk.FileSystem
                }
            }
        }
    }
    catch {
        Write-Log "Failed to get disk metrics: $($_.Exception.Message)" "WARNING"
    }
    
    try {
        # Get network statistics
        $networkAdapters = Get-CimInstance -ClassName Win32_PerfRawData_Tcpip_NetworkInterface -ErrorAction SilentlyContinue | 
                          Where-Object { $_.Name -notlike "*Loopback*" -and $_.Name -notlike "*isatap*" -and $_.BytesTotalPerSec -gt 0 }
        
        foreach ($adapter in $networkAdapters) {
            $adapterName = $adapter.Name -replace '[^a-zA-Z0-9_-]', '_'
            $metrics.network[$adapterName] = @{
                bytes_sent = $adapter.BytesSentPerSec
                bytes_recv = $adapter.BytesReceivedPerSec
                packets_sent = $adapter.PacketsSentPerSec
                packets_recv = $adapter.PacketsReceivedPerSec
            }
        }
    }
    catch {
        Write-Log "Failed to get network metrics: $($_.Exception.Message)" "WARNING"
    }
    
    Write-Log "System metrics collected: CPU: $($metrics.cpu_percent)%, RAM: $($metrics.ram_percent)%, Disks: $($metrics.disks.Count), Network: $($metrics.network.Count)" "SUCCESS"
    return $metrics
}

# Function to read log files
function Get-LogData {
    param([string[]]$LogFiles)
    
    $logs = @{}
    
    if (-not $LogFiles) {
        return $logs
    }
    
    foreach ($logFile in $LogFiles) {
        $logFile = $logFile.Trim()
        if (-not $logFile) { continue }
        
        Write-Log "Reading log file: $logFile"
        
        try {
            if (Test-Path $logFile) {
                $content = Get-Content $logFile -Tail $LogLines -ErrorAction Stop
                $logs[$logFile] = $content
                Write-Log "Read $($content.Count) lines from $logFile" "SUCCESS"
            } else {
                $errorMsg = "Log file not found: $logFile"
                Write-Log $errorMsg "WARNING"
                $logs[$logFile] = @($errorMsg)
            }
        }
        catch {
            $errorMsg = "Error reading log file $logFile`: $($_.Exception.Message)"
            Write-Log $errorMsg "ERROR"
            $logs[$logFile] = @($errorMsg)
        }
    }
    
    return $logs
}

# Function to send data to server with retry logic
function Send-Data {
    param([hashtable]$Data, [int]$MaxRetries = 3)
    
    Write-Log "Sending data to server..."
    
    # Ensure all data is properly serializable for JSON
    $cleanData = @{
        timestamp = $Data.timestamp
        metrics = @{
            cpu_percent = [double]$Data.metrics.cpu_percent
            ram_percent = [double]$Data.metrics.ram_percent
            disks = @{}
            network = @{}
        }
        logs = @{}
    }
    
    # Clean disk data
    foreach ($diskKey in $Data.metrics.disks.Keys) {
        $disk = $Data.metrics.disks[$diskKey]
        $cleanData.metrics.disks[$diskKey] = @{
            total = [long]$disk.total
            used = [long]$disk.used
            free = [long]$disk.free
            percent = [double]$disk.percent
            mountpoint = [string]$disk.mountpoint
            fstype = [string]$disk.fstype
        }
    }
    
    # Clean network data
    foreach ($netKey in $Data.metrics.network.Keys) {
        $net = $Data.metrics.network[$netKey]
        $cleanData.metrics.network[$netKey] = @{
            bytes_sent = [long]$net.bytes_sent
            bytes_recv = [long]$net.bytes_recv
            packets_sent = [long]$net.packets_sent
            packets_recv = [long]$net.packets_recv
        }
    }
    
    # Clean log data (convert arrays to strings if needed)
    foreach ($logKey in $Data.logs.Keys) {
        $logData = $Data.logs[$logKey]
        if ($logData -is [array]) {
            $cleanData.logs[$logKey] = $logData -join "`n"
        } else {
            $cleanData.logs[$logKey] = [string]$logData
        }
    }
    
    $headers = @{
        'Authorization' = "Bearer $MonitorId"
        'Content-Type' = 'application/json'
    }
    
    if ($VerboseLogging) {
        Write-Log "Payload metrics: CPU=$($cleanData.metrics.cpu_percent)%, RAM=$($cleanData.metrics.ram_percent)%, Disks=$($cleanData.metrics.disks.Count), Net=$($cleanData.metrics.network.Count)" "INFO"
    }
    
    # Retry logic for Docker networking issues
    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        $result = Invoke-APIRequest -Uri "$ApiEndpoint/agent/data" -Method "POST" -Headers $headers -Body $cleanData
        
        if ($result.Success) {
            if ($attempt -gt 1) {
                Write-Log "Data sent successfully on attempt $attempt" "SUCCESS"
            } else {
                Write-Log "Data sent successfully" "SUCCESS"
            }
            return $true
        } else {
            if ($attempt -lt $MaxRetries) {
                $waitTime = [Math]::Min(5 * $attempt, 30) # Progressive backoff: 5s, 10s, 15s...
                Write-Log "Attempt $attempt failed: $($result.Error). Retrying in $waitTime seconds..." "WARNING"
                Start-Sleep -Seconds $waitTime
            } else {
                Write-Log "All $MaxRetries attempts failed. Last error: $($result.Error)" "ERROR"
                return $false
            }
        }
    }
    
    return $false
}

# Function to fetch and execute commands
function Handle-Commands {
    Write-Log "Checking for pending commands..."
    
    $headers = @{
        'Authorization' = "Bearer $MonitorId"
    }
    
    # Fetch commands
    $result = Invoke-APIRequest -Uri "$ApiEndpoint/agent/commands" -Headers $headers
    
    if (-not $result.Success) {
        Write-Log "Failed to fetch commands: $($result.Error)" "ERROR"
        return
    }
    
    $commands = $result.Data
    if (-not $commands -or $commands.Count -eq 0) {
        return
    }
    
    Write-Log "Found $($commands.Count) pending command(s)" "INFO"
    
    foreach ($command in $commands) {
        Write-Log "Executing command ID: $($command.id)"
        
        $commandResult = Execute-Command -Command $command
        Update-CommandStatus -CommandId $command.id -Result $commandResult
    }
}

# Function to execute a command
function Execute-Command {
    param([object]$Command)
    
    $script = $Command.script
    $shellType = if ($Command.shell_type) { $Command.shell_type } else { "powershell" }
    
    if (-not $script) {
        return @{ status = "error"; output = "Empty script." }
    }
    
    Write-Log "Executing $shellType command: $($script.Substring(0, [Math]::Min(50, $script.Length)))..."
    
    try {
        $output = ""
        $status = "completed"
        
        if ($shellType -eq "powershell") {
            # Execute PowerShell command
            $result = Invoke-Expression $script 2>&1 | Out-String
            $output = $result
        }
        elseif ($shellType -eq "cmd") {
            # Execute CMD command
            $result = cmd /c $script 2>&1 | Out-String
            $output = $result
        }
        else {
            # Default to PowerShell
            $result = Invoke-Expression $script 2>&1 | Out-String
            $output = $result
        }
        
        # Check if there were errors (this is a simple check)
        if ($output -match "Exception|Error:|Fatal") {
            $status = "failed"
        }
        
        Write-Log "Command executed with status: $status" "SUCCESS"
        
        return @{
            status = $status
            output = $output
        }
    }
    catch {
        $errorOutput = $_.Exception.Message
        Write-Log "Command execution failed: $errorOutput" "ERROR"
        
        return @{
            status = "failed"
            output = $errorOutput
        }
    }
}

# Function to update command status
function Update-CommandStatus {
    param([int]$CommandId, [hashtable]$Result)
    
    Write-Log "Updating status for command $CommandId"
    
    $headers = @{
        'Authorization' = "Bearer $MonitorId"
        'Content-Type' = 'application/json'
    }
    
    $payload = @{
        status = $Result.status
        output = $Result.output
    }
    
    $updateResult = Invoke-APIRequest -Uri "$ApiEndpoint/agent/commands/$CommandId/update" -Method "POST" -Headers $headers -Body $payload
    
    if ($updateResult.Success) {
        Write-Log "Command $CommandId status updated successfully" "SUCCESS"
    } else {
        Write-Log "Failed to update command $CommandId status: $($updateResult.Error)" "ERROR"
    }
}

# Function to test connectivity
function Test-Connectivity {
    Write-Log "Testing connectivity to server..."
    
    $headers = @{
        'Authorization' = "Bearer $MonitorId"
    }
    
    $result = Invoke-APIRequest -Uri "$ApiEndpoint/monitors/$MonitorId" -Headers $headers -TimeoutSec 10
    
    if ($result.Success) {
        Write-Log "Connectivity test successful" "SUCCESS"
        return $true
    } else {
        Write-Log "Connectivity test failed: $($result.Error)" "ERROR"
        return $false
    }
}

# Main execution function
function Start-Monitoring {
    Write-Log "=== Uptime Agent Starting ===" "INFO"
    Write-Log "Monitor ID: $MonitorId" "INFO"
    Write-Log "API Endpoint: $ApiEndpoint" "INFO"
    Write-Log "Check Interval: $Interval seconds" "INFO"
    Write-Log "PowerShell Version: $($PSVersionTable.PSVersion)" "INFO"
    
    # Configure SSL bypass
    Set-SSLBypass
    
    # Test initial connectivity
    if (-not (Test-Connectivity)) {
        Write-Log "Initial connectivity test failed. Continuing anyway..." "WARNING"
    }
    
    # Get initial monitor configuration
    $config = Get-MonitorConfig
    $logFiles = @()
    
    if ($config -and $config.log_files) {
        $logFiles = $config.log_files -split ','
        Write-Log "Monitoring $($logFiles.Count) log file(s)" "INFO"
    }
    
    Write-Log "Agent initialized. Starting monitoring loop..." "SUCCESS"
    
    do {
        try {
            # Collect system metrics
            $metrics = Get-SystemMetrics
            
            # Read log files
            $logs = Get-LogData -LogFiles $logFiles
            
            # Prepare payload
            $payload = @{
                timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
                metrics = $metrics
                logs = $logs
            }
            
            # Send data
            Send-Data -Data $payload
            
            # Handle commands
            Handle-Commands
            
            if ($RunOnce) {
                Write-Log "Run-once mode, exiting..." "INFO"
                break
            }
            
            # Wait for next interval
            Write-Log "Waiting $Interval seconds until next check..."
            Start-Sleep -Seconds $Interval
        }
        catch {
            Write-Log "Unexpected error in monitoring loop: $($_.Exception.Message)" "ERROR"
            Write-Log "Waiting 30 seconds before retry..." "WARNING"
            Start-Sleep -Seconds 30
        }
    } while ($true)
}

# Script entry point
if ($MyInvocation.InvocationName -ne '.') {
    # Display banner
    Write-Host @"
===================================================
    Uptime Monitoring Agent - PowerShell Edition
===================================================
Monitor ID: $MonitorId
Server: $ApiEndpoint
SSL Bypass: $SkipSSLCheck
===================================================
"@ -ForegroundColor Cyan

    # Validate parameters
    if ($MonitorId -le 0) {
        Write-Log "Invalid Monitor ID. Must be a positive integer." "ERROR"
        exit 1
    }
    
    if (-not $ApiEndpoint -or $ApiEndpoint -notmatch "^https?://") {
        Write-Log "Invalid API Endpoint. Must be a valid HTTP/HTTPS URL." "ERROR"
        exit 1
    }
    
    # Start monitoring
    try {
        Start-Monitoring
    }
    catch {
        Write-Log "Fatal error: $($_.Exception.Message)" "ERROR"
        exit 1
    }
}
