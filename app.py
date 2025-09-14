#!/usr/bin/env python3
"""
Python Monitor - Uptime monitoring application
Main application entry point
"""

import os
import logging
from app import create_app, bcrypt
from app.models import User
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


from app.monitoring import run_monitoring_service
from app.scheduler import init_scheduler
from threading import Thread

if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Initialize and start the scheduler
    scheduler = init_scheduler()
    
    # Start the monitoring service in a background thread
    monitoring_thread = Thread(target=run_monitoring_service)
    monitoring_thread.daemon = True
    monitoring_thread.start()
    
    # Run the development server
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development',
        threaded=True
    )
