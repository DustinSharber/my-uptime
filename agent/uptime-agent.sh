#!/bin/bash

# Uptime Monitoring Agent - Linux Shell Script Edition
# Native Linux monitoring agent with SSL bypass support

# Default values
MONITOR_ID=""
API_ENDPOINT=""
INTERVAL=60
LOG_LINES=100
SKIP_SSL_CHECK=true
RUN_ONCE=false
VERBOSE_LOGGING=false

# Function to display usage
show_usage() {
    cat << EOF
Usage: $0 -m MONITOR_ID -a API_ENDPOINT [OPTIONS]

Required Parameters:
  -m, --monitor-id      Monitor ID from your uptime dashboard
  -a, --api-endpoint    API endpoint URL (e.g., https://monitor.sharber.me/api)

Options:
  -i, --interval        Check interval in seconds (default: 60)
  -l, --log-lines       Number of log lines to read (default: 100)
  -s, --skip-ssl        Skip SSL certificate validation (default: true)
  -o, --run-once        Run once and exit (for testing)
  -v, --verbose         Enable verbose logging
  -h, --help            Show this help message

Examples:
  $0 -m 1 -a "https://monitor.sharber.me/api"
  $0 -m 1 -a "http://localhost:5000/api" --run-once --verbose
EOF
}

# Function to write timestamped log messages
write_log() {
    local message="$1"
    local level="${2:-INFO}"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_message="[$timestamp] [$level] $message"
    
    case "$level" in
        "ERROR")
            echo -e "\033[31m$log_message\033[0m" ;;
        "WARNING")
            echo -e "\033[33m$log_message\033[0m" ;;
        "SUCCESS")
            echo -e "\033[32m$log_message\033[0m" ;;
        *)
            echo "$log_message" ;;
    esac
    
    # Write to syslog if verbose logging is enabled
    if [ "$VERBOSE_LOGGING" = true ]; then
        logger "UptimeAgent: $message"
    fi
}

# Function to parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--monitor-id)
                MONITOR_ID="$2"
                shift 2
                ;;
            -a|--api-endpoint)
                API_ENDPOINT="$2"
                shift 2
                ;;
            -i|--interval)
                INTERVAL="$2"
                shift 2
                ;;
            -l|--log-lines)
                LOG_LINES="$2"
                shift 2
                ;;
            -s|--skip-ssl)
                SKIP_SSL_CHECK=true
                shift
                ;;
            -o|--run-once)
                RUN_ONCE=true
                shift
                ;;
            -v|--verbose)
                VERBOSE_LOGGING=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Function to validate parameters
validate_params() {
    if [ -z "$MONITOR_ID" ]; then
        write_log "Monitor ID is required" "ERROR"
        show_usage
        exit 1
    fi
    
    if [ -z "$API_ENDPOINT" ]; then
        write_log "API endpoint is required" "ERROR"
        show_usage
        exit 1
    fi
    
    # Ensure API endpoint ends with /api
    if [[ ! "$API_ENDPOINT" =~ /api$ ]]; then
        API_ENDPOINT="${API_ENDPOINT%/}/api"
    fi
    
    # Validate monitor ID is numeric
    if ! [[ "$MONITOR_ID" =~ ^[0-9]+$ ]]; then
        write_log "Monitor ID must be a number" "ERROR"
        exit 1
    fi
    
    # Validate API endpoint format
    if ! [[ "$API_ENDPOINT" =~ ^https?:// ]]; then
        write_log "API endpoint must be a valid HTTP/HTTPS URL" "ERROR"
        exit 1
    fi
}

# Function to make HTTP requests
make_request() {
    local method="$1"
    local url="$2"
    local data="$3"
    local headers="$4"
    
    # Create temporary files for response and status code
    local temp_response=$(mktemp)
    local temp_headers=$(mktemp)
    
    local curl_opts="-s -w \"%{http_code}\" -o \"$temp_response\" -D \"$temp_headers\" -m 15"
    
    # Add SSL bypass if enabled
    if [ "$SKIP_SSL_CHECK" = true ]; then
        curl_opts="$curl_opts -k"
    fi
    
    # Add method
    if [ "$method" != "GET" ]; then
        curl_opts="$curl_opts -X $method"
    fi
    
    # Add headers
    if [ -n "$headers" ]; then
        while IFS= read -r header; do
            curl_opts="$curl_opts -H \"$header\""
        done <<< "$headers"
    fi
    
    # Add data for POST requests
    if [ -n "$data" ]; then
        curl_opts="$curl_opts -d '$data' -H 'Content-Type: application/json'"
    fi
    
    # Execute curl command and capture status code
    local status_code=$(eval curl $curl_opts "$url" 2>/dev/null)
    
    # Read response body from temp file
    local body=""
    if [ -f "$temp_response" ]; then
        body=$(cat "$temp_response")
    fi
    
    # Clean up temp files
    rm -f "$temp_response" "$temp_headers" 2>/dev/null
    
    # Validate status code is numeric
    if ! [[ "$status_code" =~ ^[0-9]{3}$ ]]; then
        # If status code is not valid, try to extract from headers or default to 0
        status_code="000"
    fi
    
    # Return status code and body
    echo "$status_code|$body"
}

# Function to get monitor configuration
get_monitor_config() {
    write_log "Fetching monitor configuration..."
    
    local headers="Authorization: Bearer $MONITOR_ID"
    local result=$(make_request "GET" "$API_ENDPOINT/monitors/$MONITOR_ID" "" "$headers")
    
    local status_code=$(echo "$result" | cut -d'|' -f1)
    local body=$(echo "$result" | cut -d'|' -f2-)
    
    if [ "$status_code" -eq 200 ]; then
        write_log "Monitor configuration retrieved successfully" "SUCCESS"
        echo "$body"
    else
        write_log "Failed to fetch monitor config: HTTP $status_code" "ERROR"
        return 1
    fi
}

# Function to get CPU usage
get_cpu_usage() {
    # Get CPU usage from /proc/stat
    local cpu_line=$(head -n1 /proc/stat)
    local cpu_times=($cpu_line)
    
    local idle=${cpu_times[4]}
    local total=0
    for time in "${cpu_times[@]:1}"; do
        total=$((total + time))
    done
    
    # Calculate CPU usage percentage
    local cpu_usage=$(awk "BEGIN {printf \"%.2f\", (($total - $idle) * 100) / $total}")
    echo "$cpu_usage"
}

# Function to get memory usage
get_memory_usage() {
    local mem_info=$(cat /proc/meminfo)
    local mem_total=$(echo "$mem_info" | grep MemTotal | awk '{print $2}')
    local mem_available=$(echo "$mem_info" | grep MemAvailable | awk '{print $2}')
    
    if [ -z "$mem_available" ]; then
        # Fallback for older systems
        local mem_free=$(echo "$mem_info" | grep MemFree | awk '{print $2}')
        local buffers=$(echo "$mem_info" | grep Buffers | awk '{print $2}')
        local cached=$(echo "$mem_info" | grep -w Cached | awk '{print $2}')
        mem_available=$((mem_free + buffers + cached))
    fi
    
    local mem_used=$((mem_total - mem_available))
    local mem_percent=$(awk "BEGIN {printf \"%.2f\", ($mem_used * 100) / $mem_total}")
    
    echo "$mem_percent"
}

# Function to get disk usage
get_disk_usage() {
    local disk_json="{"
    local first=true
    
    # Get disk usage for all mounted filesystems
    while IFS= read -r line; do
        local fields=($line)
        local filesystem="${fields[0]}"
        local total="${fields[1]}"
        local used="${fields[2]}"
        local available="${fields[3]}"
        local percent="${fields[4]%?}" # Remove % sign
        local mount="${fields[5]}"
        
        # Skip special filesystems
        if [[ "$filesystem" =~ ^(/dev/|tmpfs|udev) ]] && [[ "$mount" =~ ^(/|/home|/var|/tmp|/usr|/opt) ]]; then
            if [ "$first" = false ]; then
                disk_json="$disk_json,"
            fi
            first=false
            
            # Convert KB to bytes
            total_bytes=$((total * 1024))
            used_bytes=$((used * 1024))
            free_bytes=$((available * 1024))
            
            disk_json="$disk_json\"$mount\": {"
            disk_json="$disk_json\"total\": $total_bytes,"
            disk_json="$disk_json\"used\": $used_bytes,"
            disk_json="$disk_json\"free\": $free_bytes,"
            disk_json="$disk_json\"percent\": $percent,"
            disk_json="$disk_json\"mountpoint\": \"$mount\","
            disk_json="$disk_json\"fstype\": \"$(findmnt -n -o FSTYPE "$mount" 2>/dev/null || echo 'unknown')\""
            disk_json="$disk_json}"
        fi
    done <<< "$(df -k | tail -n +2)"
    
    disk_json="$disk_json}"
    echo "$disk_json"
}

# Function to get network statistics
get_network_stats() {
    local network_json="{"
    local first=true
    
    # Skip header line and loopback
    while IFS= read -r line; do
        if [[ "$line" =~ ^[[:space:]]*lo: ]]; then
            continue
        fi
        
        local interface=$(echo "$line" | cut -d: -f1 | tr -d ' ')
        local stats=($(echo "$line" | cut -d: -f2))
        
        if [ ${#stats[@]} -ge 16 ]; then
            local bytes_recv="${stats[0]}"
            local packets_recv="${stats[1]}"
            local bytes_sent="${stats[8]}"
            local packets_sent="${stats[9]}"
            
            if [ "$first" = false ]; then
                network_json="$network_json,"
            fi
            first=false
            
            network_json="$network_json\"$interface\": {"
            network_json="$network_json\"bytes_sent\": $bytes_sent,"
            network_json="$network_json\"bytes_recv\": $bytes_recv,"
            network_json="$network_json\"packets_sent\": $packets_sent,"
            network_json="$network_json\"packets_recv\": $packets_recv"
            network_json="$network_json}"
        fi
    done <<< "$(cat /proc/net/dev | tail -n +3)"
    
    network_json="$network_json}"
    echo "$network_json"
}

# Function to collect system metrics
get_system_metrics() {
    local cpu_percent=$(get_cpu_usage)
    local ram_percent=$(get_memory_usage)
    local disks=$(get_disk_usage)
    local network=$(get_network_stats)
    
    # Construct JSON more carefully to avoid formatting issues
    local metrics_json="{\"cpu_percent\": $cpu_percent, \"ram_percent\": $ram_percent, \"disks\": $disks, \"network\": $network}"
    
    echo "$metrics_json"
}

# Function to read log files
get_log_data() {
    local log_files="$1"
    local logs_json="{"
    local first=true
    
    if [ -z "$log_files" ]; then
        echo "{}"
        return
    fi
    
    # Split log files by comma
    IFS=',' read -ra log_array <<< "$log_files"
    
    for log_file in "${log_array[@]}"; do
        log_file=$(echo "$log_file" | xargs) # trim whitespace
        
        if [ -z "$log_file" ]; then
            continue
        fi
        
        write_log "Reading log file: $log_file"
        
        if [ "$first" = false ]; then
            logs_json="$logs_json,"
        fi
        first=false
        
        if [ -f "$log_file" ]; then
            local log_content=$(tail -n "$LOG_LINES" "$log_file" 2>/dev/null | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')
            logs_json="$logs_json\"$log_file\": \"$log_content\""
            write_log "Read log file $log_file successfully" "SUCCESS"
        else
            logs_json="$logs_json\"$log_file\": \"Log file not found: $log_file\""
            write_log "Log file not found: $log_file" "WARNING"
        fi
    done
    
    logs_json="$logs_json}"
    echo "$logs_json"
}

# Function to send data to server
send_data() {
    local payload="$1"
    write_log "Sending data to server..."
    
    # Debug: Always log payload preview when there's an error, or when verbose
    write_log "Payload preview: ${payload:0:200}..." "INFO"
    
    local headers="Authorization: Bearer $MONITOR_ID"
    local result=$(make_request "POST" "$API_ENDPOINT/agent/data" "$payload" "$headers")
    
    local status_code=$(echo "$result" | cut -d'|' -f1)
    local response_body=$(echo "$result" | cut -d'|' -f2-)
    
    # Validate status code is numeric before comparison
    if [[ "$status_code" =~ ^[0-9]{3}$ ]]; then
        if [ "$status_code" -eq 200 ] || [ "$status_code" -eq 201 ]; then
            write_log "Data sent successfully" "SUCCESS"
            return 0
        else
            write_log "Failed to send data: HTTP $status_code" "ERROR"
            if [ "$VERBOSE_LOGGING" = true ]; then
                write_log "Response body: $response_body" "ERROR"
                write_log "Full payload sent: $payload" "ERROR"
            fi
            return 1
        fi
    else
        write_log "Failed to send data: Invalid response - $status_code" "ERROR"
        if [ "$VERBOSE_LOGGING" = true ]; then
            write_log "Response body: $response_body" "ERROR"
            write_log "Full payload sent: $payload" "ERROR"
        fi
        return 1
    fi
}

# Function to fetch and execute commands
handle_commands() {
    write_log "Checking for pending commands..."
    
    local headers="Authorization: Bearer $MONITOR_ID"
    local result=$(make_request "GET" "$API_ENDPOINT/agent/commands" "" "$headers")
    
    local status_code=$(echo "$result" | cut -d'|' -f1)
    local body=$(echo "$result" | cut -d'|' -f2-)
    
    if [ "$status_code" -ne 200 ]; then
        write_log "Failed to fetch commands: HTTP $status_code" "ERROR"
        return
    fi
    
    # Simple JSON parsing for command array (basic implementation)
    local command_count=$(echo "$body" | grep -o '"id"' | wc -l)
    
    if [ "$command_count" -eq 0 ]; then
        return
    fi
    
    write_log "Found $command_count pending command(s)" "INFO"
    
    # Extract and execute each command (simplified JSON parsing)
    echo "$body" | grep -o '"id":[0-9]*' | while read -r id_line; do
        local cmd_id=$(echo "$id_line" | grep -o '[0-9]*')
        execute_command "$cmd_id" "$body"
    done
}

# Function to execute a command
execute_command() {
    local cmd_id="$1"
    local commands_json="$2"
    
    write_log "Executing command ID: $cmd_id"
    
    # Extract script from JSON (basic parsing)
    local script=$(echo "$commands_json" | grep -A 10 "\"id\":$cmd_id" | grep '"script"' | sed 's/.*"script":"\([^"]*\)".*/\1/' | sed 's/\\n/\n/g')
    
    if [ -z "$script" ]; then
        update_command_status "$cmd_id" "error" "Empty script."
        return
    fi
    
    write_log "Executing command: ${script:0:50}..."
    
    local output
    local status="completed"
    
    # Execute the command and capture output
    output=$(eval "$script" 2>&1)
    local exit_code=$?
    
    if [ $exit_code -ne 0 ]; then
        status="failed"
    fi
    
    write_log "Command executed with status: $status" "SUCCESS"
    
    update_command_status "$cmd_id" "$status" "$output"
}

# Function to update command status
update_command_status() {
    local cmd_id="$1"
    local status="$2"
    local output="$3"
    
    write_log "Updating status for command $cmd_id"
    
    # Escape output for JSON
    output=$(echo "$output" | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')
    
    local payload="{\"status\": \"$status\", \"output\": \"$output\"}"
    local headers="Authorization: Bearer $MONITOR_ID"
    
    local result=$(make_request "POST" "$API_ENDPOINT/agent/commands/$cmd_id/update" "$payload" "$headers")
    local update_status=$(echo "$result" | cut -d'|' -f1)
    
    if [ "$update_status" -eq 200 ]; then
        write_log "Command $cmd_id status updated successfully" "SUCCESS"
    else
        write_log "Failed to update command $cmd_id status: HTTP $update_status" "ERROR"
    fi
}

# Function to test connectivity
test_connectivity() {
    write_log "Testing connectivity to server..."
    
    local headers="Authorization: Bearer $MONITOR_ID"
    local result=$(make_request "GET" "$API_ENDPOINT/monitors/$MONITOR_ID" "" "$headers")
    
    local status_code=$(echo "$result" | cut -d'|' -f1)
    
    if [ "$status_code" -eq 200 ]; then
        write_log "Connectivity test successful" "SUCCESS"
        return 0
    else
        write_log "Connectivity test failed: HTTP $status_code" "ERROR"
        return 1
    fi
}

# Main monitoring loop
start_monitoring() {
    write_log "=== Uptime Agent Starting ===" "INFO"
    write_log "Monitor ID: $MONITOR_ID" "INFO"
    write_log "API Endpoint: $API_ENDPOINT" "INFO"
    write_log "Check Interval: $INTERVAL seconds" "INFO"
    write_log "Linux Distribution: $(lsb_release -d 2>/dev/null | cut -f2 || echo 'Unknown')" "INFO"
    write_log "Kernel Version: $(uname -r)" "INFO"
    
    # Test initial connectivity
    if ! test_connectivity; then
        write_log "Initial connectivity test failed. Continuing anyway..." "WARNING"
    fi
    
    # Get monitor configuration
    local config=$(get_monitor_config)
    local log_files=""
    
    if [ -n "$config" ]; then
        # Extract log files from config (basic JSON parsing)
        log_files=$(echo "$config" | grep -o '"log_files":[^,}]*' | sed 's/"log_files"://;s/^"//;s/"$//' | sed 's/null//')
        # Only process if log_files is not null or empty
        if [ -n "$log_files" ] && [ "$log_files" != "null" ]; then
            local log_count=$(echo "$log_files" | tr ',' '\n' | wc -l)
            write_log "Monitoring $log_count log file(s)" "INFO"
        else
            log_files=""
            write_log "No log files configured for monitoring" "INFO"
        fi
    fi
    
    write_log "Agent initialized. Starting monitoring loop..." "SUCCESS"
    
    while true; do
        # Collect system metrics
        local metrics=$(get_system_metrics)
        
        # Read log files
        local logs=$(get_log_data "$log_files")
        
        # Get current timestamp
        local timestamp=$(date +%s)
        
        # Prepare payload
        local payload="{\"timestamp\": $timestamp, \"metrics\": $metrics, \"logs\": $logs}"
        
        # Send data
        send_data "$payload"
        
        # Handle commands
        handle_commands
        
        # Check if running once
        if [ "$RUN_ONCE" = true ]; then
            write_log "Run-once mode, exiting..." "INFO"
            break
        fi
        
        # Wait for next interval
        write_log "Waiting $INTERVAL seconds until next check..."
        sleep "$INTERVAL"
    done
}

# Script entry point
main() {
    # Display banner
    cat << 'EOF'
===================================================
    Uptime Monitoring Agent - Linux Shell Edition
===================================================
EOF
    
    # Parse command line arguments
    parse_args "$@"
    
    # Validate parameters
    validate_params
    
    echo "Monitor ID: $MONITOR_ID"
    echo "Server: $API_ENDPOINT"
    echo "SSL Bypass: $SKIP_SSL_CHECK"
    echo "==================================================="
    
    # Check for required commands
    for cmd in curl df free; do
        if ! command -v "$cmd" &> /dev/null; then
            write_log "Required command '$cmd' not found" "ERROR"
            exit 1
        fi
    done
    
    # Start monitoring
    start_monitoring
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
