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
        """Send email notification."""
        try:
            config = channel.get('config', {})
            
            # Email configuration
            smtp_server = config.get('smtp_server')
            smtp_port = config.get('smtp_port')
            username = config.get('smtp_username')
            password = config.get('smtp_password')
            from_email = username or 'monitor@example.com' # Use username as from_email if available
            to_email = config.get('email_to')
            use_tls = config.get('use_tls', False)
            use_ssl = config.get('use_ssl', False)

            if not all([smtp_server, smtp_port, to_email]):
                logger.error('SMTP server, port, and recipient email are required.')
                return False

            # Create message
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = self._get_email_subject(incident_type, monitor)
            
            # Create email body
            body = self._get_email_body(incident_type, monitor, incident)
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
            server = None
            try:
                if use_ssl:
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port)
                else:
                    server = smtplib.SMTP(smtp_server, smtp_port)
                
                if use_tls:
                    server.starttls()
                
                if username and password:
                    server.login(username, password)
                
                server.send_message(msg)
                logger.info(f'Email notification sent successfully to {to_email}')
                return True
            finally:
                if server:
                    server.quit()
            
        except Exception as e:
            logger.error(f'Error sending email notification: {str(e)}')
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
