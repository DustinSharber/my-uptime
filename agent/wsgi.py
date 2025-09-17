#!/usr/bin/env python3
"""
WSGI entry point for production deployment with gunicorn
"""

import os
import sys
import logging
from threading import Thread
from app import create_app

# Ensure required directories exist first
for directory in ['logs', 'data', 'instance']:
    os.makedirs(directory, exist_ok=True)

# Configure logging for production with fallback to console only
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/app.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
except Exception as e:
    # Fallback to console logging only if file logging fails
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print(f"Warning: Could not set up file logging: {e}")

logger = logging.getLogger(__name__)

def start_background_services():
    """Start the monitoring service and scheduler"""
    try:
        logger.info("Starting background services...")
        
        from app.scheduler import init_scheduler
        
        # Initialize scheduler first
        scheduler = init_scheduler()
        logger.info("Scheduler initialized successfully")
        
        # Start monitoring service in background thread
        from app.monitoring import run_monitoring_service
        monitoring_thread = Thread(target=run_monitoring_service)
        monitoring_thread.daemon = True
        monitoring_thread.start()
        
        logger.info("Background services started successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to start background services: {e}")
        logger.exception("Full traceback:")
        return False

# Create the application
try:
    app = create_app(os.getenv('FLASK_ENV') or 'production')
    logger.info("Flask app created successfully")
except Exception as e:
    logger.error(f"Failed to create Flask app: {e}")
    logger.exception("Full traceback:")
    sys.exit(1)

# Start background services when the module is imported
try:
    with app.app_context():
        success = start_background_services()
        if not success:
            logger.warning("Background services failed to start, but continuing with web app only")
except Exception as e:
    logger.error(f"Failed to start background services with app context: {e}")
    logger.exception("Full traceback:")
    # Don't exit here, allow the web app to still run

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
