import psutil
import requests
import time
import json
import os
import subprocess
import glob
from datetime import datetime

# --- Configuration ---
# This will be replaced by a unique ID from the main application
API_KEY = '2' 
# The URL of the main monitoring application's API endpoint
API_ENDPOINT = os.environ.get('UPTIME_API_ENDPOINT', 'http://localhost:5000/api')
# Interval in seconds to send data
SEND_INTERVAL = 60 
# Number of lines to read from the end of each log file
LOG_LINES = int(os.environ.get('UPTIME_LOG_LINES', 100))

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
    """Executes a PowerShell script."""
    script = command.get('script')
    if not script:
        return {"status": "error", "output": "Empty script."}

    try:
        # Using powershell.exe for Windows
        result = subprocess.run(
            ["powershell.exe", "-Command", script],
            capture_output=True,
            text=True,
            timeout=300 # 5-minute timeout
        )
        
        output = result.stdout + result.stderr
        status = 'completed' if result.returncode == 0 else 'failed'
        
        return {"status": status, "output": output}

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
    print(f"Starting agent with API Key: ...{API_KEY[-4:]}")
    print(f"Sending data to: {API_ENDPOINT}")
    
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
