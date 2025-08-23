from datetime import datetime, timedelta
from app import db
from sqlalchemy import func
import json

class Monitor(db.Model):
    """Monitor configuration model."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    monitor_type = db.Column(db.String(20), default='http')  # http, https, ping, port
    method = db.Column(db.String(10), default='GET')  # GET, POST, PUT, etc.
    expected_status = db.Column(db.Integer, default=200)
    expected_text = db.Column(db.String(200), nullable=True)  # Text that should be in response
    timeout = db.Column(db.Integer, default=30)  # seconds
    interval = db.Column(db.Integer, default=60)  # seconds between checks
    retries = db.Column(db.Integer, default=3)
    headers = db.Column(db.Text, nullable=True)  # JSON string of headers
    body = db.Column(db.Text, nullable=True)  # Request body for POST/PUT
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    checks = db.relationship('MonitorCheck', backref='monitor', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Monitor {self.name}: {self.url}>'
    
    @property
    def status(self):
        """Get current status based on latest check."""
        latest_check = self.checks.order_by(MonitorCheck.checked_at.desc()).first()
        if not latest_check:
            return 'unknown'
        return 'up' if latest_check.is_up else 'down'
    
    @property
    def response_time(self):
        """Get latest response time."""
        latest_check = self.checks.order_by(MonitorCheck.checked_at.desc()).first()
        return latest_check.response_time if latest_check else None
    
    @property
    def uptime_percentage(self, days=7):
        """Calculate uptime percentage for the last N days."""
        since = datetime.utcnow() - timedelta(days=days)
        total_checks = self.checks.filter(MonitorCheck.checked_at >= since).count()
        if total_checks == 0:
            return 100.0
        
        up_checks = self.checks.filter(
            MonitorCheck.checked_at >= since,
            MonitorCheck.is_up == True
        ).count()
        
        return (up_checks / total_checks) * 100
    
    def get_parsed_headers(self):
        """Parse headers from JSON string."""
        if self.headers:
            try:
                return json.loads(self.headers)
            except json.JSONDecodeError:
                return {}
        return {}

class MonitorCheck(db.Model):
    """Individual monitor check result."""
    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey('monitor.id'), nullable=False)
    is_up = db.Column(db.Boolean, nullable=False)
    response_time = db.Column(db.Float, nullable=True)  # milliseconds
    status_code = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    response_text = db.Column(db.Text, nullable=True)  # First 1000 chars of response
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f'<MonitorCheck {self.monitor_id}: {"UP" if self.is_up else "DOWN"} at {self.checked_at}>'

class Incident(db.Model):
    """Downtime incident tracking."""
    id = db.Column(db.Integer, primary_key=True)
    monitor_id = db.Column(db.Integer, db.ForeignKey('monitor.id'), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    duration = db.Column(db.Integer, nullable=True)  # seconds
    error_message = db.Column(db.Text, nullable=True)
    is_resolved = db.Column(db.Boolean, default=False)
    
    # Relationships
    monitor = db.relationship('Monitor', backref='incidents')
    
    @property
    def duration_formatted(self):
        """Format duration in human-readable format."""
        if not self.duration:
            if self.ended_at and self.started_at:
                duration = int((self.ended_at - self.started_at).total_seconds())
            else:
                duration = int((datetime.utcnow() - self.started_at).total_seconds())
        else:
            duration = self.duration
        
        if duration < 60:
            return f"{duration}s"
        elif duration < 3600:
            return f"{duration // 60}m {duration % 60}s"
        else:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            return f"{hours}h {minutes}m"

class NotificationChannel(db.Model):
    """Notification channels for alerts."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # email, webhook, slack
    config = db.Column(db.Text, nullable=False)  # JSON configuration
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_config(self):
        """Parse configuration from JSON."""
        try:
            return json.loads(self.config)
        except json.JSONDecodeError:
            return {}