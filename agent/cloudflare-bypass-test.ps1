# Test script to bypass Cloudflare Access by using direct server IP
# This helps determine if the issue is specifically with Cloudflare Access

param(
    [Parameter(Mandatory=$true)]
    [int]$MonitorId,
    
    [Parameter(Mandatory=$true)]
    [string]$Domain,
    
    [Parameter(HelpMessage="Direct server IP (if known)")]
    [string]$ServerIP = ""
)

Write-Host "=== Cloudflare Access Bypass Test ===" -ForegroundColor Yellow

# Configure TLS 1.2+
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

# If no IP provided, try to resolve domain
if (-not $ServerIP) {
    Write-Host "`nResolving IP for $Domain..." -ForegroundColor Cyan
    try {
        $resolved = [System.Net.Dns]::GetHostAddresses($Domain)
        $ServerIP = $resolved[0].IPAddressToString
        Write-Host "Resolved to: $ServerIP" -ForegroundColor Green
    } catch {
        Write-Host "Could not resolve domain. Please provide server IP manually." -ForegroundColor Red
        return
    }
}

$headers = @{
    'Authorization' = "Bearer $MonitorId"
    'Content-Type' = 'application/json'
    'Host' = $Domain  # Important: Keep the original domain in Host header
}

Write-Host "`nTesting direct IP connection..." -ForegroundColor Cyan
Write-Host "Domain: $Domain" -ForegroundColor White
Write-Host "Server IP: $ServerIP" -ForegroundColor White

# Test 1: Direct IP connection for monitor config
Write-Host "`n1. Testing monitor config via IP..." -ForegroundColor Yellow
try {
    $directUrl = "https://$ServerIP/api/monitors/$MonitorId"
    
    # For direct IP, we need to disable SSL verification since cert won't match IP
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    
    $response = Invoke-RestMethod -Uri $directUrl -Headers $headers -Method GET -UseBasicParsing
    
    Write-Host "✓ SUCCESS: Direct IP connection works!" -ForegroundColor Green
    Write-Host "Monitor config retrieved via IP bypass" -ForegroundColor Green
    
    # Test 2: Send test data via IP
    Write-Host "`n2. Testing data submission via IP..." -ForegroundColor Yellow
    
    $testData = @{
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        metrics = @{
            cpu_percent = 15.5
            ram_percent = 45.2
            disks = @{}
            network = @{}
        }
        logs = @{}
    }
    
    $jsonBody = $testData | ConvertTo-Json -Depth 5
    $dataUrl = "https://$ServerIP/api/agent/data"
    
    $dataResponse = Invoke-RestMethod -Uri $dataUrl -Headers $headers -Method POST -Body $jsonBody -UseBasicParsing
    
    Write-Host "✓ SUCCESS: Data submission via IP works!" -ForegroundColor Green
    Write-Host "Response: $($dataResponse | ConvertTo-Json -Compress)" -ForegroundColor Gray
    
    Write-Host "`n=== SOLUTION FOUND ===" -ForegroundColor Green
    Write-Host "Your monitoring agent can bypass Cloudflare Access by using:" -ForegroundColor White
    Write-Host "IP Address: $ServerIP instead of domain: $Domain" -ForegroundColor Yellow
    Write-Host "`nTo fix your agent permanently:" -ForegroundColor White
    Write-Host "1. Replace your ApiEndpoint with: https://$ServerIP/api" -ForegroundColor Yellow
    Write-Host "2. Or configure Cloudflare Access to bypass /api/* paths" -ForegroundColor Yellow
    
} catch {
    if ($_.Exception.Message -match "403|Access denied|Unauthorized") {
        Write-Host "❌ Direct IP also blocked - server-level restriction" -ForegroundColor Red
        Write-Host "You need to configure Cloudflare Access bypass for /api/* paths" -ForegroundColor Yellow
    } elseif ($_.Exception.Message -match "certificate|SSL") {
        Write-Host "⚠️  SSL certificate issue with direct IP (expected)" -ForegroundColor Yellow
        Write-Host "Try with -SkipSSLCheck in your main agent" -ForegroundColor Yellow
    } else {
        Write-Host "❌ Connection failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`n=== Cloudflare Access Configuration ===" -ForegroundColor Cyan
Write-Host "To properly fix this in Cloudflare:" -ForegroundColor White
Write-Host "1. Go to Cloudflare Dashboard > Zero Trust > Access > Applications" -ForegroundColor Yellow
Write-Host "2. Find your application ($Domain) and click Edit" -ForegroundColor Yellow
Write-Host "3. Add a new policy:" -ForegroundColor Yellow
Write-Host "   - Name: API Bypass" -ForegroundColor Yellow
Write-Host "   - Action: Bypass" -ForegroundColor Yellow
Write-Host "   - Application path: /api/*" -ForegroundColor Yellow
Write-Host "4. Save the policy" -ForegroundColor Yellow
