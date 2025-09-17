# Debug script to check what Cloudflare is actually returning

param(
    [Parameter(Mandatory=$true)]
    [int]$MonitorId,
    
    [Parameter(Mandatory=$true)]
    [string]$ApiEndpoint
)

# Configure TLS 1.2+
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

Write-Host "=== Debugging Cloudflare Responses ===" -ForegroundColor Yellow

# Ensure endpoint ends with /api
if (-not $ApiEndpoint.EndsWith("/api")) {
    $ApiEndpoint = $ApiEndpoint.TrimEnd('/') + "/api"
}

$headers = @{
    'Authorization' = "Bearer $MonitorId"
    'Content-Type' = 'application/json'
    'User-Agent' = 'UptimeAgent-PowerShell/1.0 (Windows; PowerShell 5.1)'
}

Write-Host "`n1. Testing monitor config endpoint..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "$ApiEndpoint/monitors/$MonitorId" -Headers $headers -Method GET -UseBasicParsing
    
    Write-Host "Status Code: $($response.StatusCode)" -ForegroundColor White
    Write-Host "Content-Type: $($response.Headers['Content-Type'])" -ForegroundColor White
    Write-Host "Content-Length: $($response.Content.Length)" -ForegroundColor White
    Write-Host "Server: $($response.Headers['Server'])" -ForegroundColor White
    Write-Host "CF-Ray: $($response.Headers['CF-Ray'])" -ForegroundColor White
    
    Write-Host "`nResponse Content (first 500 chars):" -ForegroundColor Yellow
    $contentPreview = $response.Content.Substring(0, [Math]::Min(500, $response.Content.Length))
    Write-Host $contentPreview -ForegroundColor Gray
    
    # Check if it's HTML (Cloudflare error page)
    if ($response.Content -match '<html|<!DOCTYPE') {
        Write-Host "`n⚠️  WARNING: Response is HTML, not JSON!" -ForegroundColor Red
        Write-Host "This indicates Cloudflare is returning an error page instead of API data." -ForegroundColor Red
    } elseif ($response.Content -match '^\s*{.*}\s*$') {
        Write-Host "`n✓ Response appears to be JSON" -ForegroundColor Green
    } else {
        Write-Host "`n⚠️  Response format unknown" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "Status Code: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
    }
}

Write-Host "`n2. Testing data submission endpoint..." -ForegroundColor Cyan
try {
    $testData = @{
        timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        metrics = @{
            cpu_percent = 25.0
            ram_percent = 60.0
            disks = @{}
            network = @{}
        }
        logs = @{}
    }
    
    $jsonBody = $testData | ConvertTo-Json -Depth 5
    
    $response = Invoke-WebRequest -Uri "$ApiEndpoint/agent/data" -Headers $headers -Method POST -Body $jsonBody -UseBasicParsing
    
    Write-Host "Status Code: $($response.StatusCode)" -ForegroundColor White
    Write-Host "Content-Type: $($response.Headers['Content-Type'])" -ForegroundColor White
    Write-Host "Content-Length: $($response.Content.Length)" -ForegroundColor White
    Write-Host "Server: $($response.Headers['Server'])" -ForegroundColor White
    Write-Host "CF-Ray: $($response.Headers['CF-Ray'])" -ForegroundColor White
    
    Write-Host "`nResponse Content:" -ForegroundColor Yellow
    Write-Host $response.Content -ForegroundColor Gray
    
    # Check if it's HTML (Cloudflare error page)
    if ($response.Content -match '<html|<!DOCTYPE') {
        Write-Host "`n⚠️  WARNING: Response is HTML, not JSON!" -ForegroundColor Red
        Write-Host "This indicates Cloudflare is blocking the API request." -ForegroundColor Red
        
        # Look for specific Cloudflare errors
        if ($response.Content -match 'Access denied|Error 1020|Ray ID') {
            Write-Host "🚨 CLOUDFLARE BLOCKING DETECTED!" -ForegroundColor Red
            Write-Host "Your Cloudflare settings are blocking API requests." -ForegroundColor Red
        }
    } elseif ($response.Content -match '^\s*{.*}\s*$') {
        Write-Host "`n✓ Response appears to be JSON - API working!" -ForegroundColor Green
    } else {
        Write-Host "`n⚠️  Response format unknown" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "Status Code: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
    }
}

Write-Host "`n3. Checking for Cloudflare-specific headers..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri $ApiEndpoint -Method GET -UseBasicParsing
    
    $cloudflareHeaders = @('CF-Ray', 'CF-Cache-Status', 'CF-Request-ID', 'Server')
    foreach ($header in $cloudflareHeaders) {
        if ($response.Headers[$header]) {
            Write-Host "$header" + ": " + "$($response.Headers[$header])" -ForegroundColor White
        }
    }
    
    if ($response.Headers['Server'] -match 'cloudflare') {
        Write-Host "`n✓ Confirmed: Traffic is going through Cloudflare" -ForegroundColor Green
    }
    
} catch {
    Write-Host "Could not check base endpoint" -ForegroundColor Yellow
}

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "If you see HTML responses above, your Cloudflare settings need adjustment:" -ForegroundColor White
Write-Host "1. Go to Cloudflare Dashboard > Security > WAF" -ForegroundColor Yellow
Write-Host "2. Add rule to 'Skip' protection for /api/* paths" -ForegroundColor Yellow
Write-Host "3. Or temporarily set Security Level to 'Essentially Off'" -ForegroundColor Yellow
Write-Host "4. Disable 'Bot Fight Mode' if enabled" -ForegroundColor Yellow
