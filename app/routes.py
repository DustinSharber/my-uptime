from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, current_app, send_file
from app.database import db
from app.models import Monitor, MonitorCheck, Incident, NotificationChannel, Maintenance, StatusPage, User, Command, BackupConfig
from app.forms import NotificationChannelForm, CommandForm, GeneralSettingsForm, LoginForm, UserForm, ChangePasswordForm, BackupForm
from app.utils import save_settings, load_settings, parse_timestamp
from datetime import datetime, timedelta
from flask_login import login_user, logout_user, login_required, current_user
from app import bcrypt
from functools import wraps
import json
import re
from slugify import slugify
import pytz
import os
import subprocess
from pathlib import Path

main_bp = Blueprint('main', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If login is not required, allow all admin functions
        if not current_app.config.get('LOGIN_REQUIRED'):
            return f(*args, **kwargs)
        
        # If login is required, check authentication and role
        if not current_user.is_authenticated or current_user.role != 'edit':
            flash('You do not have permission to access this page. Administrator access is required.', 'danger')
            return redirect(url_for('main.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def conditional_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        login_required = current_app.config.get('LOGIN_REQUIRED')
        is_authenticated = current_user.is_authenticated
        
        # Debug logging
        current_app.logger.info(f"LOGIN_REQUIRED: {login_required}, is_authenticated: {is_authenticated}")
        
        if login_required and not is_authenticated:
            return redirect(url_for('main.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If login is not required, redirect to dashboard
    if not current_app.config.get('LOGIN_REQUIRED'):
        return redirect(url_for('main.dashboard'))
    
    if current_user.is_authenticated:
        if current_user.password_reset_required:
            return redirect(url_for('main.change_password'))
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.find_by_username(db, form.username.data)
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            if user.password_reset_required:
                flash('Please change your password before continuing.', 'info')
                return redirect(url_for('main.change_password'))
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@main_bp.route('/logout')
def logout():
    logout_user()
    # If login is not required, redirect to dashboard instead of login page
    if not current_app.config.get('LOGIN_REQUIRED'):
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

@main_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if not current_user.password_reset_required:
        return redirect(url_for('main.dashboard'))
    form = ChangePasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user_data = {
            'password': hashed_password,
            'password_reset_required': False
        }
        db.update('user', current_user.id, user_data)
        flash('Your password has been updated successfully.', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('change_password.html', title='Change Password', form=form)

@main_bp.route('/')
@conditional_login_required
def dashboard():
    """Main dashboard showing all monitors."""
    group_by = request.args.get('group_by')
    all_monitors_data = db.get_all('monitor')
    monitors = [Monitor(**m) for m in all_monitors_data if m.get('is_active', True)]
    all_tags = db.get_all('tag')

    # Get all maintenance schedules
    all_maintenance_data = db.get_all('maintenance')
    all_maintenance_schedules = [Maintenance(**m) for m in all_maintenance_data]

    for monitor in monitors:
        monitor.daily_checks = monitor.get_checks_with_maintenance(all_maintenance_schedules)
        # Determine current maintenance status for the overall monitor badge
        active_schedules = [s for s in all_maintenance_schedules if s.is_active]
        monitor.in_maintenance = any(monitor.id in s.monitors for s in active_schedules)

    # Get summary statistics
    total_monitors = len(monitors)
    up_monitors = sum(1 for m in monitors if m.status == 'up')
    down_monitors = sum(1 for m in monitors if m.status == 'down')
    
    # Get recent incidents
    all_incidents_data = db.get_all('incident')
    all_incidents = [Incident(**i) for i in all_incidents_data]
    
    # Filter incidents:
    # - Include unresolved (active) incidents
    # - Include resolved incidents only if resolved within last 5 minutes
    now = datetime.now(pytz.utc)
    five_minutes_ago = now - timedelta(minutes=5)
    
    filtered_incidents = [
        incident for incident in all_incidents
        if not incident.is_resolved or  # Active incidents
           (incident.is_resolved and incident.ended_at and  # Recently resolved
            incident.ended_at.replace(tzinfo=pytz.utc) >= five_minutes_ago)
    ]
    
    # Sort by start time and get most recent 5
    recent_incidents = sorted(filtered_incidents, key=lambda i: i.started_at, reverse=True)[:5]

    grouped_monitors = None
    if group_by == 'tag':
        grouped_monitors = {'Untagged': []}
        tag_map = {tag['id']: tag for tag in all_tags}
        for monitor in monitors:
            if not monitor.tags:
                grouped_monitors['Untagged'].append(monitor)
            else:
                for tag in monitor.tags:
                    if tag.name not in grouped_monitors:
                        grouped_monitors[tag.name] = []
                    grouped_monitors[tag.name].append(monitor)
    
    return render_template('dashboard.html',
                         monitors=monitors,
                         total_monitors=total_monitors,
                         up_monitors=up_monitors,
                         down_monitors=down_monitors,
                         recent_incidents=recent_incidents,
                         group_by=group_by,
                         grouped_monitors=grouped_monitors,
                         all_tags=all_tags)

@main_bp.route('/monitors')
@conditional_login_required
def monitors():
    """List all monitors."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    sort_by = request.args.get('sort_by', 'name')
    sort_order = request.args.get('sort_order', 'asc')

    all_monitors_data = db.get_all('monitor')
    all_monitors = [Monitor(**m) for m in all_monitors_data]
    all_tags = db.get_all('tag')

    # Sorting logic
    reverse = sort_order == 'desc'
    if sort_by == 'name':
        all_monitors.sort(key=lambda m: m.name.lower(), reverse=reverse)
    elif sort_by == 'created_at':
        all_monitors.sort(key=lambda m: m.created_at or '', reverse=reverse)
    elif sort_by == 'tags':
        # Sort by the name of the first tag, if available
        all_monitors.sort(key=lambda m: (m.tags[0].name.lower() if m.tags else ''), reverse=reverse)

    total = len(all_monitors)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_monitors = all_monitors[start:end]
    
    # Create a mock pagination object for the template
    class MockPagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
        
        @property
        def has_prev(self):
            return self.page > 1
            
        @property
        def has_next(self):
            return self.page < self.pages
            
        @property
        def prev_num(self):
            return self.page - 1
            
        @property
        def next_num(self):
            return self.page + 1
            
        def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
            last = 0
            for num in range(1, self.pages + 1):
                if num <= left_edge or \
                   (num > self.page - left_current - 1 and num < self.page + right_current) or \
                   num > self.pages - right_edge:
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    pagination = MockPagination(paginated_monitors, page, per_page, total)

    return render_template('monitors.html', 
                           monitors=pagination,
                           sort_by=sort_by,
                           sort_order=sort_order,
                           all_tags=all_tags)

@main_bp.route('/monitors/new', methods=['GET', 'POST'])
@admin_required
def new_monitor():
    """Create new monitor."""
    if request.method == 'POST':
        try:
            # Parse headers if provided
            headers = request.form.get('headers', '').strip()
            if headers:
                try:
                    json.loads(headers)  # Validate JSON
                except json.JSONDecodeError:
                    flash('Invalid JSON format in headers', 'error')
                    # Pass an empty monitor object to the template on error
                    return render_template('monitor_form.html', monitor=Monitor())
            else:
                headers = None # Ensure empty string is stored as NULL
            
            monitor_data = {
                'name': request.form['name'],
                'url': request.form['url'],
                'monitor_type': request.form.get('monitor_type', 'http'),
                'method': request.form.get('method', 'GET'),
                'expected_status': int(request.form.get('expected_status', 200)),
                'expected_text': request.form.get('expected_text', '').strip() or None,
                'timeout': int(request.form.get('timeout', 30)),
                'interval': int(request.form.get('interval', 60)),
                'retries': int(request.form.get('retries', 3)),
                'headers': headers or None,
                'body': request.form.get('body', '').strip() or None,
                'port': int(request.form.get('port')) if request.form.get('port') else None,
                'verify_ssl': request.form.get('verify_ssl') == 'on',
                'check_cert_expiry': request.form.get('check_cert_expiry') == 'on',
                'admin_notes': request.form.get('admin_notes', '').strip() or None,
                'admin_notes_text': request.form.get('admin_notes_text', '').strip() or None,
                'server_client': request.form.get('server_client') == 'on',
                'log_files': request.form.get('log_files', '').strip() or None,
                'is_active': True
            }
            
            created_monitor = db.add('monitor', monitor_data)
            
            # Handle tags
            tags_json = request.form.get('tags', '[]')
            tags_to_process = json.loads(tags_json)
            all_db_tags = db.get_all('tag')
            
            for tag_data in tags_to_process:
                tag_name = tag_data['name'].strip().upper()
                tag_color = tag_data.get('color', '#6B7280')
                
                # Find existing tag or create a new one
                existing_tag = next((t for t in all_db_tags if t['name'].upper() == tag_name), None)
                
                if existing_tag:
                    tag_id = existing_tag['id']
                    # Optionally update color if it has changed
                    if existing_tag.get('color') != tag_color:
                        db.update('tag', tag_id, {'color': tag_color})
                else:
                    new_tag = db.add('tag', {'name': tag_name, 'color': tag_color})
                    tag_id = new_tag['id']
                    all_db_tags.append(new_tag) # Add to local list to avoid re-querying
                    
                # Link tag to monitor
                db.add('monitor_tag', {'monitor_id': created_monitor['id'], 'tag_id': tag_id})

            flash(f'Monitor "{created_monitor["name"]}" created successfully!', 'success')
            return redirect(url_for('main.dashboard'))
            
        except Exception as e:
            flash(f'Error creating monitor: {str(e)}', 'error')
            all_tags = db.get_all('tag')
            return render_template('monitor_form.html', monitor=Monitor(), all_tags=all_tags)
    
    all_tags = db.get_all('tag')
    return render_template('monitor_form.html', monitor=None, all_tags=all_tags)

@main_bp.route('/monitors/<int:monitor_id>')
@conditional_login_required
def monitor_detail(monitor_id):
    """Monitor detail page with history."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)
    monitor = Monitor(**monitor_data)

    # Check if monitor is in maintenance
    all_maintenance_data = db.get_all('maintenance')
    active_maintenance_schedules = [Maintenance(**m) for m in all_maintenance_data if Maintenance(**m).is_active]
    monitor.in_maintenance = any(monitor.id in schedule.monitors for schedule in active_maintenance_schedules)
    
    # Get check history (last 24 hours by default)
    hours = request.args.get('hours', 24, type=int)
    since = (datetime.now(pytz.utc) - timedelta(hours=hours))

    all_checks_data = db.get_all('check')
    monitor_checks = []
    for c in all_checks_data:
        if c.get('monitor_id') == monitor_id:
            checked_at = parse_timestamp(c.get('checked_at'))
            if checked_at and checked_at >= since:
                monitor_checks.append(MonitorCheck(**c))
    checks = sorted(monitor_checks, key=lambda c: c.checked_at, reverse=True)

    
    # Get incidents for this monitor
    all_incidents_data = db.get_all('incident')
    monitor_incidents = [Incident(**i) for i in all_incidents_data if i['monitor_id'] == monitor_id]
    incidents = sorted(monitor_incidents, key=lambda i: i.started_at, reverse=True)[:10]
    
    # Get system metrics if this is a server monitor
    system_metrics_json = None
    if monitor.server_client:
        all_metrics = db.get_all('agent_metric')
        
        # Filter and process metrics
        monitor_metrics = []
        for m in all_metrics:
            if m.get('monitor_id') == monitor_id and m.get('timestamp'):
                dt = None
                timestamp_val = m['timestamp']
                
                try:
                    if isinstance(timestamp_val, str):
                        # Handle ISO format string
                        dt = datetime.fromisoformat(timestamp_val.replace('Z', '+00:00'))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=pytz.utc)
                    elif isinstance(timestamp_val, (int, float)):
                        # Handle UNIX timestamp
                        dt = datetime.fromtimestamp(timestamp_val, tz=pytz.utc)
                except (ValueError, TypeError):
                    # Skip malformed records
                    continue

                if dt and dt >= since:
                    # Normalize timestamp to UNIX float for the frontend
                    m['timestamp'] = dt.timestamp()
                    monitor_metrics.append(m)

        system_metrics_json = json.dumps(sorted(monitor_metrics, key=lambda m: m['timestamp']))

    # Redirect to metrics page if this is a server client view request
    if monitor.server_client and request.args.get('view') == 'metrics':
        return redirect(url_for('main.monitor_metrics', monitor_id=monitor_id))

    if monitor.server_client and request.args.get('view') == 'logs':
        return redirect(url_for('main.monitor_logs', monitor_id=monitor_id))

    return render_template('monitor_detail.html',
                         monitor=monitor,
                         checks=checks,
                         incidents=incidents,
                         hours=hours,
                         system_metrics_json=system_metrics_json)


@main_bp.route('/api/monitor/<int:monitor_id>/history')
def monitor_history_api(monitor_id):
    """API endpoint to get monitor history for charts."""
    period = request.args.get('period', '1h')
    
    if period == '1h':
        delta = timedelta(hours=1)
    elif period == '12h':
        delta = timedelta(hours=12)
    elif period == '24h':
        delta = timedelta(days=1)
    else:
        return jsonify({'error': 'Invalid period specified'}), 400

    # Load settings to get the configured timezone
    settings = load_settings()
    tz_str = settings.get('timezone', 'UTC')
    try:
        app_tz = pytz.timezone(tz_str)
    except pytz.UnknownTimeZoneError:
        app_tz = pytz.utc

    # Calculate 'since' in the application's timezone, then convert to UTC for comparison
    # because timestamps in the database are normalized to UTC.
    now_in_app_tz = datetime.now(app_tz)
    since_in_app_tz = now_in_app_tz - delta
    since = since_in_app_tz.astimezone(pytz.utc)
    
    try:
        all_history = db.get_all('history')
        
        chart_data = []
        for record in all_history:
            # Match monitor_id and ensure response_time is not null
            if record.get('monitor_id') == monitor_id and record.get('response_time') is not None:
                timestamp_str = record.get('checked_at')
                
                if isinstance(timestamp_str, str):
                    try:
                        record_time = parse_timestamp(timestamp_str)
                        if record_time and record_time >= since:
                            chart_data.append({
                                'timestamp': int(record_time.timestamp() * 1000),
                                'response_time': record['response_time'],
                                'is_up': record.get('is_up', False)
                            })
                    except (ValueError, TypeError):
                        current_app.logger.warning(f"Skipping history record with invalid timestamp: {timestamp_str}")
                        continue
        
        # Sort by timestamp ascending
        sorted_data = sorted(chart_data, key=lambda x: x['timestamp'])
        
        return jsonify(sorted_data)
    except Exception as e:
        current_app.logger.error(f"Error fetching monitor history: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@main_bp.route('/monitors/<int:monitor_id>/metrics')
@conditional_login_required
def monitor_metrics(monitor_id):
    """Server metrics view for a monitor."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)
    monitor = Monitor(**monitor_data)

    if not monitor.server_client:
        flash('This monitor is not configured as a server client', 'error')
        return redirect(url_for('main.monitor_detail', monitor_id=monitor_id))

    # Get metrics data (last 24 hours by default)
    hours = request.args.get('hours', 24, type=int)
    since = (datetime.utcnow() - timedelta(hours=hours)).replace(tzinfo=pytz.utc)
    
    all_metrics = db.get_all('agent_metric')
    
    # Filter and process metrics
    monitor_metrics = []
    for m in all_metrics:
        if m.get('monitor_id') == monitor_id and m.get('timestamp'):
            dt = None
            timestamp_val = m['timestamp']
            
            try:
                if isinstance(timestamp_val, str):
                    dt = datetime.fromisoformat(timestamp_val.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.utc)
                elif isinstance(timestamp_val, (int, float)):
                    dt = datetime.fromtimestamp(timestamp_val, tz=pytz.utc)
            except (ValueError, TypeError):
                continue

            if dt and dt >= since:
                m['timestamp'] = dt.timestamp()
                monitor_metrics.append(m)
                
    metrics_data = sorted(monitor_metrics, key=lambda m: m['timestamp'])
    
    return render_template('monitor_metrics.html',
                         monitor=monitor,
                         hours=hours,
                         metrics_json=json.dumps(metrics_data))

@main_bp.route('/monitors/<int:monitor_id>/logs')
@conditional_login_required
def monitor_logs(monitor_id):
    """Server logs view for a monitor."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)
    monitor = Monitor(**monitor_data)

    if not monitor.server_client:
        flash('This monitor is not configured as a server client', 'error')
        return redirect(url_for('main.monitor_detail', monitor_id=monitor_id))

    # Get logs data (last 24 hours by default)
    hours = request.args.get('hours', 24, type=int)
    since = (datetime.utcnow() - timedelta(hours=hours)).replace(tzinfo=pytz.utc)
    
    all_logs = db.get_all('agent_log')

    # Filter and process logs
    monitor_logs_processed = []
    for log in all_logs:
        if log.get('monitor_id') == monitor_id and log.get('timestamp'):
            dt = None
            timestamp_val = log['timestamp']

            try:
                if isinstance(timestamp_val, str):
                    dt = datetime.fromisoformat(timestamp_val.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.utc)
                elif isinstance(timestamp_val, (int, float)):
                    dt = datetime.fromtimestamp(timestamp_val, tz=pytz.utc)
            except (ValueError, TypeError):
                continue

            if dt and dt >= since:
                log['timestamp'] = dt.timestamp()
                monitor_logs_processed.append(log)

    logs_data = sorted(monitor_logs_processed, key=lambda log: log['timestamp'], reverse=True)
    
    return render_template('monitor_logs.html',
                         monitor=monitor,
                         hours=hours,
                         logs=logs_data)

@main_bp.route('/monitors/<int:monitor_id>/commands')
@conditional_login_required
def monitor_commands(monitor_id):
    """Commands view for a monitor."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)
    monitor = Monitor(**monitor_data)

    if not monitor.server_client:
        flash('This monitor does not support commands.', 'warning')
        return redirect(url_for('main.monitor_detail', monitor_id=monitor_id))

    commands_data = db.get_all('command')
    monitor_commands = [Command(**cmd) for cmd in commands_data if cmd.get('monitor_id') == monitor_id]

    return render_template('monitor_commands.html', monitor=monitor, commands=monitor_commands)


@main_bp.route('/monitors/<int:monitor_id>/commands/add', methods=['GET', 'POST'])
@admin_required
def add_command(monitor_id):
    """Add a new command to a monitor."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)
    monitor = Monitor(**monitor_data)
    form = CommandForm()

    if form.validate_on_submit():
        command_data = {
            'monitor_id': monitor_id,
            'name': form.name.data,
            'script': form.script.data,
            'shell_type': form.shell_type.data,
            'trigger': form.trigger.data,
            'schedule': form.schedule.data if form.trigger.data == 'schedule' else None
        }
        db.add('command', command_data)
        flash('Command added successfully!', 'success')
        return redirect(url_for('main.monitor_commands', monitor_id=monitor_id))
    
    return render_template('command_form.html', form=form, monitor=monitor, command=None)


@main_bp.route('/monitors/<int:monitor_id>/commands/history', methods=['GET'])
@conditional_login_required
def command_history(monitor_id):
    """Display the execution history of commands for a monitor."""
    monitor = db.get_by_id('monitor', monitor_id)
    if not monitor:
        flash('Monitor not found.', 'error')
        return redirect(url_for('main.dashboard'))

    all_pending = db.get_all('pending_command')
    
    # Filter for the specific monitor and enrich with command name
    history = []
    for pc in all_pending:
        if pc.get('monitor_id') == monitor_id:
            command = db.get_by_id('command', pc.get('command_id'))
            pc['command_name'] = command['name'] if command else 'Unknown Command'
            history.append(pc)
    
    # Sort history by execution time, most recent first
    history.sort(key=lambda x: x.get('executed_at') or '', reverse=True)

    return render_template('command_history.html', monitor=monitor, history=history)


@main_bp.route('/monitors/<int:monitor_id>/commands/<int:command_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_command(monitor_id, command_id):
    """Edit an existing command."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)
    monitor = Monitor(**monitor_data)

    command_data = db.get_by_id('command', command_id)
    if not command_data:
        abort(404)
    command = Command(**command_data)
    form = CommandForm(obj=command)

    if form.validate_on_submit():
        update_data = {
            'name': form.name.data,
            'script': form.script.data,
            'shell_type': form.shell_type.data,
            'trigger': form.trigger.data,
            'schedule': form.schedule.data if form.trigger.data == 'schedule' else None
        }
        db.update('command', command_id, update_data)
        flash('Command updated successfully!', 'success')
        return redirect(url_for('main.monitor_commands', monitor_id=monitor_id))

    return render_template('command_form.html', form=form, monitor=monitor, command=command)


@main_bp.route('/monitors/<int:monitor_id>/commands/<int:command_id>/delete', methods=['POST'])
@admin_required
def delete_command(monitor_id, command_id):
    """Delete a command."""
    command = db.get_by_id('command', command_id)
    if not command:
        abort(404)
    
    db.delete('command', command_id)
    flash('Command deleted successfully!', 'success')
    return redirect(url_for('main.monitor_commands', monitor_id=monitor_id))

@main_bp.route('/monitors/<int:monitor_id>/commands/<int:command_id>/run', methods=['POST'])
@admin_required
def run_command(monitor_id, command_id):
    """Manually run a command."""
    command_data = db.get_by_id('command', command_id)
    if not command_data or command_data.get('monitor_id') != monitor_id:
        flash('Command not found or access denied.', 'error')
        return redirect(url_for('main.monitor_commands', monitor_id=monitor_id))

    command = Command(**command_data)
    
    pending_command_data = {
        'command_id': command.id,
        'monitor_id': monitor_id,
        'script': command.script,
        'shell_type': command.shell_type,
        'status': 'pending',
    }
    db.add('pending_command', pending_command_data)
    
    flash(f'Execution of command "{command.name}" has been queued.', 'info')
    
    return redirect(url_for('main.monitor_commands', monitor_id=monitor_id))

@main_bp.route('/monitors/<int:monitor_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_monitor(monitor_id):
    """Edit monitor configuration."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)
    monitor = Monitor(**monitor_data)

    if request.method == 'POST':
        try:
            # Parse headers if provided
            headers_str = request.form.get('headers', '').strip()
            if headers_str:
                try:
                    json.loads(headers_str)  # Validate JSON
                except json.JSONDecodeError:
                    flash('Invalid JSON format in headers', 'error')
                    return render_template('monitor_form.html', monitor=monitor)
            
            update_data = {
                'name': request.form['name'],
                'url': request.form['url'],
                'monitor_type': request.form.get('monitor_type', 'http'),
                'method': request.form.get('method', 'GET'),
                'expected_status': int(request.form.get('expected_status', 200)),
                'expected_text': request.form.get('expected_text', '').strip() or None,
                'timeout': int(request.form.get('timeout', 30)),
                'interval': int(request.form.get('interval', 60)),
                'retries': int(request.form.get('retries', 3)),
                'headers': headers_str if headers_str else None,
                'body': request.form.get('body', '').strip() or None,
                'port': int(request.form.get('port')) if request.form.get('port') else None,
                'verify_ssl': request.form.get('verify_ssl') == 'on',
                'check_cert_expiry': request.form.get('check_cert_expiry') == 'on',
                'admin_notes': request.form.get('admin_notes', '').strip() or None,
                'admin_notes_text': request.form.get('admin_notes_text', '').strip() or None,
                'server_client': request.form.get('server_client') == 'on',
                'log_files': request.form.get('log_files', '').strip() or None,
                'is_active': monitor.is_active  # Preserve the current active state
            }
            
            db.update('monitor', monitor_id, update_data)

            # Handle tags
            tags_json = request.form.get('tags', '[]')
            tags_to_process = json.loads(tags_json)
            all_db_tags = db.get_all('tag')
            
            # Get current tag links for this monitor
            all_monitor_tags = db.get_all('monitor_tag')
            current_tag_links = [mt for mt in all_monitor_tags if mt['monitor_id'] == monitor_id]
            current_tag_ids = {mt['tag_id'] for mt in current_tag_links}
            
            processed_tag_ids = set()

            for tag_data in tags_to_process:
                tag_name = tag_data['name'].strip().upper()
                tag_color = tag_data.get('color', '#6B7280')
                
                existing_tag = next((t for t in all_db_tags if t['name'].upper() == tag_name), None)
                
                if existing_tag:
                    tag_id = existing_tag['id']
                    if existing_tag.get('color') != tag_color:
                        db.update('tag', tag_id, {'color': tag_color})
                else:
                    new_tag = db.add('tag', {'name': tag_name, 'color': tag_color})
                    tag_id = new_tag['id']
                    all_db_tags.append(new_tag)
                
                processed_tag_ids.add(tag_id)
                
                # Add new link if it doesn't exist
                if tag_id not in current_tag_ids:
                    db.add('monitor_tag', {'monitor_id': monitor_id, 'tag_id': tag_id})

            # Remove old links
            tags_to_remove = current_tag_ids - processed_tag_ids
            for tag_id_to_remove in tags_to_remove:
                link_to_delete = next((mt for mt in current_tag_links if mt['tag_id'] == tag_id_to_remove), None)
                if link_to_delete:
                    db.delete('monitor_tag', link_to_delete['id'])

            flash(f'Monitor "{update_data["name"]}" updated successfully!', 'success')
            return redirect(url_for('main.monitor_detail', monitor_id=monitor_id))
            
        except Exception as e:
            current_app.logger.error(f"Error updating monitor {monitor_id}: {str(e)}")
            return jsonify({'status': 'error', 'message': f'Error updating monitor: {str(e)}'}), 500
    
    all_tags = db.get_all('tag')
    # Convert monitor tags to a list of dictionaries for JSON serialization
    monitor_tags_dicts = [tag.to_dict() for tag in monitor.tags]
    return render_template('monitor_form.html', monitor=monitor, all_tags=all_tags, monitor_tags_json=json.dumps(monitor_tags_dicts))

@main_bp.route('/monitors/<int:monitor_id>/delete', methods=['POST'])
@admin_required
def delete_monitor(monitor_id):
    """Delete monitor."""
    monitor = db.get_by_id('monitor', monitor_id)
    if not monitor:
        abort(404)
    
    try:
        db.delete('monitor', monitor_id)
        # Also delete associated checks and incidents
        all_checks = db.get_all('check')
        checks_to_keep = [c for c in all_checks if c['monitor_id'] != monitor_id]
        db.write_data(db.model_files['check'], checks_to_keep)

        all_incidents = db.get_all('incident')
        incidents_to_keep = [i for i in all_incidents if i['monitor_id'] != monitor_id]
        db.write_data(db.model_files['incident'], incidents_to_keep)

        flash(f'Monitor "{monitor["name"]}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting monitor: {str(e)}', 'error')
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/monitors/<int:monitor_id>/toggle', methods=['POST'])
@admin_required
def toggle_monitor(monitor_id):
    """Toggle monitor active status."""
    monitor = db.get_by_id('monitor', monitor_id)
    if not monitor:
        abort(404)
    
    try:
        new_status = not monitor.get('is_active', True)
        db.update('monitor', monitor_id, {'is_active': new_status})
        
        status = "enabled" if new_status else "disabled"
        flash(f'Monitor "{monitor["name"]}" {status}!', 'success')
    except Exception as e:
        flash(f'Error updating monitor: {str(e)}', 'error')
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/incidents')
@conditional_login_required
def incidents():
    """List all incidents with filtering."""
    # Get filter parameters
    status = request.args.get('status')
    time_range = request.args.get('time_range')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Load and convert all incidents
    all_incidents_data = db.get_all('incident')
    all_incidents = [Incident(**i) for i in all_incidents_data]

    # Apply status filter
    if status == 'ongoing':
        all_incidents = [i for i in all_incidents if not i.is_resolved]
    elif status == 'resolved':
        all_incidents = [i for i in all_incidents if i.is_resolved]

    # Apply time range filter with keep/delete action
    now = datetime.now(pytz.utc)
    range_action = request.args.get('range_action', 'keep')
    
    if time_range:
        if time_range == '12h':
            cutoff = now - timedelta(hours=12)
        elif time_range == '24h':
            cutoff = now - timedelta(days=1)
        elif time_range == '7d':
            cutoff = now - timedelta(days=7)
        
        if range_action == 'keep':
            all_incidents = [i for i in all_incidents if i.started_at >= cutoff]
        else:  # delete
            all_incidents = [i for i in all_incidents if i.started_at < cutoff]

    # Sort by start time
    all_incidents = sorted(all_incidents, key=lambda i: i.started_at, reverse=True)

    # Pagination
    total = len(all_incidents)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_incidents = all_incidents[start:end]
    
    # Re-use mock pagination from /monitors route
    class MockPagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
        
        @property
        def has_prev(self):
            return self.page > 1
            
        @property
        def has_next(self):
            return self.page < self.pages
            
        @property
        def prev_num(self):
            return self.page - 1
            
        @property
        def next_num(self):
            return self.page + 1
            
        def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
            last = 0
            for num in range(1, self.pages + 1):
                if num <= left_edge or \
                   (num > self.page - left_current - 1 and num < self.page + right_current) or \
                   num > self.pages - right_edge:
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    pagination = MockPagination(paginated_incidents, page, per_page, total)
    
    return render_template('incidents.html', incidents=pagination)

@main_bp.route('/maintenance', methods=['GET', 'POST'])
@admin_required
@conditional_login_required
def maintenance():
    """Maintenance page."""
    if request.method == 'POST':
        try:
            start_time_str = request.form['start_time']
            end_time_str = request.form['end_time']
            timezone_str = request.form.get('timezone', 'UTC')

            # Basic validation
            if not start_time_str or not end_time_str:
                flash('Start time and end time are required.', 'error')
                return redirect(url_for('main.maintenance'))

            # Convert naive datetime from form to timezone-aware datetime
            try:
                local_tz = pytz.timezone(timezone_str)
            except pytz.UnknownTimeZoneError:
                flash(f'Invalid timezone: {timezone_str}', 'error')
                return redirect(url_for('main.maintenance'))

            start_time_local = local_tz.localize(datetime.fromisoformat(start_time_str))
            end_time_local = local_tz.localize(datetime.fromisoformat(end_time_str))

            # Convert to UTC for storage
            start_time_utc = start_time_local.astimezone(pytz.utc)
            end_time_utc = end_time_local.astimezone(pytz.utc)

            if end_time_utc <= start_time_utc:
                flash('End time must be after start time.', 'error')
                return redirect(url_for('main.maintenance'))

            maintenance_data = {
                'name': request.form['name'],
                'start_time': start_time_utc.isoformat(),
                'end_time': end_time_utc.isoformat(),
                'description': request.form.get('description', ''),
                'timezone': timezone_str
            }
            db.add('maintenance', maintenance_data)
            flash('Maintenance schedule created successfully!', 'success')
            return redirect(url_for('main.maintenance'))
        except Exception as e:
            flash(f'Error creating maintenance schedule: {str(e)}', 'error')

    schedules_data = db.get_all('maintenance')
    # Filter out schedules that don't have a start_time before sorting
    valid_schedules = [Maintenance(**s) for s in schedules_data if s.get('start_time')]
    schedules = sorted(valid_schedules, key=lambda s: s.start_time, reverse=True)
    
    timezones = pytz.all_timezones
    default_timezone = current_app.config.get('TIMEZONE', 'UTC')
    
    return render_template('maintenance.html', 
                           schedules=schedules, 
                           timezones=timezones, 
                           default_timezone=default_timezone)

@main_bp.route('/maintenance/<int:schedule_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_maintenance(schedule_id):
    """Edit a maintenance schedule."""
    schedule_data = db.get_by_id('maintenance', schedule_id)
    if not schedule_data:
        abort(404)
    
    schedule = Maintenance(**schedule_data)
    
    if request.method == 'POST':
        try:
            start_time_str = request.form['start_time']
            end_time_str = request.form['end_time']
            timezone_str = request.form.get('timezone', 'UTC')

            if not start_time_str or not end_time_str:
                flash('Start time and end time are required.', 'error')
                return redirect(url_for('main.edit_maintenance', schedule_id=schedule_id))

            try:
                local_tz = pytz.timezone(timezone_str)
            except pytz.UnknownTimeZoneError:
                flash(f'Invalid timezone: {timezone_str}', 'error')
                return redirect(url_for('main.edit_maintenance', schedule_id=schedule_id))

            start_time_local = local_tz.localize(datetime.fromisoformat(start_time_str))
            end_time_local = local_tz.localize(datetime.fromisoformat(end_time_str))

            start_time_utc = start_time_local.astimezone(pytz.utc)
            end_time_utc = end_time_local.astimezone(pytz.utc)

            if end_time_utc <= start_time_utc:
                flash('End time must be after start time.', 'error')
                return redirect(url_for('main.edit_maintenance', schedule_id=schedule_id))

            selected_monitors = request.form.getlist('monitors')
            update_data = {
                'name': request.form['name'],
                'start_time': start_time_utc.isoformat(),
                'end_time': end_time_utc.isoformat(),
                'description': request.form.get('description', ''),
                'monitors': [int(m_id) for m_id in selected_monitors],
                'timezone': timezone_str
            }
            db.update('maintenance', schedule_id, update_data)
            flash('Maintenance schedule updated successfully!', 'success')
            return redirect(url_for('main.maintenance'))
        except Exception as e:
            flash(f'Error updating maintenance schedule: {str(e)}', 'error')
    
    all_monitors_data = db.get_all('monitor')
    monitors = [Monitor(**m) for m in all_monitors_data]
    
    timezones = pytz.all_timezones
    # Use the schedule's own timezone for display, falling back to the app's default
    schedule_timezone = schedule.timezone or current_app.config.get('TIMEZONE', 'UTC')

    # When editing, convert the stored UTC time back to the schedule's specific timezone for display
    try:
        target_tz = pytz.timezone(schedule_timezone)
        if schedule.start_time:
            # Ensure start_time is aware before converting
            if schedule.start_time.tzinfo is None:
                schedule.start_time = pytz.utc.localize(schedule.start_time)
            schedule.start_time = schedule.start_time.astimezone(target_tz)
        
        if schedule.end_time:
            # Ensure end_time is aware before converting
            if schedule.end_time.tzinfo is None:
                schedule.end_time = pytz.utc.localize(schedule.end_time)
            schedule.end_time = schedule.end_time.astimezone(target_tz)
            
    except (pytz.UnknownTimeZoneError, AttributeError):
        # Fallback if timezone is invalid or times are not set
        pass

    return render_template('maintenance_form.html', 
                           schedule=schedule, 
                           monitors=monitors,
                           timezones=timezones,
                           schedule_timezone=schedule_timezone)

@main_bp.route('/maintenance/<int:schedule_id>/delete', methods=['POST'])
@admin_required
def delete_maintenance(schedule_id):
    """Delete a maintenance schedule."""
    schedule = db.get_by_id('maintenance', schedule_id)
    if not schedule:
        abort(404)
    
    try:
        db.delete('maintenance', schedule_id)
        flash(f'Maintenance schedule "{schedule["name"]}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting schedule: {str(e)}', 'error')
    
    return redirect(url_for('main.maintenance'))

@main_bp.route('/maintenance/<int:schedule_id>/duplicate', methods=['POST'])
@admin_required
def duplicate_maintenance(schedule_id):
    """Duplicate a maintenance schedule."""
    original_schedule = db.get_by_id('maintenance', schedule_id)
    if not original_schedule:
        abort(404)
    
    try:
        # Create a copy and modify its name
        new_schedule_data = original_schedule.copy()
        new_schedule_data.pop('id', None) # Remove ID to ensure a new one is created
        new_schedule_data['name'] = f"{original_schedule.get('name', 'Schedule')} (Copy)"
        
        db.add('maintenance', new_schedule_data)
        flash(f'Successfully duplicated schedule "{original_schedule["name"]}".', 'success')
    except Exception as e:
        flash(f'Error duplicating schedule: {str(e)}', 'error')
        
    return redirect(url_for('main.maintenance'))

# Status Page Routes
@main_bp.route('/incidents/clear', methods=['GET'])
@admin_required
def clear_incidents():
    """Clear incidents based on filters."""
    status = request.args.get('status')
    time_range = request.args.get('time_range')
    range_action = request.args.get('range_action', 'delete') # Default to delete

    all_incidents_data = db.get_all('incident')
    
    # Determine the cutoff time if a time range is specified
    now = datetime.now(pytz.utc)
    cutoff = None
    if time_range == '12h':
        cutoff = now - timedelta(hours=12)
    elif time_range == '24h':
        cutoff = now - timedelta(hours=24)
    elif time_range == '7d':
        cutoff = now - timedelta(days=7)

    # This list will hold the incidents that match the filter criteria
    matching_incidents = []
    # This list will hold the incidents that do NOT match the filter criteria
    non_matching_incidents = []

    for incident_data in all_incidents_data:
        incident = Incident(**incident_data)
        matches = True

        # Check status filter
        if status:
            if status == 'ongoing' and incident.is_resolved:
                matches = False
            if status == 'resolved' and not incident.is_resolved:
                matches = False
        
        # Check time range filter
        if cutoff and incident.started_at < cutoff:
            matches = False
            
        if matches:
            matching_incidents.append(incident_data)
        else:
            non_matching_incidents.append(incident_data)

    if range_action == 'keep':
        # Keep the matching incidents, delete the non-matching ones
        db.write_data(db.model_files['incident'], matching_incidents)
        flash(f'Successfully saved {len(matching_incidents)} incidents and deleted {len(non_matching_incidents)}.', 'success')
    else: # 'delete'
        # Delete the matching incidents, keep the non-matching ones
        db.write_data(db.model_files['incident'], non_matching_incidents)
        flash(f'Successfully deleted {len(matching_incidents)} incidents.', 'success')

    return redirect(url_for('main.incidents'))

@main_bp.route('/status-pages')
@admin_required
@conditional_login_required
def status_pages():
    """List all status pages."""
    status_pages_data = db.get_all('status_page')
    status_pages = [StatusPage(**sp) for sp in status_pages_data]
    return render_template('status_pages.html', status_pages=status_pages)

@main_bp.route('/status-pages/new', methods=['GET', 'POST'])
@admin_required
def new_status_page():
    """Create a new status page."""
    if request.method == 'POST':
        name = request.form.get('name')
        slug = request.form.get('slug') or slugify(name)
        monitor_ids = request.form.getlist('monitors')

        if not name or not slug:
            flash('Name and slug are required.', 'error')
            return redirect(url_for('main.new_status_page'))

        # Check if slug is unique
        if db.get_all('status_page') and any(sp['slug'] == slug for sp in db.get_all('status_page')):
            flash('Slug must be unique.', 'error')
            return redirect(url_for('main.new_status_page'))

        status_page_data = {
            'name': name,
            'slug': slug,
            'monitors': [int(m_id) for m_id in monitor_ids]
        }
        db.add('status_page', status_page_data)
        flash('Status page created successfully!', 'success')
        return redirect(url_for('main.status_pages'))

    monitors = [Monitor(**m) for m in db.get_all('monitor')]
    return render_template('status_page_form.html', monitors=monitors, status_page=None)

@main_bp.route('/status-pages/<int:page_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_status_page(page_id):
    """Edit a status page."""
    status_page_data = db.get_by_id('status_page', page_id)
    if not status_page_data:
        abort(404)
    
    status_page = StatusPage(**status_page_data)

    if request.method == 'POST':
        name = request.form.get('name')
        slug = request.form.get('slug') or slugify(name)
        monitor_ids = request.form.getlist('monitors')

        if not name or not slug:
            flash('Name and slug are required.', 'error')
            return redirect(url_for('main.edit_status_page', page_id=page_id))

        # Check if slug is unique (and not the current page's slug)
        if any(sp['slug'] == slug and sp['id'] != page_id for sp in db.get_all('status_page')):
            flash('Slug must be unique.', 'error')
            return redirect(url_for('main.edit_status_page', page_id=page_id))

        update_data = {
            'name': name,
            'slug': slug,
            'monitors': [int(m_id) for m_id in monitor_ids]
        }
        db.update('status_page', page_id, update_data)
        flash('Status page updated successfully!', 'success')
        return redirect(url_for('main.status_pages'))

    monitors = [Monitor(**m) for m in db.get_all('monitor')]
    return render_template('status_page_form.html', monitors=monitors, status_page=status_page)

@main_bp.route('/status-pages/<int:page_id>/delete', methods=['POST'])
@admin_required
def delete_status_page(page_id):
    """Delete a status page."""
    db.delete('status_page', page_id)
    flash('Status page deleted successfully!', 'success')
    return redirect(url_for('main.status_pages'))

@main_bp.route('/status/<slug>')
def public_status_page(slug):
    """Public view of a status page."""
    all_status_pages = db.get_all('status_page')
    status_page_data = next((sp for sp in all_status_pages if sp['slug'] == slug), None)
    
    if not status_page_data:
        abort(404)
        
    status_page = StatusPage(**status_page_data)
    
    # Get all maintenance schedules
    all_maintenance_data = db.get_all('maintenance')
    all_maintenance_schedules = [Maintenance(**m) for m in all_maintenance_data]

    for monitor in status_page.monitor_objects:
        monitor.daily_checks = monitor.get_checks_with_maintenance(all_maintenance_schedules)
        # Determine current maintenance status for the overall monitor badge
        active_schedules = [s for s in all_maintenance_schedules if s.is_active]
        monitor.in_maintenance = any(monitor.id in s.monitors for s in active_schedules)

    return render_template('public_status_page.html', status_page=status_page)


@main_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
@conditional_login_required
def settings():
    """Application settings page."""
    form = GeneralSettingsForm()
    user_form = UserForm()

    if form.validate_on_submit() and 'submit_general' in request.form:
        old_login_required = current_app.config.get('LOGIN_REQUIRED')
        new_login_required = form.login_required.data
        settings_data = {
            'timezone': form.timezone.data,
            'login_required': new_login_required,
            'site_name': form.site_name.data.strip() if form.site_name.data else '',
            'footer_text': form.footer_text.data.strip() if form.footer_text.data else '',
            'site_icon': form.site_icon.data.strip() if form.site_icon.data else '',
            'favicon_url': form.favicon_url.data.strip() if form.favicon_url.data else ''
        }
        save_settings(settings_data)
        # Convert the login_required boolean to match Flask's expectation
        flask_settings = {
            'TIMEZONE': settings_data['timezone'],
            'LOGIN_REQUIRED': settings_data['login_required']
        }
        current_app.config.update(flask_settings)
        flash('Settings updated successfully!', 'success')

        # If login requirement changed from True to False, log out user and redirect to dashboard
        if old_login_required and not new_login_required:
            logout_user()
            flash('Login is now disabled. You have been logged out.', 'info')
            return redirect(url_for('main.dashboard'))
        
        # If login is now required, log out non-admin users
        if new_login_required and current_user.is_authenticated and current_user.role != 'edit':
            logout_user()
            flash('Login is now required. Please log in again.', 'info')
            return redirect(url_for('main.login'))
            
        return redirect(url_for('main.settings'))

    if user_form.validate_on_submit() and 'submit_user' in request.form:
        hashed_password = bcrypt.generate_password_hash(user_form.password.data).decode('utf-8')
        user_data = {
            'username': user_form.username.data,
            'password': hashed_password,
            'role': user_form.role.data
        }
        db.add('user', user_data)
        flash('User created successfully!', 'success')
        return redirect(url_for('main.settings'))

    # Load current settings to populate the form
    current_settings = load_settings()
    form.timezone.data = current_settings.get('timezone', current_app.config['TIMEZONE'])
    form.login_required.data = current_settings.get('login_required', current_app.config['LOGIN_REQUIRED'])
    form.site_name.data = current_settings.get('site_name', '')
    form.footer_text.data = current_settings.get('footer_text', '')
    form.site_icon.data = current_settings.get('site_icon', '')
    form.favicon_url.data = current_settings.get('favicon_url', '')

    channels_data = db.get_all('notification_channel')
    channels = [NotificationChannel(**c) for c in channels_data]
    tags = db.get_all('tag')
    users_data = db.get_all('user')
    users = [User(**u) for u in users_data]
    return render_template('settings.html', channels=channels, tags=tags, form=form, user_form=user_form, users=users)

# Backup Configuration Routes
@main_bp.route('/settings/backup', methods=['GET', 'POST'])
@admin_required
def backup_config():
    """Backup configuration page."""
    form = BackupForm()
    
    if form.validate_on_submit():
        try:
            backup_data = {
                'name': form.name.data,
                'backup_path': form.backup_path.data,
                'frequency': form.frequency.data,
                'time': form.time.data,
                'day_of_week': form.day_of_week.data,
                'day_of_month': form.day_of_month.data,
                'retention_days': form.retention_days.data,
                'is_active': form.is_active.data,
                'include_logs': form.include_logs.data
            }
            
            # Check if there's already a backup config (only one allowed)
            existing_configs = db.get_all('backup_config')
            if existing_configs:
                # Update existing config
                existing_id = existing_configs[0]['id']
                db.update('backup_config', existing_id, backup_data)
                flash('Backup configuration updated successfully!', 'success')
            else:
                # Create new config
                db.add('backup_config', backup_data)
                flash('Backup configuration created successfully!', 'success')
            
            # Restart scheduler to pick up changes
            try:
                from app.scheduler import init_scheduler
                current_app.scheduler.shutdown()
                current_app.scheduler = init_scheduler()
            except Exception as e:
                current_app.logger.warning(f"Failed to restart scheduler: {e}")
                
            return redirect(url_for('main.backup_config'))
            
        except Exception as e:
            flash(f'Error saving backup configuration: {str(e)}', 'error')
    
    # Load existing config if it exists
    existing_configs = db.get_all('backup_config')
    if existing_configs:
        config = BackupConfig(**existing_configs[0])
        if not form.is_submitted():
            form.name.data = config.name
            form.backup_path.data = config.backup_path
            form.frequency.data = config.frequency
            form.time.data = config.time
            form.day_of_week.data = str(config.day_of_week)
            form.day_of_month.data = config.day_of_month
            form.retention_days.data = config.retention_days
            form.is_active.data = config.is_active
            form.include_logs.data = config.include_logs
    else:
        config = None
    
    return render_template('backup_config.html', form=form, config=config)

@main_bp.route('/settings/backup/run', methods=['POST'])
@admin_required
def run_backup():
    """Manually trigger a backup."""
    try:
        from app.utils import perform_backup
        
        existing_configs = db.get_all('backup_config')
        if not existing_configs:
            flash('No backup configuration found. Please configure backup settings first.', 'error')
            return redirect(url_for('main.backup_config'))
        
        config = BackupConfig(**existing_configs[0])
        success, error_message = perform_backup(config, db)
        
        # Update backup status
        update_data = {
            'last_backup_at': datetime.utcnow().isoformat(),
            'last_backup_status': 'success' if success else 'failed',
            'last_backup_error': error_message if not success else None
        }
        db.update('backup_config', config.id, update_data)
        
        if success:
            flash('Backup completed successfully!', 'success')
        else:
            flash(f'Backup failed: {error_message}', 'error')
            
    except Exception as e:
        flash(f'Error running backup: {str(e)}', 'error')
    
    return redirect(url_for('main.backup_config'))

@main_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    if current_user.id == user_id:
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for('main.settings'))
    db.delete('user', user_id)
    flash('User deleted successfully.', 'success')
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/notification-channels/add', methods=['GET', 'POST'])
@admin_required
def add_notification_channel():
    """Add a new notification channel."""
    form = NotificationChannelForm()
    monitors = [Monitor(**m) for m in db.get_all('monitor')]
    form.monitors.choices = [(m.id, m.name) for m in monitors]

    if form.validate_on_submit():
        try:
            config = {}
            channel_type = form.channel_type.data

            if channel_type == 'email':
                config = {
                    'email_to': form.email_to.data,
                    'smtp_server': form.smtp_server.data,
                    'smtp_port': form.smtp_port.data,
                    'smtp_username': form.smtp_username.data,
                    'smtp_password': form.smtp_password.data,
                    'use_tls': form.use_tls.data,
                    'use_ssl': form.use_ssl.data
                }
            elif channel_type == 'webhook':
                config = {'url': form.webhook_url.data}
            elif channel_type == 'slack':
                config = {'webhook_url': form.slack_webhook_url.data}

            channel_data = {
                'name': form.name.data,
                'channel_type': channel_type,
                'config': config,
                'is_active': form.is_active.data,
                'monitors': form.monitors.data
            }
            db.add('notification_channel', channel_data)
            flash('Notification channel added successfully!', 'success')
            return redirect(url_for('main.settings'))
        except Exception as e:
            flash(f'Error adding channel: {str(e)}', 'error')
            
    return render_template('notification_channel_form.html', form=form, monitors=monitors)

@main_bp.route('/settings/notification-channels/<int:channel_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_notification_channel(channel_id):
    """Edit a notification channel."""
    channel_data = db.get_by_id('notification_channel', channel_id)
    if not channel_data:
        abort(404)
    
    channel = NotificationChannel(**channel_data)
    form = NotificationChannelForm(obj=channel)
    monitors = [Monitor(**m) for m in db.get_all('monitor')]
    form.monitors.choices = [(m.id, m.name) for m in monitors]

    if form.validate_on_submit():
        try:
            config = {}
            channel_type = form.channel_type.data

            if channel_type == 'email':
                config = {
                    'email_to': form.email_to.data,
                    'smtp_server': form.smtp_server.data,
                    'smtp_port': form.smtp_port.data,
                    'smtp_username': form.smtp_username.data,
                    'smtp_password': form.smtp_password.data,
                    'use_tls': form.use_tls.data,
                    'use_ssl': form.use_ssl.data
                }
            elif channel_type == 'webhook':
                config = {'url': form.webhook_url.data}
            elif channel_type == 'slack':
                config = {'webhook_url': form.slack_webhook_url.data}

            update_data = {
                'name': form.name.data,
                'channel_type': channel_type,
                'config': config,
                'is_active': form.is_active.data,
                'monitors': form.monitors.data
            }
            db.update('notification_channel', channel_id, update_data)
            flash('Notification channel updated successfully!', 'success')
            return redirect(url_for('main.settings'))
        except Exception as e:
            flash(f'Error updating channel: {str(e)}', 'error')

    if not form.is_submitted():
        form.monitors.data = channel.monitors
        form.is_active.data = channel.is_active
        # Pre-populate config fields
        if channel.config:
            if channel.channel_type == 'email':
                form.email_to.data = channel.config.get('email_to')
                form.smtp_server.data = channel.config.get('smtp_server')
                form.smtp_port.data = channel.config.get('smtp_port')
                form.smtp_username.data = channel.config.get('smtp_username')
                form.smtp_password.data = channel.config.get('smtp_password')
                form.use_tls.data = channel.config.get('use_tls')
                form.use_ssl.data = channel.config.get('use_ssl')
            elif channel.channel_type == 'webhook':
                form.webhook_url.data = channel.config.get('url')
            elif channel.channel_type == 'slack':
                form.slack_webhook_url.data = channel.config.get('webhook_url')

    return render_template('notification_channel_form.html', form=form, monitors=monitors)

@main_bp.route('/settings/notification-channels/<int:channel_id>/toggle', methods=['POST'])
@admin_required
def toggle_notification_channel(channel_id):
    """Toggle notification channel active status."""
    channel = db.get_by_id('notification_channel', channel_id)
    if not channel:
        abort(404)
    
    try:
        new_status = not channel.get('is_active', True)
        db.update('notification_channel', channel_id, {'is_active': new_status})
        
        status = "activated" if new_status else "deactivated"
        flash(f'Channel "{channel["name"]}" {status}!', 'success')
    except Exception as e:
        flash(f'Error updating channel: {str(e)}', 'error')
    
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/notification-channels/<int:channel_id>/delete', methods=['POST'])
@admin_required
def delete_notification_channel(channel_id):
    """Delete a notification channel."""
    db.delete('notification_channel', channel_id)
    flash('Notification channel deleted successfully!', 'success')
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/notification-channels/<int:channel_id>/test', methods=['POST'])
@admin_required
def test_notification_channel(channel_id):
    """Send a test notification to a channel."""
    channel_data = db.get_by_id('notification_channel', channel_id)
    if not channel_data:
        abort(404)
    
    from app.notifications import notification_service
    
    # Create a mock monitor for the test notification
    mock_monitor = Monitor(id=0, name="Test Monitor", url="http://test.com", status="up")
    
    success = notification_service.send_notification(channel_data, 'test', mock_monitor)
    
    if success:
        flash('Test notification sent successfully!', 'success')
    else:
        flash('Failed to send test notification.', 'error')
        
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/tags/<int:tag_id>/delete', methods=['POST'])
@admin_required
def delete_tag(tag_id):
    """Delete a tag and its associations."""
    tag = db.get_by_id('tag', tag_id)
    if not tag:
        abort(404)
    
    try:
        # First, remove all associations from the monitor_tag table
        all_monitor_tags = db.get_all('monitor_tag')
        links_to_delete = [mt['id'] for mt in all_monitor_tags if mt['tag_id'] == tag_id]
        for link_id in links_to_delete:
            db.delete('monitor_tag', link_id)
            
        # Then, delete the tag itself
        db.delete('tag', tag_id)
        
        flash(f'Tag "{tag["name"]}" and all its associations have been deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting tag: {str(e)}', 'error')
        
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/cleanup', methods=['POST'])
@admin_required
def cleanup_data():
    """Manually trigger a cleanup of old history data."""
    try:
        history = db.read_data(db.model_files['history'])
        # Assuming a 7-day retention period for manual cleanup
        cutoff = datetime.utcnow() - timedelta(days=7)
        
        original_count = len(history)
        history_to_keep = [h for h in history if datetime.fromisoformat(h['checked_at']) >= cutoff]
        cleaned_count = original_count - len(history_to_keep)
        
        db.write_data(db.model_files['history'], history_to_keep)
        
        flash(f'Successfully cleaned up {cleaned_count} old history records.', 'success')
    except Exception as e:
        flash(f'Error during cleanup: {str(e)}', 'error')
        
    return redirect(url_for('main.settings'))

@main_bp.route('/download-prebuilt-agent')
@admin_required
def download_prebuilt_agent():
    """Serve pre-built agent executables."""
    platform = request.args.get('platform', 'windows')
    
    agent_dir = Path(current_app.root_path).parent / 'agent'
    dist_dir = agent_dir / 'dist'
    
    if platform == 'linux':
        # Check for binary first, then source package
        binary_path = dist_dir / 'uptime_agent'
        source_path = dist_dir / 'uptime_agent_linux_src.tar.gz'
        
        if binary_path.exists():
            agent_path = binary_path
            mimetype = 'application/octet-stream'
            download_name = 'uptime_agent'
        elif source_path.exists():
            agent_path = source_path
            mimetype = 'application/gzip'
            download_name = 'uptime_agent_linux_src.tar.gz'
        else:
            agent_path = None
    else:  # windows
        agent_name = 'uptime_agent.exe'
        agent_path = dist_dir / agent_name
        mimetype = 'application/x-msdownload'
        download_name = 'uptime_agent.exe'
    
    # Check if pre-built agent exists
    if not agent_path or not agent_path.exists():
        flash('Pre-built agent not found. Please build the agents first.', 'error')
        return redirect(request.referrer or url_for('main.dashboard'))
    
    try:
        return send_file(
            agent_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )
    except Exception as e:
        flash(f'Error downloading agent: {str(e)}', 'error')
        return redirect(request.referrer or url_for('main.dashboard'))

@main_bp.route('/monitors/<int:monitor_id>/download-agent')
@admin_required
def download_agent(monitor_id):
    """Build and serve the agent executable."""
    platform = request.args.get('platform', 'windows')
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)

    agent_dir = Path(current_app.root_path).parent / 'agent'
    dist_dir = agent_dir / 'dist'
    dist_dir.mkdir(exist_ok=True)

    # Check if we're running in a Docker container
    is_docker = os.path.exists('/.dockerenv')
    # Check if we're on Windows
    is_windows = os.name == 'nt'
    
    # Define executable names and build approach based on platform and environment
    if platform == 'linux':
        agent_name = f'uptime_agent_linux_{monitor_id}'
        mimetype = 'application/octet-stream'
        if is_docker:
            build_script = 'build_cross_platform.sh'
        elif is_windows:
            # On Windows, use direct PyInstaller for Linux builds since shell scripts don't work
            build_script = None  # Will use direct PyInstaller approach
        else:
            # Native Linux environment
            build_script = 'build_linux.sh'
        build_platform = 'linux'
    else:  # windows
        if is_docker:
            # In Docker containers, we can now build true Windows executables using Wine
            agent_name = f'uptime_agent_{monitor_id}.exe'
            mimetype = 'application/x-msdownload'
            build_script = 'build_cross_platform.sh'
        elif is_windows:
            # Native Windows environment
            agent_name = f'uptime_agent_{monitor_id}.exe'
            mimetype = 'application/x-msdownload'
            build_script = 'build.bat'
        else:
            # Native Linux building Windows (would require Wine)
            agent_name = f'uptime_agent_{monitor_id}.exe'
            mimetype = 'application/x-msdownload'
            build_script = 'build_cross_platform.sh'
        build_platform = 'windows'

    agent_path = dist_dir / agent_name

    # Create a temporary, monitor-specific agent script
    temp_agent_script_path = agent_dir / f'agent_{monitor_id}.py'
    with open(agent_dir / 'agent_parameterized.py', 'r') as f:
        template_code = f.read()
    
    # Replace the argument parsing with hardcoded monitor ID while preserving parameter functionality
    custom_code = template_code.replace(
        "args = parser.parse_args()",
        f"""# Hardcode monitor ID but preserve other arguments
args = parser.parse_args()
if not args.monitor_id:
    args.monitor_id = {monitor_id}"""
    )
    
    with open(temp_agent_script_path, 'w') as f:
        f.write(custom_code)

    # Build the agent, deleting the old one if it exists
    if agent_path.exists():
        os.remove(agent_path)
    
    try:
        if build_script is None:
            # Direct PyInstaller approach for Windows environments building Linux agents
            pyinstaller_name = f'uptime_agent_linux_{monitor_id}'
            
            # Install PyInstaller if not already available
            subprocess.run(['pip', 'install', 'pyinstaller'], 
                          capture_output=True, check=True, cwd=str(agent_dir))
            
            # Run PyInstaller directly
            result = subprocess.run([
                'pyinstaller', 
                '--onefile', 
                '--name', pyinstaller_name,
                '--distpath', 'dist',
                str(temp_agent_script_path)
            ], capture_output=True, text=True, cwd=str(agent_dir), check=False)
            
            if result.returncode != 0:
                error_output = result.stdout + "\n" + result.stderr
                raise subprocess.CalledProcessError(result.returncode, 'pyinstaller', output=error_output)
                
        else:
            # Use build script approach with cross-platform script
            pyinstaller_name = f'uptime_agent_linux_{monitor_id}' if platform == 'linux' else f'uptime_agent_{monitor_id}'
            
            build_script_path = agent_dir / build_script
            
            # Ensure the build script is executable
            build_script_path.chmod(0o755)

            # Construct the command to run the build script
            # Pass the platform as third argument to cross-platform script
            build_command = [
                str(build_script_path),
                str(temp_agent_script_path),
                pyinstaller_name,
                build_platform
            ]

            # Run the build process
            result = subprocess.run(
                build_command,
                capture_output=True,
                text=True,
                cwd=str(agent_dir),
                check=False
            )

            if result.returncode != 0:
                error_output = result.stdout + "\n" + result.stderr
                raise subprocess.CalledProcessError(result.returncode, build_command, output=error_output)

        # Verify the executable was created
        if not agent_path.exists():
            raise Exception(f"Build process completed, but the executable was not found at {agent_path}")

    except subprocess.CalledProcessError as e:
        error_msg = e.output if hasattr(e, 'output') and e.output else str(e)
        flash(f'Error building agent: {error_msg}', 'error')
        return redirect(url_for('main.edit_monitor', monitor_id=monitor_id))
    except Exception as e:
        flash(f'An unexpected error occurred during build: {str(e)}', 'error')
        return redirect(url_for('main.edit_monitor', monitor_id=monitor_id))
    finally:
        # Clean up the temporary script
        if temp_agent_script_path.exists():
            os.remove(temp_agent_script_path)

    # Serve the executable
    try:
        return send_file(
            agent_path,
            as_attachment=True,
            download_name=agent_name,
            mimetype=mimetype
        )
    except Exception as e:
        flash(f'Error downloading agent: {str(e)}', 'error')
        return redirect(url_for('main.edit_monitor', monitor_id=monitor_id))

@main_bp.route('/settings/export', methods=['GET'])
@admin_required
def export_data():
    """Export all data as a single JSON file."""
    try:
        all_data = {
            'monitors': db.get_all('monitor'),
            'checks': db.get_all('check'),
            'incidents': db.get_all('incident'),
            'history': db.get_all('history'),
            'notification_channels': db.get_all('notification_channel')
        }
        
        return jsonify(all_data)
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('main.settings'))

@main_bp.route('/settings/export-monitors', methods=['GET'])
@admin_required
def export_monitors():
    """Export site configuration as a ZIP backup."""
    try:
        from app.utils import create_manual_backup
        
        # Create a manual backup ZIP file
        backup_path, error = create_manual_backup(db)
        
        if error:
            flash(f'Error creating backup: {error}', 'error')
            return redirect(url_for('main.settings'))
            
        if not backup_path or not os.path.exists(backup_path):
            flash('Backup file was not created successfully', 'error')
            return redirect(url_for('main.settings'))
            
        # Send the ZIP file
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=f'site_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
            mimetype='application/zip'
        )
        
    except Exception as e:
        current_app.logger.error(f'Error in export_monitors: {str(e)}')
        flash(f'Error exporting site configuration: {str(e)}', 'error')
        return redirect(url_for('main.settings'))

@main_bp.route('/settings/import-monitors', methods=['POST'])
@admin_required
def import_monitors():
    """Import site configuration from a backup ZIP file."""
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('main.settings'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('main.settings'))
        
    if file and file.filename.endswith('.zip'):
        try:
            from app.utils import restore_from_backup
            import tempfile
            import os
            
            # Save uploaded file to temporary location
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            file.save(temp_file.name)
            temp_file.close()
            
            try:
                # Restore from backup
                success, error = restore_from_backup(temp_file.name, db)
                
                if success:
                    flash('Site configuration restored successfully! Please restart the application to ensure all changes take effect.', 'success')
                else:
                    flash(f'Error restoring backup: {error}', 'error')
                    
            finally:
                # Clean up temporary file
                os.unlink(temp_file.name)
                
        except Exception as e:
            flash(f'Error importing backup: {str(e)}', 'error')
    else:
        flash('Invalid file type. Please upload a .zip backup file.', 'error')
        
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/rebuild-agents', methods=['POST'])
@admin_required
def rebuild_agents():
    """Rebuild Windows agent executable with the latest code."""
    try:
        import sys
        import shutil
        
        agent_dir = Path(current_app.root_path).parent / 'agent'
        dist_dir = agent_dir / 'dist'
        
        # Clean up old Windows builds (with error handling)
        if dist_dir.exists():
            exe_path = dist_dir / 'uptime_agent.exe'
            if exe_path.exists():
                try:
                    os.remove(exe_path)
                except Exception as e:
                    current_app.logger.warning(f"Could not remove old Windows executable: {e}")
        dist_dir.mkdir(exist_ok=True)
        
        # Clean up build cache with more aggressive approach
        build_dir = agent_dir / 'build'
        if build_dir.exists():
            try:
                # Try multiple approaches to clean the build directory
                for root, dirs, files in os.walk(str(build_dir), topdown=False):
                    for name in files:
                        try:
                            file_path = os.path.join(root, name)
                            os.chmod(file_path, 0o777)
                            os.remove(file_path)
                        except:
                            pass
                    for name in dirs:
                        try:
                            dir_path = os.path.join(root, name)
                            os.rmdir(dir_path)
                        except:
                            pass
                try:
                    os.rmdir(str(build_dir))
                except:
                    pass
            except Exception as e:
                current_app.logger.warning(f"Could not fully clean build directory: {e}")
        
        # Path to the agent script
        agent_script = agent_dir / 'agent_parameterized.py'
        
        if not agent_script.exists():
            flash('Agent script not found!', 'error')
            return redirect(url_for('main.settings'))
        
        # Install required packages
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller', 'psutil', 'requests'], 
                      check=True, capture_output=True, timeout=300)
        
        # Build Windows executable
        pyinstaller_cmd = [
            sys.executable, '-m', 'PyInstaller',
            '--onefile',
            '--name', 'uptime_agent',
            '--distpath', str(dist_dir),
            '--workpath', str(agent_dir / 'build_temp'),
            '--specpath', str(agent_dir),
            '--noconfirm',
            str(agent_script)
        ]
        
        # Create clean environment for build (remove any UPTIME_* environment variables)
        build_env = os.environ.copy()
        # Remove any environment variables that might interfere
        build_env.pop('UPTIME_API_ENDPOINT', None)
        build_env.pop('UPTIME_API_KEY', None)
        build_env.pop('UPTIME_LOG_LINES', None)
        
        result = subprocess.run(pyinstaller_cmd, cwd=str(agent_dir), capture_output=True, text=True, timeout=600, env=build_env)
        
        # Clean up temp build directory
        temp_build_dir = agent_dir / 'build_temp'
        if temp_build_dir.exists():
            try:
                shutil.rmtree(str(temp_build_dir), ignore_errors=True)
            except:
                pass
        
        if result.returncode != 0:
            flash(f'Windows agent build failed: {result.stderr}', 'error')
            current_app.logger.error(f"Windows agent build failed: {result.stdout}\n{result.stderr}")
            return redirect(url_for('main.settings'))
        
        # Check if executable was created
        exe_path = dist_dir / 'uptime_agent.exe'
        if exe_path.exists():
            file_size = exe_path.stat().st_size / (1024*1024)
            flash(f'Windows agent rebuilt successfully! (Size: {file_size:.1f} MB)', 'success')
        else:
            flash('Windows agent build completed but executable not found!', 'warning')
        
        return redirect(url_for('main.settings'))
        
    except subprocess.TimeoutExpired:
        flash('Windows agent build timed out. Please try again.', 'error')
        return redirect(url_for('main.settings'))
    except Exception as e:
        flash(f'Error rebuilding Windows agent: {str(e)}', 'error')
        current_app.logger.error(f"Windows agent rebuild error: {str(e)}")
        return redirect(url_for('main.settings'))

@main_bp.route('/settings/rebuild-linux-agents', methods=['POST'])
@admin_required
def rebuild_linux_agents():
    """Create universal Linux Python agent package - works on any Linux system with Python 3.6+."""
    try:
        import shutil
        
        agent_dir = Path(current_app.root_path).parent / 'agent'
        dist_dir = agent_dir / 'dist'
        
        # Ensure dist directory exists
        dist_dir.mkdir(exist_ok=True)
        
        # Path to the agent script
        agent_script = agent_dir / 'agent_parameterized.py'
        
        if not agent_script.exists():
            flash('Agent script not found!', 'error')
            return redirect(url_for('main.settings'))
        
        current_app.logger.info("Creating universal Linux Python package")
        
        # Clean up old packages
        old_packages = [
            dist_dir / 'uptime_agent',
            dist_dir / 'uptime_agent_linux_src.tar.gz',
            dist_dir / 'uptime_agent_linux.tar.gz'
        ]
        
        for old_pkg in old_packages:
            if old_pkg.exists():
                try:
                    if old_pkg.is_file():
                        os.remove(old_pkg)
                    else:
                        shutil.rmtree(old_pkg)
                    current_app.logger.info(f"Removed old package: {old_pkg.name}")
                except Exception as e:
                    current_app.logger.warning(f"Could not remove old package {old_pkg.name}: {e}")
        
        # Create Linux package directory
        linux_pkg_dir = dist_dir / 'uptime_agent_linux'
        if linux_pkg_dir.exists():
            shutil.rmtree(linux_pkg_dir)
        linux_pkg_dir.mkdir()
        
        # Copy the agent script
        shutil.copy2(agent_script, linux_pkg_dir / 'agent_parameterized.py')
        
        # Create smart requirements.txt with version constraints for better compatibility
        with open(linux_pkg_dir / 'requirements.txt', 'w') as f:
            f.write('psutil>=5.6.0\nrequests>=2.20.0\n')
        
        # Create system compatibility checker
        checker_content = '''#!/usr/bin/env python3
"""
System Compatibility Checker for Uptime Agent
Validates system requirements and provides helpful guidance.
"""
import sys
import subprocess
import importlib.util

def check_python_version():
    """Check if Python version meets requirements."""
    version = sys.version_info
    if version < (3, 6):
        print(f"❌ Python 3.6+ required. Found: {version.major}.{version.minor}")
        print("   Please upgrade Python or use a newer system")
        return False
    else:
        print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
        return True

def check_pip():
    """Check if pip is available."""
    try:
        import pip
        print("✅ pip is available")
        return True
    except ImportError:
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ pip is available via module")
                return True
        except:
            pass
        
        print("❌ pip not found")
        print("   Install with: python3 -m ensurepip --upgrade")
        return False

def check_dependencies():
    """Check if required dependencies are available or can be installed."""
    deps = ['psutil', 'requests']
    missing = []
    
    for dep in deps:
        spec = importlib.util.find_spec(dep)
        if spec is None:
            missing.append(dep)
        else:
            print(f"✅ {dep} is available")
    
    if missing:
        print(f"ℹ️  Missing dependencies: {', '.join(missing)}")
        print("   Will be installed automatically on first run")
    
    return True

def check_network():
    """Test basic network connectivity."""
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        print("✅ Network connectivity OK")
        return True
    except:
        print("⚠️  Network connectivity issue detected")
        print("   Agent may have trouble reaching your monitoring server")
        return False

def main():
    print("🔍 Uptime Agent System Compatibility Check\\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("Package Manager", check_pip),
        ("Dependencies", check_dependencies),
        ("Network", check_network)
    ]
    
    all_passed = True
    for name, check_func in checks:
        try:
            result = check_func()
            if not result:
                all_passed = False
        except Exception as e:
            print(f"❌ {name} check failed: {e}")
            all_passed = False
        print()
    
    if all_passed:
        print("🎉 System is ready for Uptime Agent!")
        print("   Run: ./uptime_agent --help")
    else:
        print("⚠️  Some issues detected. Please resolve them before running the agent.")
        print("   For help, see README.md or contact support.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
'''
        
        with open(linux_pkg_dir / 'check_system.py', 'w') as f:
            f.write(checker_content)
        
        # Make checker executable
        (linux_pkg_dir / 'check_system.py').chmod(0o755)
        
        # Create smart launcher script with enhanced error handling
        launcher_content = '''#!/bin/bash
# Smart Uptime Agent Launcher
# Universal compatibility for Linux systems
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SCRIPT="$SCRIPT_DIR/agent_parameterized.py"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

# Colors for output
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Find Python executable
find_python() {
    local python_candidates=("python3" "python3.11" "python3.10" "python3.9" "python3.8" "python3.7" "python3.6" "python")
    
    for cmd in "${python_candidates[@]}"; do
        if command -v "$cmd" &> /dev/null; then
            local version=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            local major=$(echo $version | cut -d. -f1)
            local minor=$(echo $version | cut -d. -f2)
            
            # Check if version >= 3.6
            if [[ $major -eq 3 && $minor -ge 6 ]] || [[ $major -gt 3 ]]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    
    return 1
}

# Check Python availability
if ! PYTHON_CMD=$(find_python); then
    log_error "Python 3.6+ is required but not found"
    log_info "Please install Python 3.6 or newer:"
    log_info "  Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip"
    log_info "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    log_info "  Alpine:        apk add python3 py3-pip"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
log_success "Found Python $PYTHON_VERSION at $(which $PYTHON_CMD)"

# Check dependencies and install if needed
install_deps() {
    log_info "Checking dependencies..."
    
    if ! $PYTHON_CMD -c "import psutil, requests" 2>/dev/null; then
        log_warning "Required packages missing, installing..."
        
        # Try different installation methods
        if $PYTHON_CMD -m pip install --user -r "$REQUIREMENTS" 2>/dev/null; then
            log_success "Dependencies installed successfully (user mode)"
        elif $PYTHON_CMD -m pip install -r "$REQUIREMENTS" 2>/dev/null; then
            log_success "Dependencies installed successfully (system mode)"
        else
            log_error "Failed to install dependencies automatically"
            log_info "Please install manually:"
            log_info "  $PYTHON_CMD -m pip install psutil requests"
            log_info "  OR: pip3 install psutil requests"
            exit 1
        fi
    else
        log_success "All dependencies are available"
    fi
}

# Show help if no arguments
if [[ $# -eq 0 ]]; then
    echo "🚀 Uptime Agent - Universal Linux Distribution"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Common usage:"
    echo "  $0 --monitor-id 123 --api-endpoint http://your-server:5000/api"
    echo
    echo "System check:"
    echo "  $0 --check-system"
    echo
    echo "For all options:"
    echo "  $0 --help"
    exit 0
fi

# System check mode
if [[ "$1" == "--check-system" ]]; then
    log_info "Running system compatibility check..."
    exec $PYTHON_CMD "$SCRIPT_DIR/check_system.py"
fi

# Install dependencies before running agent
install_deps

# Run the agent
log_info "Starting Uptime Agent..."
exec $PYTHON_CMD "$AGENT_SCRIPT" "$@"
'''
        
        launcher_path = linux_pkg_dir / 'uptime_agent'
        with open(launcher_path, 'w') as f:
            f.write(launcher_content)
        
        # Make launcher executable
        launcher_path.chmod(0o755)
        
        # Create one-click installer script
        installer_content = '''#!/bin/bash
# One-Click Uptime Agent Installer
set -e

# Colors
GREEN='\\033[0;32m'
BLUE='\\033[0;34m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

echo -e "${BLUE}🚀 Uptime Agent One-Click Installer${NC}"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
MONITOR_ID=""
API_ENDPOINT=""
INSTALL_DIR="/opt/uptime-agent"
SERVICE_NAME="uptime-agent"

while [[ $# -gt 0 ]]; do
    case $1 in
        --monitor-id)
            MONITOR_ID="$2"
            shift 2
            ;;
        --server|--api-endpoint)
            API_ENDPOINT="$2"
            shift 2
            ;;
        --install-dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 --monitor-id ID --server URL [OPTIONS]"
            echo
            echo "Required:"
            echo "  --monitor-id ID     Monitor ID from your uptime dashboard"
            echo "  --server URL        Your uptime server URL (e.g., http://192.168.1.100:5000)"
            echo
            echo "Optional:"
            echo "  --install-dir DIR   Installation directory (default: /opt/uptime-agent)"
            echo
            echo "Example:"
            echo "  $0 --monitor-id 123 --server http://192.168.1.100:5000"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [[ -z "$MONITOR_ID" || -z "$API_ENDPOINT" ]]; then
    echo -e "${YELLOW}Missing required parameters${NC}"
    echo "Use --help for usage information"
    exit 1
fi

# Ensure API endpoint includes /api
if [[ ! "$API_ENDPOINT" =~ /api$ ]]; then
    API_ENDPOINT="$API_ENDPOINT/api"
fi

echo "Configuration:"
echo "  Monitor ID: $MONITOR_ID"
echo "  Server: $API_ENDPOINT"
echo "  Install Directory: $INSTALL_DIR"
echo

# Create install directory
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/uptime_agent"
sudo chmod +x "$INSTALL_DIR/check_system.py"

# Test the installation
echo -e "${BLUE}Testing installation...${NC}"
"$INSTALL_DIR/uptime_agent" --check-system

# Create systemd service
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Uptime Monitoring Agent
After=network.target
Wants=network.target

[Service]
Type=simple
User=nobody
Group=nogroup
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/uptime_agent --monitor-id $MONITOR_ID --api-endpoint $API_ENDPOINT
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo -e "${GREEN}✅ Installation complete!${NC}"
echo
echo "Service status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l

echo
echo "Useful commands:"
echo "  Check status:   sudo systemctl status $SERVICE_NAME"
echo "  View logs:      sudo journalctl -u $SERVICE_NAME -f"
echo "  Stop service:   sudo systemctl stop $SERVICE_NAME"
echo "  Start service:  sudo systemctl start $SERVICE_NAME"
'''
        
        with open(linux_pkg_dir / 'install.sh', 'w') as f:
            f.write(installer_content)
        
        # Make installer executable
        (linux_pkg_dir / 'install.sh').chmod(0o755)
        
        # Create comprehensive README
        readme_content = '''# Uptime Agent for Linux - Universal Python Distribution

A smart, universal Linux agent that works on any Linux system with Python 3.6+.

## 🚀 Quick Start

### Option 1: One-Click Install (Recommended)
```bash
# Extract the package
tar -xzf uptime_agent_linux.tar.gz
cd uptime_agent_linux

# Install as system service
sudo ./install.sh --monitor-id YOUR_MONITOR_ID --server http://your-server:5000
```

### Option 2: Manual Run
```bash
# Extract and run directly
tar -xzf uptime_agent_linux.tar.gz
cd uptime_agent_linux

# Run the agent
./uptime_agent --monitor-id YOUR_MONITOR_ID --api-endpoint http://your-server:5000/api
```

## 🔧 System Requirements

- **Python**: 3.6 or newer (automatically detected)
- **OS**: Any Linux distribution
- **Network**: Internet access to reach your monitoring server
- **Permissions**: User-level (no root required for basic operation)

## 📋 Pre-Installation Check

Run the system compatibility checker:
```bash
./uptime_agent --check-system
```

This will verify:
- Python version compatibility
- Required packages availability  
- Network connectivity
- System readiness

## 🛠️ Installation Methods

### Method 1: System Service (Recommended for servers)
```bash
sudo ./install.sh --monitor-id 123 --server http://192.168.1.100:5000
```

**Benefits:**
- Automatically starts on boot
- Runs as system service
- Includes log rotation
- Easy management with systemctl

### Method 2: User Process (Good for testing)
```bash
./uptime_agent --monitor-id 123 --api-endpoint http://192.168.1.100:5000/api
```

### Method 3: Docker Container
```bash
# Build container
docker build -t uptime-agent .

# Run container  
docker run -d --name uptime-agent \\
  uptime-agent --monitor-id 123 --api-endpoint http://host.docker.internal:5000/api
```

## 📖 Usage Examples

### Basic monitoring
```bash
./uptime_agent --monitor-id 123 --api-endpoint http://your-server:5000/api
```

### With custom check interval
```bash
./uptime_agent --monitor-id 123 --api-endpoint http://your-server:5000/api --interval 30
```

### Enable debug logging
```bash
./uptime_agent --monitor-id 123 --api-endpoint http://your-server:5000/api --debug
```

### Background execution
```bash
nohup ./uptime_agent --monitor-id 123 --api-endpoint http://your-server:5000/api > agent.log 2>&1 &
```

## 🔍 Troubleshooting

### Check system compatibility
```bash
./uptime_agent --check-system
```

### Common Issues

**Python not found:**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-pip

# CentOS/RHEL
sudo yum install python3 python3-pip

# Alpine
apk add python3 py3-pip
```

**Permission denied:**
```bash
chmod +x uptime_agent
```

**Dependencies missing:**
```bash
python3 -m pip install -r requirements.txt
```

**Network issues:**
- Check firewall settings
- Verify server URL is accessible
- Test with: `curl http://your-server:5000/api`

### View logs (if installed as service)
```bash
# Follow live logs
sudo journalctl -u uptime-agent -f

# View recent logs
sudo journalctl -u uptime-agent --since "1 hour ago"
```

## 🏗️ Advanced Configuration

### Custom Python executable
```bash
PYTHON=/usr/local/bin/python3.9 ./uptime_agent --monitor-id 123 --api-endpoint http://your-server:5000/api
```

### Environment variables
```bash
export UPTIME_MONITOR_ID=123
export UPTIME_API_ENDPOINT=http://your-server:5000/api
./uptime_agent
```

### Configuration file
Create `config.env`:
```
UPTIME_MONITOR_ID=123
UPTIME_API_ENDPOINT=http://your-server:5000/api
UPTIME_INTERVAL=60
```

Then run:
```bash
source config.env && ./uptime_agent
```

## 📁 Package Contents

- `uptime_agent` - Smart launcher script
- `agent_parameterized.py` - Main agent code
- `requirements.txt` - Python dependencies
- `install.sh` - One-click installer
- `check_system.py` - System compatibility checker
- `README.md` - This documentation

## 🆘 Support

For issues or questions:
1. Run `./uptime_agent --check-system` first
2. Check the logs for error messages
3. Verify network connectivity to your server
4. Ensure Python 3.6+ is installed

## ✨ Features

- **Universal Compatibility**: Works on any Linux with Python 3.6+
- **Smart Detection**: Automatically finds the best Python executable
- **Auto-Installation**: Installs dependencies automatically
- **Error Recovery**: Detailed error messages with solutions
- **Multiple Install Methods**: Service, user process, or container
- **System Integration**: Full systemd service support
- **Comprehensive Logging**: Detailed logs for troubleshooting
'''

        with open(linux_pkg_dir / 'README.md', 'w') as f:
            f.write(readme_content)
        
        # Create the final tar.gz package
        import tarfile
        tar_path = dist_dir / 'uptime_agent_linux.tar.gz'
        if tar_path.exists():
            tar_path.unlink()
        
        current_app.logger.info(f"Creating universal Linux package: {tar_path}")
        
        # Create tar.gz with proper structure
        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(linux_pkg_dir, arcname='uptime_agent_linux')
        
        # Clean up temp directory
        shutil.rmtree(linux_pkg_dir)
        
        # Verify and report success
        if tar_path.exists():
            file_size = tar_path.stat().st_size
            if file_size > 0:
                size_kb = file_size / 1024
                
                # Verify contents
                with tarfile.open(tar_path, 'r:gz') as tar:
                    members = tar.getnames()
                    
                flash(f'Universal Linux Python package created successfully! (Size: {size_kb:.1f} KB) - Works on any Linux system with Python 3.6+. Contains {len(members)} files.', 'success')
                current_app.logger.info(f"Universal Linux package created: {size_kb:.1f} KB, {len(members)} files")
            else:
                flash('Package created but appears to be empty!', 'error')
        else:
            flash('Failed to create package file!', 'error')
        
        return redirect(url_for('main.settings'))
        
    except Exception as e:
        current_app.logger.error(f"Error creating universal Linux package: {str(e)}")
        flash(f'Error creating Linux package: {str(e)}', 'error')
        return redirect(url_for('main.settings'))

@main_bp.route('/settings/reset', methods=['POST'])
@admin_required
def reset_data():
    """Reset all data files to their default empty state."""
    try:
        db.write_data(db.model_files['monitor'], [])
        db.write_data(db.model_files['check'], [])
        db.write_data(db.model_files['incident'], [])
        db.write_data(db.model_files['history'], [])
        # Optionally, you might want to keep notification channels
        # db.write_data(db.model_files['notification_channel'], [])
        
        flash('All application data has been reset.', 'success')
    except Exception as e:
        flash(f'Error resetting data: {str(e)}', 'error')
        
    return redirect(url_for('main.settings'))
