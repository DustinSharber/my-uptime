#!/usr/bin/env python3
"""
WSGI entry point for production deployment with gunicorn
"""

import os
import logging
from threading import Thread
from app import create_app
from app.database import db

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Create the application
app = create_app(os.getenv('FLASK_ENV') or 'production')

def start_background_services():
    """Start the monitoring service and scheduler"""
    try:
        from app.monitoring import run_monitoring_service
        from app.scheduler import init_scheduler
        
        # Initialize scheduler
        scheduler = init_scheduler()
        
        # Start monitoring service in background thread
        monitoring_thread = Thread(target=run_monitoring_service)
        monitoring_thread.daemon = True
        monitoring_thread.start()
        
        logging.info("Background services started successfully")
    except Exception as e:
        logging.error(f"Failed to start background services: {e}")

# Start background services when the module is imported
with app.app_context():
    start_background_services()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
