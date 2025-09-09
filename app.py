#!/usr/bin/env python3
"""
Python Monitor - Uptime monitoring application
Main application entry point
"""

import os
import logging
from app import create_app
from app.models import Monitor, MonitorCheck, Incident, NotificationChannel
from app.database import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

# Create the application
app = create_app(os.getenv('FLASK_ENV') or 'default')

# CLI commands
@app.cli.command()
def create_sample_data():
    """Create sample monitors and data."""
    if not db.get_all('monitor'):
        monitors = [
            {
                'name': 'Google',
                'url': 'https://www.google.com',
                'monitor_type': 'https',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 30,
                'interval': 60,
                'retries': 3,
                'is_active': True
            },
            {
                'name': 'GitHub',
                'url': 'https://github.com',
                'monitor_type': 'https',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 30,
                'interval': 120,
                'retries': 3,
                'is_active': True
            },
            {
                'name': 'Local API',
                'url': 'http://localhost:5001/api/status',
                'monitor_type': 'http',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 10,
                'interval': 30,
                'retries': 3,
                'is_active': True
            }
        ]
        
        for monitor_data in monitors:
            db.add('monitor', monitor_data)
        
        print(f"Created {len(monitors)} sample monitors")
    else:
        print("Monitors already exist, skipping sample data creation")

from app.monitoring import run_monitoring_service
from threading import Thread

if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Start the monitoring service in a background thread
    monitoring_thread = Thread(target=run_monitoring_service)
    monitoring_thread.daemon = True
    monitoring_thread.start()
    
    # Run the development server
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5001)),
        debug=os.environ.get('FLASK_ENV') == 'development',
        threaded=True
    )
