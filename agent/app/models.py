from datetime import datetime, timedelta
import json
import pytz
from flask_login import UserMixin
from .database import db
from .utils import parse_timestamp

class User(UserMixin):
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.username = kwargs.get('username')
        self.password = kwargs.get('password')
        self.role = kwargs.get('role')
        self.password_reset_required = kwargs.get('password_reset_required', False)

    @staticmethod
    def get(db_instance, user_id):
        user_data = db_instance.get_by_id('user', user_id)
        if user_data:
            return User(**user_data)
        return None

    @staticmethod
    def find_by_username(db_instance, username):
        users = db_instance.get_all('user')
        for user_data in users:
            if user_data['username'] == username:
                return User(**user_data)
        return None

class Monitor:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        self.url = kwargs.get('url')
        self.monitor_type = kwargs.get('monitor_type', 'http')
        self.method = kwargs.get('method', 'GET')
        self.expected_status = kwargs.get('expected_status', 200)
        self.expected_text = kwargs.get('expected_text', '')
        self.timeout = kwargs.get('timeout', 30)
        self.interval = kwargs.get('interval', 60)
        self.retries = kwargs.get('retries', 3)
        self.headers = kwargs.get('headers', '')
        self.body = kwargs.get('body', '')
        self.port = kwargs.get('port')
        self.is_active = kwargs.get('is_active', True)
        self.verify_ssl = kwargs.get('verify_ssl', True)
        self.check_cert_expiry = kwargs.get('check_cert_expiry', False)
        self.admin_notes = kwargs.get('admin_notes') or None
        self.admin_notes_text = kwargs.get('admin_notes_text') or None
        self.server_client = kwargs.get('server_client', False)
        self.log_files = kwargs.get('log_files', '')
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')

    @property
    def tags(self):
        """Get all tags associated with this monitor."""
        monitor_tags = db.get_all('monitor_tag')
        tag_ids = [mt['tag_id'] for mt in monitor_tags if mt['monitor_id'] == self.id]
        all_tags = db.get_all('tag')
        return [Tag(**t) for t in all_tags if t['id'] in tag_ids]

    @property
    def status(self):
        """Get current status based on latest check."""
        checks = db.get_all('check')
        latest_check = max([c for c in checks if c['monitor_id'] == self.id], key=lambda c: c['checked_at'], default=None)
        if not latest_check:
            return 'unknown'
        return 'up' if latest_check['is_up'] else 'down'

    @property
    def response_time(self):
        """Get latest response time."""
        checks = db.get_all('check')
        latest_check = max([c for c in checks if c['monitor_id'] == self.id], key=lambda c: c['checked_at'], default=None)
        return latest_check['response_time'] if latest_check else None

    @property
    def cert_expires_in_days(self):
        """Get latest cert_expires_in_days."""
        if not self.check_cert_expiry:
            return None
        checks = db.get_all('check')
        latest_check = max([c for c in checks if c['monitor_id'] == self.id], key=lambda c: c['checked_at'], default=None)
        return latest_check.get('cert_expires_in_days') if latest_check else None

    @property
    def uptime_percentage(self):
        """Calculate uptime percentage for the last 7 days."""
        days=7
        since = datetime.now(pytz.utc) - timedelta(days=days)
        checks = db.get_all('check')
        # Make naive datetime from DB timezone-aware for comparison
        relevant_checks = [c for c in checks if c.get('monitor_id') == self.id and c.get('checked_at') and parse_timestamp(c['checked_at']) >= since]
        total_checks = len(relevant_checks)
        if total_checks == 0:
            return 100.0
        
        up_checks = sum(1 for c in relevant_checks if c['is_up'])
        
        return (up_checks / total_checks) * 100

    @property
    def checks_last_4h(self):
        """
        Get a list of 48 checks representing the last 4 hours at 5-minute intervals.
        Empty slots will have an 'is_up' status of None.
        """
        num_slots = 48  # 4 hours * 12 intervals per hour
        now = datetime.now(pytz.utc)
        since = now - timedelta(hours=4)
        
        # Create 48 empty slots, each representing a 5-minute interval
        time_slots = [{'is_up': None, 'checked_at': (since + timedelta(minutes=i * 5)).isoformat()} for i in range(num_slots)]

        # Fetch actual checks from the database
        checks = db.get_all('check')
        relevant_checks = [
            c for c in checks 
            if c.get('monitor_id') == self.id and 
               c.get('checked_at') and 
               parse_timestamp(c['checked_at']) >= since
        ]
        
        if not relevant_checks:
            return time_slots

        # Sort checks to ensure the latest check in a slot is processed last
        sorted_relevant_checks = sorted(relevant_checks, key=lambda c: parse_timestamp(c['checked_at']))

        # Place actual checks into the correct time slot
        slot_duration_seconds = 300  # 5 minutes
        for check in sorted_relevant_checks:
            checked_at_dt = parse_timestamp(check['checked_at'])
            time_diff_seconds = (checked_at_dt - since).total_seconds()
            slot_index = int(time_diff_seconds / slot_duration_seconds)
            
            if 0 <= slot_index < num_slots:
                # Overwrite the placeholder. Since checks are sorted, this will be the latest check for that slot.
                time_slots[slot_index] = check

        return time_slots

    def get_checks_with_maintenance(self, all_schedules):
        """
        Get checks for the last 4 hours and enrich them with maintenance status.
        """
        # First, get the time-slotted checks
        slotted_checks = self.checks_last_4h
        
        # Find maintenance schedules relevant to this monitor
        relevant_schedules = [s for s in all_schedules if self.id in s.monitors]
        if not relevant_schedules:
            # If no maintenance, just add 'in_maintenance': False to each check
            for check in slotted_checks:
                check['in_maintenance'] = False
            return slotted_checks

        # Iterate through each check and see if it falls into a maintenance window
        for check in slotted_checks:
            check['in_maintenance'] = False # Default to not in maintenance
            if check.get('checked_at'):
                # Ensure the check's datetime is timezone-aware (UTC) for comparison
                checked_at_dt = parse_timestamp(check['checked_at'])
                
                for schedule in relevant_schedules:
                    if schedule.start_time and schedule.end_time:
                        # Ensure schedule times are aware for comparison
                        start_time = parse_timestamp(schedule.start_time.isoformat())
                        end_time = parse_timestamp(schedule.end_time.isoformat())
                        
                        if start_time <= checked_at_dt < end_time:
                            check['in_maintenance'] = True
                            break # Move to the next check once found in a schedule
        
        return slotted_checks

    def get_parsed_headers(self):
        """Parse headers from JSON string."""
        if self.headers and isinstance(self.headers, str):
            try:
                return json.loads(self.headers)
            except json.JSONDecodeError:
                return {}
        return {}

class MonitorCheck:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.monitor_id = kwargs.get('monitor_id')
        self.is_up = kwargs.get('is_up')
        self.response_time = kwargs.get('response_time')
        self.status_code = kwargs.get('status_code')
        self.error_message = kwargs.get('error_message')
        self.response_text = kwargs.get('response_text')
        self.cert_expires_in_days = kwargs.get('cert_expires_in_days')
        checked_at_str = kwargs.get('checked_at')
        self.checked_at = parse_timestamp(checked_at_str) if checked_at_str else None

class Incident:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.monitor_id = kwargs.get('monitor_id')
        # Ensure started_at is timezone-aware
        started_at_str = kwargs.get('started_at')
        self.started_at = parse_timestamp(started_at_str) if started_at_str else None
        
        # Ensure ended_at is timezone-aware
        ended_at_str = kwargs.get('ended_at')
        self.ended_at = parse_timestamp(ended_at_str) if ended_at_str else None
        self.duration = kwargs.get('duration')
        self.error_message = kwargs.get('error_message')
        self.is_resolved = kwargs.get('is_resolved', False)

    @property
    def monitor(self):
        """Get the associated monitor object."""
        monitor_data = db.get_by_id('monitor', self.monitor_id)
        return Monitor(**monitor_data) if monitor_data else None

    @property
    def duration_formatted(self):
        """Format duration in human-readable format."""
        if not self.duration:
            # Ensure both datetimes are timezone-aware
            started_at = self.started_at
            if self.ended_at:
                ended_at = self.ended_at
                duration = int((ended_at - started_at).total_seconds())
            else:
                duration = int((datetime.now(pytz.utc) - started_at).total_seconds())
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

class NotificationChannel:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        self.channel_type = kwargs.get('channel_type') or kwargs.get('type')
        self.config = kwargs.get('config', {})
        self.is_active = kwargs.get('is_active', True)
        self.created_at = kwargs.get('created_at')
        self.monitors = kwargs.get('monitors', [])

    def get_config(self):
        """Parse configuration from JSON."""
        if isinstance(self.config, str):
            try:
                return json.loads(self.config)
            except json.JSONDecodeError:
                return {}
        return self.config

class Maintenance:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        # Ensure start_time and end_time are timezone-aware
        start_time_str = kwargs.get('start_time')
        self.start_time = parse_timestamp(start_time_str) if start_time_str else None
        end_time_str = kwargs.get('end_time')
        self.end_time = parse_timestamp(end_time_str) if end_time_str else None
        self.description = kwargs.get('description')
        self.created_at = kwargs.get('created_at')
        self.monitors = kwargs.get('monitors', [])
        self.timezone = kwargs.get('timezone', 'UTC')

    @property
    def is_active(self):
        """Check if the maintenance window is currently active."""
        if not self.start_time or not self.end_time:
            return False
        now = datetime.now(pytz.utc)
        return self.start_time <= now < self.end_time

    @property
    def is_finished(self):
        """Check if the maintenance window has finished."""
        if not self.end_time:
            return False
        now = datetime.now(pytz.utc)
        return now >= self.end_time

class StatusPage:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        self.slug = kwargs.get('slug')
        self.monitors = kwargs.get('monitors', [])  # List of monitor IDs

    @property
    def monitor_objects(self):
        """Get the full monitor objects for the status page."""
        if not self.monitors:
            return []
        
        all_monitors_data = db.get_all('monitor')
        
        # Filter monitors that are in this status page's list
        status_page_monitors_data = [m for m in all_monitors_data if m['id'] in self.monitors]
        
        # Create Monitor objects
        return [Monitor(**data) for data in status_page_monitors_data]

class Tag:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        self.color = kwargs.get('color', '#6B7280')  # Default to gray
        self.created_at = kwargs.get('created_at')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'created_at': self.created_at
        }

class AgentMetric:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.monitor_id = kwargs.get('monitor_id')
        self.cpu_percent = kwargs.get('cpu_percent')
        self.ram_percent = kwargs.get('ram_percent')
        self.disks = kwargs.get('disks', {})
        self.network = kwargs.get('network', {})
        self.timestamp = kwargs.get('timestamp')
        self.created_at = kwargs.get('created_at', datetime.utcnow().isoformat())

class Command:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.monitor_id = kwargs.get('monitor_id')
        self.name = kwargs.get('name')
        self.script = kwargs.get('script')
        self.shell_type = kwargs.get('shell_type', 'powershell') # powershell or bash
        self.trigger = kwargs.get('trigger') # manual, schedule, on_down
        self.schedule = kwargs.get('schedule') # cron-like string for 'schedule' trigger
        self.created_at = kwargs.get('created_at')

class BackupConfig:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name', 'Auto Backup')
        self.backup_path = kwargs.get('backup_path')
        self.frequency = kwargs.get('frequency', 'weekly') # daily, weekly, monthly
        self.time = kwargs.get('time', '02:00') # HH:MM format
        self.day_of_week = kwargs.get('day_of_week', '0') # 0-6, Sunday=0
        self.day_of_month = kwargs.get('day_of_month', 1) # 1-28
        self.retention_days = kwargs.get('retention_days', 30)
        self.is_active = kwargs.get('is_active', True)
        self.include_logs = kwargs.get('include_logs', False)
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
        self.last_backup_at = kwargs.get('last_backup_at')
        self.last_backup_status = kwargs.get('last_backup_status') # success, failed
        self.last_backup_error = kwargs.get('last_backup_error')

    def get_cron_expression(self):
        """Generate cron expression based on frequency settings."""
        hour, minute = self.time.split(':')
        
        if self.frequency == 'daily':
            return f"{minute} {hour} * * *"
        elif self.frequency == 'weekly':
            return f"{minute} {hour} * * {self.day_of_week}"
        elif self.frequency == 'monthly':
            return f"{minute} {hour} {self.day_of_month} * *"
        
        return None
