#!/usr/bin/env python3
"""
Python Monitor - Uptime monitoring application
Main application entry point
"""

import os
import logging
from flask import Flask
from app import create_app, db
from app.models import Monitor, MonitorCheck, Incident, NotificationChannel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

def create_application():
    """Create and configure the Flask application."""
    # Create the Flask app
    app = create_app()
    
    # Create database tables
    with app.app_context():
        db.create_all()
        
        # Create a sample monitor if none exist
        if Monitor.query.count() == 0:
            sample_monitor = Monitor(
                name='Google',
                url='https://www.google.com',
                monitor_type='https',
                method='GET',
                expected_status=200,
                timeout=30,
                interval=60,
                retries=3
            )
            db.session.add(sample_monitor)
            
            sample_monitor2 = Monitor(
                name='Local Host',
                url='http://localhost:3000',
                monitor_type='http',
                method='GET',
                expected_status=200,
                timeout=10,
                interval=30,
                retries=2
            )
            db.session.add(sample_monitor2)
            
            try:
                db.session.commit()
                print("Sample monitors created")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating sample monitors: {e}")
    
    return app

def init_database(app):
    """Initialize database with sample data."""
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Add sample notification channels if none exist
        if NotificationChannel.query.count() == 0:
            email_channel = NotificationChannel(
                name='Admin Email',
                type='email',
                config='{"email": "admin@example.com", "smtp_server": "localhost"}',
                is_active=False  # Disabled by default
            )
            db.session.add(email_channel)
            
            webhook_channel = NotificationChannel(
                name='Webhook Alert',
                type='webhook',
                config='{"url": "https://hooks.example.com/webhook", "method": "POST"}',
                is_active=False  # Disabled by default
            )
            db.session.add(webhook_channel)
            
            try:
                db.session.commit()
                print("Sample notification channels created")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating sample channels: {e}")

# Create the application
app = create_application()

# Initialize database
init_database(app)

# CLI commands
@app.cli.command()
def init_db():
    """Initialize the database."""
    db.create_all()
    print("Database initialized!")

@app.cli.command()
def create_sample_data():
    """Create sample monitors and data."""
    # Create sample monitors
    if Monitor.query.count() == 0:
        monitors = [
            {
                'name': 'Google',
                'url': 'https://www.google.com',
                'monitor_type': 'https',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 30,
                'interval': 60
            },
            {
                'name': 'GitHub',
                'url': 'https://github.com',
                'monitor_type': 'https',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 30,
                'interval': 120
            },
            {
                'name': 'Local API',
                'url': 'http://localhost:3000/api/status',
                'monitor_type': 'http',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 10,
                'interval': 30
            }
        ]
        
        for monitor_data in monitors:
            monitor = Monitor(**monitor_data)
            db.session.add(monitor)
        
        try:
            db.session.commit()
            print(f"Created {len(monitors)} sample monitors")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating sample monitors: {e}")
    else:
        print("Monitors already exist, skipping sample data creation")

@app.cli.command()
def cleanup_old_data():
    """Clean up old monitoring data."""
    from datetime import datetime, timedelta
    
    # Remove check data older than 30 days
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    
    old_checks = MonitorCheck.query.filter(
        MonitorCheck.checked_at < cutoff_date
    ).delete()
    
    # Remove resolved incidents older than 90 days
    old_incidents = Incident.query.filter(
        Incident.is_resolved == True,
        Incident.ended_at < datetime.utcnow() - timedelta(days=90)
    ).delete()
    
    db.session.commit()
    
    print(f"Cleaned up {old_checks} old checks and {old_incidents} old incidents")

@app.cli.command()
def export_data():
    """Export all monitoring data to JSON."""
    import json
    from datetime import datetime
    
    # Get all data
    monitors = Monitor.query.all()
    checks = MonitorCheck.query.order_by(MonitorCheck.checked_at.desc()).limit(10000).all()
    incidents = Incident.query.order_by(Incident.started_at.desc()).all()
    
    # Prepare export data
    export_data = {
        'export_date': datetime.utcnow().isoformat(),
        'monitors': [],
        'checks': [],
        'incidents': []
    }
    
    # Export monitors
    for monitor in monitors:
        export_data['monitors'].append({
            'id': monitor.id,
            'name': monitor.name,
            'url': monitor.url,
            'monitor_type': monitor.monitor_type,
            'method': monitor.method,
            'expected_status': monitor.expected_status,
            'expected_text': monitor.expected_text,
            'timeout': monitor.timeout,
            'interval': monitor.interval,
            'retries': monitor.retries,
            'headers': monitor.headers,
            'body': monitor.body,
            'is_active': monitor.is_active,
            'created_at': monitor.created_at.isoformat(),
            'updated_at': monitor.updated_at.isoformat()
        })
    
    # Export checks
    for check in checks:
        export_data['checks'].append({
            'id': check.id,
            'monitor_id': check.monitor_id,
            'is_up': check.is_up,
            'response_time': check.response_time,
            'status_code': check.status_code,
            'error_message': check.error_message,
            'checked_at': check.checked_at.isoformat()
        })
    
    # Export incidents
    for incident in incidents:
        export_data['incidents'].append({
            'id': incident.id,
            'monitor_id': incident.monitor_id,
            'started_at': incident.started_at.isoformat(),
            'ended_at': incident.ended_at.isoformat() if incident.ended_at else None,
            'duration': incident.duration,
            'error_message': incident.error_message,
            'is_resolved': incident.is_resolved
        })
    
    # Save to file
    filename = f"monitor_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"Data exported to {filename}")
    print(f"Exported {len(monitors)} monitors, {len(checks)} checks, {len(incidents)} incidents")

if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Run the development server
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 3000)),
        debug=os.environ.get('FLASK_ENV') == 'development'
    )