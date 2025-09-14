#!/usr/bin/env python3
"""
Standalone monitoring service script
This script runs the monitoring service independently
"""

import sys
import os

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.monitoring import run_monitoring_service

if __name__ == '__main__':
    print("Starting Python Monitor background service...")
    run_monitoring_service()