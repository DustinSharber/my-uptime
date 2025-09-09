import psutil
import requests
import time
import json
import os

# --- Configuration ---
# This will be replaced by a unique ID from the main application
API_KEY = '2' 
# The URL of the main monitoring application's API endpoint
API_ENDPOINT = os.environ.get('UPTIME_API_ENDPOINT', 'http://localhost:5001/api/agent/data')
# Interval in seconds to send data
SEND_INTERVAL = 60 

def get_system_metrics():
    """Gathers system metrics like CPU and RAM usage."""
    return {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'ram_percent': psutil.virtual_memory().percent,
    }

def send_data(data):
    """Sends the collected data to the main application's API."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}'
    }
    try:
        response = requests.post(API_ENDPOINT, data=json.dumps(data), headers=headers, timeout=15)
        if response.status_code == 200:
            print(f"Successfully sent data: {data}")
        else:
            print(f"Error sending data: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to connect to the API endpoint: {e}")

def main():
    """Main loop to collect and send metrics."""
    print(f"Starting agent with API Key: ...{API_KEY[-4:]}")
    print(f"Sending data to: {API_ENDPOINT}")
    
    while True:
        try:
            metrics = get_system_metrics()
            
            # Add a timestamp
            metrics['timestamp'] = time.time()
            
            send_data(metrics)
            
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
