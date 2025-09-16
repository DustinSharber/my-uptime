import psutil
import requests
import time
import json
import os
import subprocess
import glob
import argparse
import sys
from datetime import datetime

# --- Configuration ---
# Parse command line arguments
parser = argparse.ArgumentParser(description='Uptime Monitoring Agent')
parser.add_argument('--monitor-id', type=int, help='Monitor ID for this agent')
parser.add_argument('--api-endpoint', help='API endpoint URL')
parser.add_argument('--log-lines', type=int, default=100, help='Number of log lines to read')

args = parser.parse_args()

# Configuration with command line override
API_KEY = str(args.monitor_id) if args.monitor_id else os.environ.get('UPTIME_API_KEY', 'YOUR_DEFAULT_API_KEY')
API_ENDPOINT = args.api_endpoint or os.environ.get('UPTIME_API_ENDPOINT', 'http://localhost:5000/api')
LOG_LINES = args.log_lines

# Validate required parameters
if not args.monitor_id and not os.environ.get('UPTIME_API_KEY'):
    print("Error: Monitor ID is required. Use --monitor-id parameter or set UPTIME_API_KEY environment variable.")
    print("Example: ./uptime_agent --monitor-id 3")
    sys.exit(1)

# Show the actual monitor ID in logs, not the API key
monitor_id_display = args.monitor_id if args.monitor_id else os.environ.get('UPTIME_API_KEY', 'Unknown')
print(f"Starting agent for Monitor ID: {monitor_id_display}")
print(f"API Endpoint: {API_ENDPOINT}")
print(f"Data will be sent to: {API_ENDPOINT}/agent/data")

# Interval in seconds to send data
SEND_INTERVAL = 60

def get_monitor_config():
    """Fetches the monitor's configuration from the main application."""
    headers = {
        'Authorization': f'Bearer {API_KEY}'
    }
    try:
        # Construct the URL to fetch monitor details
        monitor_url = f"{API_ENDPOINT}/monitors/{API_KEY}"
        response = requests.get(monitor_url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching monitor config: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to the API to get config: {e}")
        return None

def get_log_data(log_files_str):
    """Reads the last N lines of configured log files."""
    logs = {}
    if not log_files_str:
        return logs
        
    log_files = log_files_str.split(',')
    for log_file in log_files:
        if not log_file:
            continue
        try:
            with open(log_file.strip(), 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                logs[log_file] = lines[-LOG_LINES:]
        except Exception as e:
            print(f"Could not read log file {log_file}: {e}")
            logs[log_file] = [f"Error reading log: {e}"]
    return logs

def get_system_metrics():
    """Gathers system metrics like CPU, RAM, disk and network usage."""
    metrics = {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'ram_percent': psutil.virtual_memory().percent,
        'disks': {},
        'network': {}
    }

    # Get disk usage for all drives
    for partition in psutil.disk_partitions(all=True):
        try:
            disk = psutil.disk_usage(partition.mountpoint)
            metrics['disks'][partition.device] = {
                'total': disk.total,
                'used': disk.used,
                'free': disk.free,
                'percent': disk.percent,
                'mountpoint': partition.mountpoint
            }
        except Exception as e:
            print(f"Could not get disk usage for {partition.device}: {e}")
            continue

    # Get network stats for each interface
    try:
        net_io = psutil.net_io_counters(pernic=True)
        for interface, io in net_io.items():
            metrics['network'][interface] = {
                'bytes_sent': io.bytes_sent,
                'bytes_recv': io.bytes_recv,
                'packets_sent': io.packets_sent,
                'packets_recv': io.packets_recv,
                'errin': io.errin,
                'errout': io.errout,
                'dropin': io.dropin,
                'dropout': io.dropout
            }
    except Exception as e:
        print(f"Could not get network stats: {e}")
        metrics['network'] = {}

    return metrics

def send_data(data):
    """Sends the collected data to the main application's API."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }
    try:
        response = requests.post(f"{API_ENDPOINT}/agent/data", data=json.dumps(data), headers=headers, timeout=15)
        if response.status_code == 200:
            print(f"Successfully sent data")
        else:
            print(f"Error sending data: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to the API endpoint: {e}")

def fetch_commands():
    """Fetches pending commands from the server."""
    headers = {'Authorization': f'Bearer {API_KEY}'}
    try:
        response = requests.get(f"{API_ENDPOINT}/agent/commands", headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching commands: {e}")
        return []

def execute_command(command):
    """Executes a script using the specified shell."""
    script = command.get('script')
    shell_type = command.get('shell_type', 'powershell') # Default to powershell for backward compatibility

    if not script:
        return {"status": "error", "output": "Empty script."}

    try:
        if shell_type == 'bash':
            # For Linux/macOS
            executable = "bash"
            args = ["-c", script]
        else:
            # For Windows PowerShell
            executable = "powershell.exe"
            args = ["-Command", script]

        result = subprocess.run(
            [executable] + args,
            capture_output=True,
            text=True,
            timeout=300, # 5-minute timeout
            shell=False # It's safer to not use shell=True
        )
        
        output = result.stdout + result.stderr
        status = 'completed' if result.returncode == 0 else 'failed'
        
        return {"status": status, "output": output}

    except FileNotFoundError:
        return {"status": "failed", "output": f"The executable '{executable}' was not found. Ensure it is in the system's PATH."}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "output": "Command timed out after 5 minutes."}
    except Exception as e:
        return {"status": "failed", "output": str(e)}

def update_command_status(command_id, result):
    """Updates the server with the command execution result."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }
    payload = {
        'status': result['status'],
        'output': result['output']
    }
    try:
        url = f"{API_ENDPOINT}/agent/commands/{command_id}/update"
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"Successfully updated status for command {command_id}.")
    except requests.exceptions.RequestException as e:
        print(f"Error updating command status for {command_id}: {e}")

def handle_commands():
    """Fetch, execute, and update commands."""
    print("Checking for commands...")
    commands = fetch_commands()
    for command in commands:
        print(f"Executing command ID: {command['id']}")
        result = execute_command(command)
        update_command_status(command['id'], result)

def main():
    """Main loop to collect and send metrics."""
    print(f"Agent initialized. Starting monitoring loop...")
    print(f"Check interval: {SEND_INTERVAL} seconds")
    
    while True:
        try:
            # Fetch monitor config to get the list of log files
            config = get_monitor_config()
            log_files_to_monitor = []
            if config and config.get('log_files'):
                log_files_to_monitor = config.get('log_files')

            metrics = get_system_metrics()
            logs = get_log_data(log_files_to_monitor)
            
            # Combine all data into a single payload
            payload = {
                'timestamp': time.time(),
                'metrics': metrics,
                'logs': logs
            }
            
            send_data(payload)
            
            # Handle commands
            handle_commands()

            # Wait for the next interval
            time.sleep(SEND_INTERVAL)
            
        except KeyboardInterrupt:
            print("Agent stopped by user.")
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            # Wait a bit before retrying to avoid spamming errors
            time.sleep(30)

if __name__ == "__main__":
    main()
