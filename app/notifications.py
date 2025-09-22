import smtplib
import requests
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class NotificationService:
    """Handle different types of notifications (email, webhook, etc.)."""
    
    def __init__(self):
        pass
    
    def send_notification(self, channel: Dict[str, Any], incident_type: str, monitor: Any, incident: Any = None):
        """Send notification through the specified channel."""
        try:
            channel_type = channel.get('channel_type', '').lower()
            
            if channel_type == 'email':
                return self.send_email_notification(channel, incident_type, monitor, incident)
            elif channel_type == 'webhook':
                return self.send_webhook_notification(channel, incident_type, monitor, incident)
            elif channel_type == 'slack':
                return self.send_slack_notification(channel, incident_type, monitor, incident)
            else:
                logger.error(f'Unsupported notification type: {channel_type}')
                return False
                
        except Exception as e:
            logger.error(f'Error sending notification: {str(e)}')
            return False
    
    def send_email_notification(self, channel: Dict[str, Any], incident_type: str, monitor: Any, incident: Any = None):
        """Send email notification with enhanced Gmail support and error handling."""
        try:
            config = channel.get('config', {})
            
            # Email configuration
            smtp_server = config.get('smtp_server')
            smtp_port = config.get('smtp_port')
            username = config.get('smtp_username')
            password = config.get('smtp_password')
            from_email = username or 'monitor@example.com'
            to_email = config.get('email_to')
            use_tls = config.get('use_tls', False)
            use_ssl = config.get('use_ssl', False)

            if not all([smtp_server, smtp_port, to_email]):
                logger.error('SMTP server, port, and recipient email are required.')
                return False

            # Enhanced Gmail configuration detection and optimization
            is_gmail = 'gmail.com' in smtp_server.lower()
            if is_gmail:
                logger.info('Gmail SMTP detected, applying Gmail-specific optimizations')
                # Gmail specific settings
                if smtp_port == 587:
                    use_tls = True
                    use_ssl = False
                elif smtp_port == 465:
                    use_ssl = True
                    use_tls = False
                else:
                    # Default Gmail settings
                    smtp_port = 587
                    use_tls = True
                    use_ssl = False
                    logger.info(f'Gmail: Using default port 587 with TLS')

            # Create message
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = self._get_email_subject(incident_type, monitor)
            
            # Create email body
            body = self._get_email_body(incident_type, monitor, incident)
            msg.attach(MIMEText(body, 'html'))
            
            # Send email with enhanced error handling and connection management
            server = None
            try:
                logger.info(f'Connecting to SMTP server: {smtp_server}:{smtp_port} (SSL: {use_ssl}, TLS: {use_tls})')
                
                # Enhanced connection handling
                if use_ssl:
                    # Use SMTP_SSL for SSL connections (port 465)
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
                    logger.info('Connected using SSL')
                else:
                    # Use regular SMTP for non-SSL connections (port 587)
                    server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                    logger.info('Connected using regular SMTP')
                    
                    # Upgrade to TLS if requested
                    if use_tls:
                        logger.info('Starting TLS...')
                        server.starttls()
                        logger.info('TLS enabled successfully')
                
                # Enhanced authentication with better error messages
                if username and password:
                    logger.info(f'Authenticating as: {username}')
                    
                    if is_gmail and not password.startswith('app-'):
                        logger.warning('Gmail detected but password might not be an App Password. For Gmail, use App Passwords instead of regular passwords.')
                    
                    server.login(username, password)
                    logger.info('Authentication successful')
                else:
                    logger.info('No authentication credentials provided')
                
                # Send the message
                logger.info(f'Sending email to: {to_email}')
                server.send_message(msg)
                logger.info(f'Email notification sent successfully to {to_email}')
                
                return True
                
            except smtplib.SMTPAuthenticationError as e:
                error_msg = f'SMTP Authentication failed: {str(e)}'
                if is_gmail:
                    error_msg += '. For Gmail, ensure you are using an App Password, not your regular password. Enable 2-factor authentication and generate an App Password at: https://myaccount.google.com/apppasswords'
                logger.error(error_msg)
                return False
                
            except smtplib.SMTPConnectError as e:
                error_msg = f'Failed to connect to SMTP server {smtp_server}:{smtp_port}: {str(e)}'
                if is_gmail:
                    error_msg += '. Verify Gmail SMTP settings: smtp.gmail.com:587 (TLS) or smtp.gmail.com:465 (SSL)'
                logger.error(error_msg)
                return False
                
            except smtplib.SMTPServerDisconnected as e:
                error_msg = f'SMTP server disconnected unexpectedly: {str(e)}'
                if is_gmail:
                    error_msg += '. This often indicates authentication issues or Gmail security settings blocking the connection.'
                logger.error(error_msg)
                return False
                
            except smtplib.SMTPException as e:
                logger.error(f'SMTP error occurred: {str(e)}')
                return False
                
            except ConnectionResetError as e:
                error_msg = f'Connection reset by server: {str(e)}'
                if is_gmail:
                    error_msg += '. This often happens with Gmail when using incorrect authentication or security settings.'
                logger.error(error_msg)
                return False
                
            except Exception as e:
                logger.error(f'Unexpected error sending email: {str(e)}')
                return False
                
            finally:
                # Properly close connection
                if server:
                    try:
                        server.quit()
                        logger.info('SMTP connection closed')
                    except Exception as e:
                        logger.warning(f'Error closing SMTP connection: {str(e)}')
            
        except Exception as e:
            logger.error(f'Error in send_email_notification: {str(e)}')
            return False
    
    def send_webhook_notification(self, channel: Dict[str, Any], incident_type: str, monitor: Any, incident: Any = None):
        """Send webhook notification."""
        try:
            config = channel.get('config', {})
            
            webhook_url = config.get('url')
            method = config.get('method', 'POST').upper()
            headers = config.get('headers', {})
            timeout = config.get('timeout', 30)
            
            if not webhook_url:
                logger.error('No webhook URL configured')
                return False
            
            # Prepare payload
            payload = {
                'type': incident_type,
                'monitor': {
                    'id': monitor.id,
                    'name': monitor.name,
                    'url': monitor.url,
                    'status': monitor.status
                },
                'timestamp': datetime.utcnow().isoformat(),
                'incident': None
            }
            
            if incident:
                payload['incident'] = {
                    'id': incident.id,
                    'started_at': incident.started_at.isoformat(),
                    'duration': incident.duration_formatted,
                    'error_message': incident.error_message,
                    'is_resolved': incident.is_resolved
                }
            
            # Set default headers
            if 'Content-Type' not in headers:
                headers['Content-Type'] = 'application/json'
            
            # Send webhook
            response = requests.request(
                method=method,
                url=webhook_url,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            response.raise_for_status()
            
            logger.info(f'Webhook notification sent successfully to {webhook_url}')
            return True
            
        except Exception as e:
            logger.error(f'Error sending webhook notification: {str(e)}')
            return False
    
    def send_slack_notification(self, channel: Dict[str, Any], incident_type: str, monitor: Any, incident: Any = None):
        """Send Slack notification using webhook."""
        try:
            config = channel.get('config', {})
            
            webhook_url = config.get('webhook_url')
            if not webhook_url:
                logger.error('No Slack webhook URL configured')
                return False
            
            # Create Slack message
            color = 'danger' if incident_type == 'incident_started' else 'good' if incident_type == 'incident_resolved' else 'warning'
            
            attachment = {
                'color': color,
                'title': f'Monitor Alert: {monitor.name}',
                'title_link': f'http://localhost:5000/monitors/{monitor.id}',
                'fields': [
                    {
                        'title': 'Monitor',
                        'value': monitor.name,
                        'short': True
                    },
                    {
                        'title': 'URL',
                        'value': monitor.url,
                        'short': True
                    },
                    {
                        'title': 'Status',
                        'value': monitor.status.upper(),
                        'short': True
                    },
                    {
                        'title': 'Time',
                        'value': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
                        'short': True
                    }
                ],
                'footer': 'Python Monitor',
                'ts': int(datetime.utcnow().timestamp())
            }
            
            if incident and incident_type == 'incident_started':
                attachment['text'] = f'🚨 Service is down: {incident.error_message or "Service unavailable"}'
            elif incident and incident_type == 'incident_resolved':
                attachment['text'] = f'✅ Service is back up! Downtime: {incident.duration_formatted}'
            else:
                attachment['text'] = f'ℹ️ Monitor status change for {monitor.name}'
            
            payload = {
                'attachments': [attachment]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=30)
            response.raise_for_status()
            
            logger.info(f'Slack notification sent successfully')
            return True
            
        except Exception as e:
            logger.error(f'Error sending Slack notification: {str(e)}')
            return False
    
    def _get_email_subject(self, incident_type: str, monitor: Any) -> str:
        """Generate email subject based on incident type."""
        if incident_type == 'incident_started':
            return f'🚨 ALERT: {monitor.name} is DOWN'
        elif incident_type == 'incident_resolved':
            return f'✅ RESOLVED: {monitor.name} is back UP'
        elif incident_type == 'test':
            return f'🧪 Test Notification: {monitor.name}'
        else:
            return f'📊 Monitor Update: {monitor.name}'
    
    def _get_email_body(self, incident_type: str, monitor: Any, incident: Any = None) -> str:
        """Generate HTML email body."""
        
        status_color = 'red' if incident_type == 'incident_started' else 'green' if incident_type == 'incident_resolved' else 'blue' if incident_type == 'test' else 'orange'
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: {status_color}; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 5px; margin: 10px 0; }}
                .footer {{ font-size: 12px; color: #666; text-align: center; margin-top: 20px; }}
                .info-table {{ width: 100%; border-collapse: collapse; }}
                .info-table th, .info-table td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                .info-table th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{self._get_email_subject(incident_type, monitor)}</h2>
                </div>
                
                <div class="content">
                    <h3>Monitor Details</h3>
                    <table class="info-table">
                        <tr><th>Monitor Name</th><td>{monitor.name}</td></tr>
                        <tr><th>URL</th><td>{monitor.url}</td></tr>
                        <tr><th>Type</th><td>{monitor.monitor_type.upper()}</td></tr>
                        <tr><th>Current Status</th><td>{monitor.status.upper()}</td></tr>
                        <tr><th>Timestamp</th><td>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
                    </table>
        """
        
        if incident:
            html += f"""
                    <h3>Incident Information</h3>
                    <table class="info-table">
                        <tr><th>Started At</th><td>{incident.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
            """
            
            if incident.ended_at:
                html += f"""
                        <tr><th>Ended At</th><td>{incident.ended_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
                        <tr><th>Duration</th><td>{incident.duration_formatted}</td></tr>
                """
            else:
                html += f"""
                        <tr><th>Duration</th><td>{incident.duration_formatted} (ongoing)</td></tr>
                """
            
            if incident.error_message:
                html += f"""
                        <tr><th>Error Message</th><td>{incident.error_message}</td></tr>
                """
            
            html += """
                    </table>
            """
        
        html += f"""
                </div>
                
                <div class="footer">
                    <p>This alert was sent by Python Monitor</p>
                    <p>View monitor details: <a href="http://localhost:5000/monitors/{monitor.id}">Monitor Dashboard</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

# Global notification service instance
notification_service = NotificationService()
