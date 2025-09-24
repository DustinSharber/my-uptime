import requests
import time
import os
import subprocess
import socket
import ssl
import logging
from datetime import datetime, timedelta
import pytz
from app import create_app
from app.database import db
from app.models import Monitor, MonitorCheck, Incident, NotificationChannel, Maintenance
from app.notifications import notification_service
from app.utils import parse_timestamp
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
    
    def check_monitor(self, monitor):
        """Check a single monitor and return the result."""
        check_result = {
            'monitor_id': monitor.id,
            'is_up': False,
            'response_time': None,
            'status_code': None,
            'error_message': None,
            'response_text': None,
            'checked_at': datetime.now(pytz.utc).isoformat(),
            'cert_expires_in_days': None
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
            if not headers:
                headers = {}
            
            # Set default browser-like headers if not provided, to avoid being blocked
            if 'User-Agent' not in headers:
                headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            if 'Accept' not in headers:
                headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'
            if 'Accept-Language' not in headers:
                headers['Accept-Language'] = 'en-US,en;q=0.9'
            if 'Accept-Encoding' not in headers:
                headers['Accept-Encoding'] = 'gzip, deflate, br'
            if 'Connection' not in headers:
                headers['Connection'] = 'keep-alive'

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
                        verify=monitor.verify_ssl
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

        # Certificate Expiry Check
        if monitor.check_cert_expiry and monitor.url.startswith('https://'):
            try:
                hostname = monitor.url.split('/')[2]
                context = ssl.create_default_context()
                with socket.create_connection((hostname, 443), timeout=monitor.timeout) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert = ssock.getpeercert()
                        expiry_date_str = cert['notAfter']
                        # Example format: 'Sep  9 12:00:00 2025 GMT'
                        expiry_date = datetime.strptime(expiry_date_str, '%b %d %H:%M:%S %Y %Z')
                        
                        # Make expiry_date timezone-aware to compare with utcnow()
                        # We assume GMT/UTC from the cert string
                        expiry_date = expiry_date.replace(tzinfo=pytz.utc)
                        
                        now_utc = datetime.now(pytz.utc)
                        days_remaining = (expiry_date - now_utc).days
                        
                        check_result['cert_expires_in_days'] = days_remaining
                        
                        # If cert expires in less than 30 days, consider it a warning/down
                        if days_remaining < 0:
                            check_result['is_up'] = False
                            check_result['error_message'] = f"Certificate for {hostname} has expired."
                        elif days_remaining < 30:
                            # This is a soft-down, might need a special status later
                            if check_result['is_up']: # Don't overwrite a real error
                                check_result['error_message'] = f"Certificate for {hostname} expires in {days_remaining} days."

            except Exception as cert_e:
                logger.error(f"Could not check SSL cert for {hostname}: {cert_e}")
                if check_result['is_up']: # Don't overwrite a real error
                    check_result['error_message'] = f"Failed to check SSL certificate: {cert_e}"
        
        return check_result
    
    def check_ping_monitor(self, monitor, check_result):
        """Check ping monitor using multiple methods for Docker compatibility."""
        start_time = time.time()
        
        try:
            # Extract hostname from URL
            hostname = monitor.url.replace('http://', '').replace('https://', '').split('/')[0].split(':')[0]
            
            # Method 1: Try TCP connect to port 80/443 as ping alternative
            ping_success = self._tcp_ping(hostname, monitor.timeout)
            
            if not ping_success:
                # Method 2: Try system ping command (may fail in Docker)
                ping_success = self._system_ping(hostname, monitor.timeout)
            
            response_time = (time.time() - start_time) * 1000
            check_result['response_time'] = round(response_time, 2)
            check_result['is_up'] = ping_success
            
            if not ping_success and not check_result.get('error_message'):
                check_result['error_message'] = f'Unable to reach {hostname} via TCP or ICMP ping'
        
        except Exception as e:
            check_result['error_message'] = str(e)
            logger.error(f'Error in ping monitor for {hostname}: {str(e)}')
        
        return check_result
    
    def _tcp_ping(self, hostname, timeout):
        """TCP-based ping using common ports (Docker-friendly)."""
        common_ports = [80, 443, 22, 21, 25, 53, 3389]
        
        try:
            # First try to resolve the hostname
            try:
                socket.gethostbyname(hostname)
                logger.debug(f'DNS resolution successful for {hostname}')
            except socket.gaierror as e:
                logger.warning(f'DNS resolution failed for {hostname}: {e}')
                return False
            
            # Try to connect to common ports
            for port in common_ports:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(min(timeout / len(common_ports), 2))  # Distribute timeout across ports
                    result = sock.connect_ex((hostname, port))
                    sock.close()
                    
                    if result == 0:
                        logger.debug(f'TCP ping successful to {hostname}:{port}')
                        return True
                    
                except Exception as e:
                    logger.debug(f'TCP ping failed to {hostname}:{port} - {e}')
                    continue
            
            logger.debug(f'TCP ping failed to all common ports for {hostname}')
            return False
            
        except Exception as e:
            logger.error(f'Error in TCP ping to {hostname}: {e}')
            return False
    
    def _system_ping(self, hostname, timeout):
        """Traditional ICMP ping using system command."""
        try:
            # Use system ping command
            if os.name == 'nt':  # Windows
                command = ['ping', '-n', '1', '-w', str(int(timeout * 1000)), hostname]
            else:  # Linux/Unix
                command = ['ping', '-c', '1', '-W', str(int(timeout)), hostname]
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout + 5  # Add buffer to subprocess timeout
            )
            
            if result.returncode == 0:
                logger.debug(f'ICMP ping successful to {hostname}')
                return True
            else:
                logger.debug(f'ICMP ping failed to {hostname}: {result.stderr}')
                return False
        
        except subprocess.TimeoutExpired:
            logger.warning(f'ICMP ping timeout to {hostname}')
            return False
        except FileNotFoundError:
            logger.warning('ping command not found - falling back to TCP ping only')
            return False
        except Exception as e:
            logger.error(f'Error in system ping to {hostname}: {e}')
            return False
    
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
            db.add('check', check_result)
            
            # Update history
            self.update_history(check_result)

            # Handle incident tracking
            monitor_data = db.get_by_id('monitor', check_result['monitor_id'])
            if monitor_data:
                monitor = Monitor(**monitor_data)
                self.handle_incident_tracking(monitor, check_result['is_up'], check_result.get('error_message'))
            
            # Invalidate performance cache for this monitor
            try:
                from app.performance import invalidate_monitor_cache
                invalidate_monitor_cache(check_result['monitor_id'])
            except Exception as cache_e:
                logger.debug(f'Cache invalidation error: {cache_e}')
            
        except Exception as e:
            logger.error(f'Error saving check result: {str(e)}')

    def update_history(self, check_result):
        """Update the history file with the latest check."""
        try:
            history = db.get_all('history')
            now = datetime.now(pytz.utc)
            
            # Add new check
            history.append({
                'monitor_id': check_result['monitor_id'],
                'checked_at': check_result['checked_at'],
                'response_time': check_result['response_time'],
                'is_up': check_result['is_up']
            })
            
            # Prune old data (older than 7 days)
            cutoff = now - timedelta(days=7)
            history_to_keep = []
            for h in history:
                checked_at = parse_timestamp(h.get('checked_at'))
                if checked_at and checked_at >= cutoff:
                    history_to_keep.append(h)
            
            db.write_data(db.model_files['history'], history_to_keep)
        except Exception as e:
            logger.error(f"Error updating history file: {e}")
    
    def is_in_maintenance(self):
        """Check if there is an active global maintenance window."""
        schedules_data = db.get_all('maintenance')
        now = datetime.now(pytz.utc)
        for s_data in schedules_data:
            schedule = Maintenance(**s_data)
            if schedule.is_active:
                logger.info(f"Active maintenance window: '{schedule.name}'")
                return True
        return False

    def handle_incident_tracking(self, monitor, is_up, error_message):
        """Handle incident creation and resolution."""
        all_incidents = db.get_all('incident')
        latest_incident_data = None
        for i in sorted(all_incidents, key=lambda x: x['started_at'], reverse=True):
            if i['monitor_id'] == monitor.id and not i.get('is_resolved', False):
                latest_incident_data = i
                break
        
        if not is_up:  # Monitor is down
            if self.is_in_maintenance():
                logger.info(f"Monitor {monitor.name} is down during a maintenance window. Suppressing incident.")
                return

            if not latest_incident_data:
                # Create new incident
                incident_data = {
                    'monitor_id': monitor.id,
                    'started_at': datetime.now(pytz.utc).isoformat(),
                    'error_message': error_message,
                    'is_resolved': False
                }
                new_incident = db.add('incident', incident_data)
                logger.warning(f'New incident created for monitor: {monitor.name}')
                
                # Send notifications for new incident
                self.send_notifications('incident_started', monitor, Incident(**new_incident))

                # Trigger 'on_down' commands
                self.trigger_on_down_commands(monitor.id)
                
        else:  # Monitor is up
            if latest_incident_data:
                # Resolve existing incident
                ended_at = datetime.now(pytz.utc)
                started_at = parse_timestamp(latest_incident_data['started_at'])
                duration = int((ended_at - started_at).total_seconds())
                
                update_data = {
                    'ended_at': ended_at.isoformat(),
                    'duration': duration,
                    'is_resolved': True
                }
                db.update('incident', latest_incident_data['id'], update_data)
                
                resolved_incident = Incident(**{**latest_incident_data, **update_data})
                logger.info(f'Incident resolved for monitor: {monitor.name} (Duration: {resolved_incident.duration_formatted})')
                
                # Send notifications for incident resolution
                self.send_notifications('incident_resolved', monitor, resolved_incident)

    def trigger_on_down_commands(self, monitor_id):
        """Trigger commands with 'on_down' trigger for a given monitor."""
        all_commands = db.get_all('command')
        for cmd_data in all_commands:
            if cmd_data.get('monitor_id') == monitor_id and cmd_data.get('trigger') == 'on_down':
                command = Command(**cmd_data)
                pending_command_data = {
                    'command_id': command.id,
                    'monitor_id': monitor_id,
                    'script': command.script,
                    'status': 'pending',
                }
                db.add('pending_command', pending_command_data)
                logger.info(f"Queued 'on_down' command '{command.name}' for monitor {monitor_id}")
    
    def run_checks(self):
        """Run checks for all active monitors that are due for checking."""
        try:
            now = datetime.now(pytz.utc)
            all_monitors_data = db.get_all('monitor')
            active_monitors = [Monitor(**m) for m in all_monitors_data if m.get('is_active', True)]
            all_checks_data = db.get_all('check')

            for monitor in active_monitors:
                # Check if monitor is due for checking
                monitor_checks = [c for c in all_checks_data if c['monitor_id'] == monitor.id]
                last_check = max(monitor_checks, key=lambda c: c['checked_at'], default=None)
                
                if not last_check or (now - parse_timestamp(last_check['checked_at'])).total_seconds() >= monitor.interval:
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
        """Send notifications through all active channels associated with the monitor."""
        try:
            all_channels_data = db.get_all('notification_channel')
            
            # Filter for active channels that are associated with this monitor
            relevant_channels = [
                NotificationChannel(**c) for c in all_channels_data 
                if c.get('is_active', True) and monitor.id in c.get('monitors', [])
            ]
            
            if not relevant_channels:
                logger.debug(f'No active notification channels configured for monitor: {monitor.name}')
                return
            
            logger.info(f"Found {len(relevant_channels)} relevant channel(s) for monitor '{monitor.name}'")

            for channel in relevant_channels:
                try:
                    # Prepare channel data for notification service
                    channel_data = {
                        'id': channel.id,
                        'name': channel.name,
                        'channel_type': channel.channel_type,
                        'config': channel.get_config()
                    }
                    
                    # Send notification
                    success = notification_service.send_notification(
                        channel_data, incident_type, monitor, incident
                    )
                    
                    if success:
                        logger.info(f'Notification sent successfully via {channel.channel_type} channel: {channel.name}')
                    else:
                        logger.error(f'Failed to send notification via {channel.channel_type} channel: {channel.name}')
                        
                except Exception as e:
                    logger.error(f'Error sending notification via channel {channel.name}: {str(e)}')
        
        except Exception as e:
            logger.error(f'Error in send_notifications: {str(e)}')
    
    def cleanup_old_data(self):
        """Clean up old check data and resolved incidents using the enhanced cleanup service."""
        try:
            from .cleanup import DataCleanupService
            
            cleanup_service = DataCleanupService(self.app)
            result = cleanup_service.run_full_cleanup()
            
            logger.info(f'Enhanced cleanup completed: {result["total_removed"]} total items removed')
            logger.debug(f'Cleanup breakdown: {result["results"]}')
            
            # Show performance notice if significant cleanup occurred
            total_removed = result.get('total_removed', 0)
            if total_removed > 1000:
                logger.warning(f'Large cleanup performed ({total_removed} items). Dashboard performance should improve.')
            
        except Exception as e:
            logger.error(f'Error in enhanced cleanup: {str(e)}')
            # Fallback to basic cleanup if enhanced fails
            try:
                self._basic_cleanup_fallback()
            except Exception as fallback_e:
                logger.error(f'Fallback cleanup also failed: {str(fallback_e)}')
    
    def _basic_cleanup_fallback(self):
        """Basic cleanup as fallback if enhanced cleanup fails."""
        try:
            # Clean up checks (reduced retention to 7 days for performance)
            cutoff_date_checks = datetime.now(pytz.utc) - timedelta(days=7)
            all_checks = db.get_all('check')
            checks_to_keep = [c for c in all_checks if parse_timestamp(c['checked_at']) >= cutoff_date_checks]
            
            if len(checks_to_keep) < len(all_checks):
                db.write_data(db.model_files['check'], checks_to_keep)
                logger.info(f'Basic cleanup: {len(all_checks) - len(checks_to_keep)} old checks removed')

            # Clean up incidents  
            cutoff_date_incidents = datetime.now(pytz.utc) - timedelta(days=90)
            all_incidents = db.get_all('incident')
            incidents_to_keep = [
                i for i in all_incidents 
                if not i.get('is_resolved') or not i.get('ended_at') or parse_timestamp(i['ended_at']) >= cutoff_date_incidents
            ]

            if len(incidents_to_keep) < len(all_incidents):
                db.write_data(db.model_files['incident'], incidents_to_keep)
                logger.info(f'Basic cleanup: {len(all_incidents) - len(incidents_to_keep)} old incidents removed')

        except Exception as e:
            logger.error(f'Error in basic cleanup fallback: {str(e)}')

def run_monitoring_service():
    """Main function to run the monitoring service."""
    app = create_app()
    with app.app_context():
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
