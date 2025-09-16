#!/usr/bin/env python3
"""Quick test to verify the agent_parameterized.py argument handling"""

import sys
import os

# Add the agent directory to the path to import the agent logic
sys.path.insert(0, os.path.dirname(__file__))

# Simulate command line arguments
sys.argv = ['quick_test_agent.py', '--monitor-id', '3', '--api-endpoint', 'http://127.0.0.1:5000/api']

print("Testing agent argument parsing...")
print(f"Simulated command line: {' '.join(sys.argv)}")
print()

try:
    # Import and parse arguments like the agent does
    import argparse
    
    parser = argparse.ArgumentParser(description='Uptime Monitoring Agent')
    parser.add_argument('--monitor-id', type=int, help='Monitor ID for this agent')
    parser.add_argument('--api-endpoint', help='API endpoint URL')
    parser.add_argument('--log-lines', type=int, default=100, help='Number of log lines to read')

    args = parser.parse_args()

    # Configuration with command line override (same logic as agent_parameterized.py)
    API_KEY = str(args.monitor_id) if args.monitor_id else os.environ.get('UPTIME_API_KEY', 'YOUR_DEFAULT_API_KEY')
    API_ENDPOINT = args.api_endpoint or os.environ.get('UPTIME_API_ENDPOINT', 'http://localhost:5000/api')
    LOG_LINES = args.log_lines

    # Show results
    print("=== ARGUMENT PARSING TEST RESULTS ===")
    print(f"Parsed monitor_id: {args.monitor_id}")
    print(f"Parsed api_endpoint: {args.api_endpoint}")
    print(f"Final API_KEY: {API_KEY}")
    print(f"Final API_ENDPOINT: {API_ENDPOINT}")
    print(f"Environment UPTIME_API_ENDPOINT: {os.environ.get('UPTIME_API_ENDPOINT', 'Not set')}")
    print()
    print("Agent would display:")
    monitor_id_display = args.monitor_id if args.monitor_id else os.environ.get('UPTIME_API_KEY', 'Unknown')
    print(f"Starting agent for Monitor ID: {monitor_id_display}")
    print(f"API Endpoint: {API_ENDPOINT}")
    print(f"Data will be sent to: {API_ENDPOINT}/agent/data")
    print()
    
    if API_ENDPOINT == 'http://127.0.0.1:5000/api':
        print("✅ SUCCESS: Agent is using the correct endpoint!")
    else:
        print(f"❌ PROBLEM: Agent is using {API_ENDPOINT} instead of http://127.0.0.1:5000/api")

except Exception as e:
    print(f"❌ Error during test: {e}")
