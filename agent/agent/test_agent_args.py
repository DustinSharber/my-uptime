#!/usr/bin/env python3
import argparse
import os
import sys

# Parse command line arguments
parser = argparse.ArgumentParser(description='Uptime Monitoring Agent - Test Args')
parser.add_argument('--monitor-id', type=int, help='Monitor ID for this agent')
parser.add_argument('--api-endpoint', help='API endpoint URL')
parser.add_argument('--log-lines', type=int, default=100, help='Number of log lines to read')

args = parser.parse_args()

# Configuration with command line override
API_KEY = str(args.monitor_id) if args.monitor_id else os.environ.get('UPTIME_API_KEY', 'YOUR_DEFAULT_API_KEY')
API_ENDPOINT = args.api_endpoint or os.environ.get('UPTIME_API_ENDPOINT', 'http://localhost:5000/api')
LOG_LINES = args.log_lines

print("=== AGENT PARAMETER TEST ===")
print(f"Command line args: {sys.argv}")
print(f"Parsed monitor_id: {args.monitor_id}")
print(f"Parsed api_endpoint: {args.api_endpoint}")
print(f"Final API_KEY: {API_KEY}")
print(f"Final API_ENDPOINT: {API_ENDPOINT}")
print(f"Environment UPTIME_API_ENDPOINT: {os.environ.get('UPTIME_API_ENDPOINT', 'Not set')}")

# Show exactly what would be sent to
print(f"Would send data to: {API_ENDPOINT}/agent/data")
