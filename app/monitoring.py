import requests
import time
import socket
import logging
from datetime import datetime, timedelta
from app import db, create_app
from app.models import Monitor, MonitorCheck, Incident, NotificationChannel
from app.notifications import notification_service
from sqlalchemy.orm import scoped_session, sessionmaker
from threading import Thread
import schedule
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/monitoring.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class MonitoringService:
    """Main monitoring service that checks all active monitors."""
    
    def __init__(self, app=None):
        self.app = app or create_app()
        self.session = None
        self.setup_database_session()
        
    def setup_database_session(self):
        """Setup database session for background thread."""
        with self.app.app_context():
            engine = db.get_engine()
            session_factory = sessionmaker(bind=engine)
            self.session = scoped_session(session_factory)
    
    def check_monitor(self, monitor):
        """Check a single monitor and return the result."""
        check_result = {
            'monitor_id': monitor.id,
            'is_up': False,
            'response_time': None,
            'status_code': None,
            'error_message': None,
            'response_text': None,
            'checked_at': datetime.utcnow()
        }
        
        try:
            if monitor.monitor_type in ['http', 'https']:
                return self.check_http_monitor(monitor, check_result)
            elif monitor.monitor_type == 'ping':
                return self.check_ping_monitor(monitor, check_result)
            elif monitor.monitor_type == 'port':
                return self.check_port_monitor(monitor, check_result)
            else:
                check_result['error_message'] = f'Unsupported monitor type: {monitor.monitor_type}'
                return check_result
                
        except Exception as e:
            logger.error(f'Error checking monitor {monitor.name}: {str(e)}')
            check_result['error_message'] = str(e)
            return check_result
    
    def check_http_monitor(self, monitor, check_result):
        """Check HTTP/HTTPS monitor."""
        start_time = time.time()
        
        try:
            # Prepare request parameters
            headers = monitor.get_parsed_headers()
            
            # Make the request with retry logic
            for attempt in range(monitor.retries):
                try:
                    response = requests.request(
                        method=monitor.method,
                        url=monitor.url,
                        headers=headers,
                        data=monitor.body,
                        timeout=monitor.timeout,
                        allow_redirects=True,
                        verify=True  # SSL verification
                    )
                    
                    # Calculate response time
                    response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                    check_result['response_time'] = round(response_time, 2)
                    check_result['status_code'] = response.status_code
                    
                    # Store first 1000 characters of response
                    try:
                        check_result['response_text'] = response.text[:1000]
                    except:
                        check_result['response_text'] = 'Unable to decode response text'
                    
                    # Check if status code matches expected
                    status_ok = response.status_code == monitor.expected_status
                    
                    # Check if expected text is present (if specified)
                    text_ok = True
                    if monitor.expected_text:
                        text_ok = monitor.expected_text in response.text
                        if not text_ok:
                            check_result['error_message'] = f'Expected text "{monitor.expected_text}" not found in response'
                    
                    # Check if status code indicates error
                    if not status_ok:
                        check_result['error_message'] = f'Expected status {monitor.expected_status}, got {response.status_code}'
                    
                    check_result['is_up'] = status_ok and text_ok
                    break
                    
                except requests.exceptions.RequestException as e:
                    if attempt == monitor.retries - 1:  # Last attempt
                        check_result['error_message'] = str(e)
                    else:
                        time.sleep(1)  # Wait 1 second before retry
                        continue
        
        except Exception as e:
            check_result['error_message'] = str(e)
        
        return check_result
    
    def check_ping_monitor(self, monitor, check_result):
        """Check ping monitor using socket connection."""
        import subprocess
        
        start_time = time.time()
        
        try:
            # Extract hostname from URL
            hostname = monitor.url.replace('http://', '').replace('https://', '').split('/')[0].split(':')[0]
            
            # Use system ping command
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(monitor.timeout * 1000), hostname],
                capture_output=True,
                text=True,
                timeout=monitor.timeout
            )
            
            response_time = (time.time() - start_time) * 1000
            check_result['response_time'] = round(response_time, 2)
            
            if result.returncode == 0:
                check_result['is_up'] = True
            else:
                check_result['error_message'] = result.stderr or 'Ping failed'
        
        except subprocess.TimeoutExpired:
            check_result['error_message'] = 'Ping timeout'
        except Exception as e:
            check_result['error_message'] = str(e)
        
        return check_result
    
    def check_port_monitor(self, monitor, check_result):
        """Check port connectivity."""
        start_time = time.time()
        
        try:
            # Parse hostname and port from URL
            url_parts = monitor.url.replace('http://', '').replace('https://', '').split(':')
            hostname = url_parts[0]
            port = int(url_parts[1]) if len(url_parts) > 1 else (443 if monitor.url.startswith('https') else 80)
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(monitor.timeout)
            
            result = sock.connect_ex((hostname, port))
            response_time = (time.time() - start_time) * 1000
            check_result['response_time'] = round(response_time, 2)
            
            if result == 0:
                check_result['is_up'] = True
            else:
                check_result['error_message'] = f'Connection failed to {hostname}:{port}'
            
            sock.close()
        
        except Exception as e:
            check_result['error_message'] = str(e)
        
        return check_result
    
    def save_check_result(self, check_result):
        """Save check result to database and handle incidents."""
        try:
            # Create new check record
            check = MonitorCheck(**check_result)
            self.session.add(check)
            
            # Handle incident tracking
            monitor = self.session.query(Monitor).get(check_result['monitor_id'])
            if monitor:
                self.handle_incident_tracking(monitor, check_result['is_up'], check_result.get('error_message'))
            
            self.session.commit()
            
        except Exception as e:
            logger.error(f'Error saving check result: {str(e)}')
            self.session.rollback()
    
    def handle_incident_tracking(self, monitor, is_up, error_message):
        """Handle incident creation and resolution."""
        # Get the latest incident for this monitor
        latest_incident = self.session.query(Incident).filter_by(
            monitor_id=monitor.id,
            is_resolved=False
        ).order_by(Incident.started_at.desc()).first()
        
        if not is_up:  # Monitor is down
            if not latest_incident:
                # Create new incident
                incident = Incident(
                    monitor_id=monitor.id,
                    started_at=datetime.utcnow(),
                    error_message=error_message,
                    is_resolved=False
                )
                self.session.add(incident)
                logger.warning(f'New incident created for monitor: {monitor.name}')
                
                # Send notifications for new incident
                self.send_notifications('incident_started', monitor, incident)
                
        else:  # Monitor is up
            if latest_incident:
                # Resolve existing incident
                latest_incident.ended_at = datetime.utcnow()
                latest_incident.duration = int((latest_incident.ended_at - latest_incident.started_at).total_seconds())
                latest_incident.is_resolved = True
                logger.info(f'Incident resolved for monitor: {monitor.name} (Duration: {latest_incident.duration_formatted})')
                
                # Send notifications for incident resolution
                self.send_notifications('incident_resolved', monitor, latest_incident)
    
    def run_checks(self):
        """Run checks for all active monitors that are due for checking."""
        try:
            with self.app.app_context():
                # Get monitors that need checking
                now = datetime.utcnow()
                monitors = self.session.query(Monitor).filter_by(is_active=True).all()
                
                for monitor in monitors:
                    # Check if monitor is due for checking
                    last_check = self.session.query(MonitorCheck).filter_by(
                        monitor_id=monitor.id
                    ).order_by(MonitorCheck.checked_at.desc()).first()
                    
                    if not last_check or (now - last_check.checked_at).total_seconds() >= monitor.interval:
                        logger.info(f'Checking monitor: {monitor.name}')
                        
                        # Run the check
                        result = self.check_monitor(monitor)
                        
                        # Save the result
                        self.save_check_result(result)
                        
                        status = "UP" if result['is_up'] else "DOWN"
                        response_time = f" ({result['response_time']}ms)" if result['response_time'] else ""
                        logger.info(f'Monitor {monitor.name}: {status}{response_time}')
        
        except Exception as e:
            logger.error(f'Error in run_checks: {str(e)}')
    
    def send_notifications(self, incident_type: str, monitor: Monitor, incident: Incident = None):
        """Send notifications through all active channels."""
        try:
            # Get active notification channels
            channels = self.session.query(NotificationChannel).filter_by(is_active=True).all()
            
            if not channels:
                logger.debug('No active notification channels configured')
                return
            
            for channel in channels:
                try:
                    # Parse channel configuration
                    config = json.loads(channel.config) if channel.config else {}
                    
                    # Prepare channel data for notification service
                    channel_data = {
                        'id': channel.id,
                        'name': channel.name,
                        'type': channel.type,
                        'config': channel.config
                    }
                    
                    # Send notification
                    success = notification_service.send_notification(
                        channel_data, incident_type, monitor, incident
                    )
                    
                    if success:
                        logger.info(f'Notification sent successfully via {channel.type} channel: {channel.name}')
                    else:
                        logger.error(f'Failed to send notification via {channel.type} channel: {channel.name}')
                        
                except Exception as e:
                    logger.error(f'Error sending notification via channel {channel.name}: {str(e)}')
        
        except Exception as e:
            logger.error(f'Error in send_notifications: {str(e)}')
    
    def cleanup_old_data(self):
        """Clean up old check data and resolved incidents."""
        try:
            with self.app.app_context():
                # Remove check data older than configured days
                cutoff_date = datetime.utcnow() - timedelta(days=self.app.config['KEEP_HISTORY_DAYS'])
                
                old_checks = self.session.query(MonitorCheck).filter(
                    MonitorCheck.checked_at < cutoff_date
                ).delete()
                
                # Remove resolved incidents older than 90 days
                old_incidents = self.session.query(Incident).filter(
                    Incident.is_resolved == True,
                    Incident.ended_at < datetime.utcnow() - timedelta(days=90)
                ).delete()
                
                self.session.commit()
                
                if old_checks > 0 or old_incidents > 0:
                    logger.info(f'Cleaned up {old_checks} old checks and {old_incidents} old incidents')
        
        except Exception as e:
            logger.error(f'Error in cleanup_old_data: {str(e)}')
            self.session.rollback()

def run_monitoring_service():
    """Main function to run the monitoring service."""
    app = create_app()
    service = MonitoringService(app)
    
    # Schedule checks every 30 seconds
    schedule.every(30).seconds.do(service.run_checks)
    
    # Schedule cleanup daily at 02:00
    schedule.every().day.at("02:00").do(service.cleanup_old_data)
    
    logger.info('Monitoring service started')
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    run_monitoring_service()