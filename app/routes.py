from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, current_app, send_file
from app.database import db
from app.models import Monitor, MonitorCheck, Incident, NotificationChannel, Maintenance, StatusPage
from datetime import datetime, timedelta
import json
import re
from slugify import slugify
import pytz
import os
import subprocess
from pathlib import Path

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def dashboard():
    """Main dashboard showing all monitors."""
    all_monitors_data = db.get_all('monitor')
    monitors = [Monitor(**m) for m in all_monitors_data if m.get('is_active', True)]
    
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
    recent_incidents = sorted([Incident(**i) for i in all_incidents_data], key=lambda i: i.started_at, reverse=True)[:5]
    
    return render_template('dashboard.html',
                         monitors=monitors,
                         total_monitors=total_monitors,
                         up_monitors=up_monitors,
                         down_monitors=down_monitors,
                         recent_incidents=recent_incidents)

@main_bp.route('/monitors')
def monitors():
    """List all monitors."""
    # Simple pagination logic
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    all_monitors_data = db.get_all('monitor')
    all_monitors = [Monitor(**m) for m in all_monitors_data]
    
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
    
    return render_template('monitors.html', monitors=pagination)

@main_bp.route('/monitors/new', methods=['GET', 'POST'])
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
                'verify_ssl': request.form.get('verify_ssl') == 'on',
                'check_cert_expiry': request.form.get('check_cert_expiry') == 'on',
                'admin_notes': request.form.get('admin_notes', '').strip() or None,
                'server_client': request.form.get('server_client') == 'on',
                'is_active': True
            }
            
            new_monitor = db.add('monitor', monitor_data)
            flash(f'Monitor "{new_monitor["name"]}" created successfully!', 'success')
            return redirect(url_for('main.dashboard'))
            
        except Exception as e:
            flash(f'Error creating monitor: {str(e)}', 'error')
            # Pass an empty monitor object to the template on error
            return render_template('monitor_form.html', monitor=Monitor())
    
    # For GET request, pass an empty monitor object
    return render_template('monitor_form.html', monitor=Monitor())

@main_bp.route('/monitors/<int:monitor_id>')
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
    since = datetime.utcnow() - timedelta(hours=hours)
    
    all_checks_data = db.get_all('check')
    monitor_checks = [
        MonitorCheck(**c) for c in all_checks_data 
        if c['monitor_id'] == monitor_id and c.get('checked_at') and datetime.fromisoformat(c['checked_at']) >= since
    ]
    checks = sorted(monitor_checks, key=lambda c: c.checked_at, reverse=True)

    # Prepare data for the chart from history
    all_history_data = db.get_all('history')
    monitor_history = [
        h for h in all_history_data
        if h.get('monitor_id') == monitor_id and h.get('checked_at') and datetime.fromisoformat(h['checked_at']) >= since
    ]
    chart_checks_data = sorted(monitor_history, key=lambda c: c['checked_at'])
    
    # Get incidents for this monitor
    all_incidents_data = db.get_all('incident')
    monitor_incidents = [Incident(**i) for i in all_incidents_data if i['monitor_id'] == monitor_id]
    incidents = sorted(monitor_incidents, key=lambda i: i.started_at, reverse=True)[:10]
    
    # Get system metrics if this is a server monitor
    system_metrics_json = None
    if monitor.server_client:
        all_metrics = db.get_all('agent_metric')
        monitor_metrics = [
            m for m in all_metrics
            if m['monitor_id'] == monitor_id and 
               datetime.fromtimestamp(m['timestamp']) >= since
        ]
        system_metrics_json = json.dumps(sorted(monitor_metrics, key=lambda m: m['timestamp']))

    # Redirect to metrics page if this is a server client view request
    if monitor.server_client and request.args.get('view') == 'metrics':
        return redirect(url_for('main.monitor_metrics', monitor_id=monitor_id))

    return render_template('monitor_detail.html',
                         monitor=monitor,
                         checks=checks,
                         incidents=incidents,
                         hours=hours,
                         chart_checks_json=json.dumps(chart_checks_data),
                         system_metrics_json=system_metrics_json)

@main_bp.route('/monitors/<int:monitor_id>/metrics')
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
    since = datetime.utcnow() - timedelta(hours=hours)
    
    all_metrics = db.get_all('agent_metric')
    monitor_metrics = [
        m for m in all_metrics
        if m['monitor_id'] == monitor_id and 
           datetime.fromtimestamp(m['timestamp']) >= since
    ]
    metrics_data = sorted(monitor_metrics, key=lambda m: m['timestamp'])
    
    return render_template('monitor_metrics.html',
                         monitor=monitor,
                         hours=hours,
                         metrics_json=json.dumps(metrics_data))

@main_bp.route('/monitors/<int:monitor_id>/edit', methods=['GET', 'POST'])
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
                'verify_ssl': request.form.get('verify_ssl') == 'on',
                'check_cert_expiry': request.form.get('check_cert_expiry') == 'on',
                'admin_notes': request.form.get('admin_notes', '').strip() or None,
                'server_client': request.form.get('server_client') == 'on'
            }
            
            db.update('monitor', monitor_id, update_data)
            flash(f'Monitor "{update_data["name"]}" updated successfully!', 'success')
            return redirect(url_for('main.monitor_detail', monitor_id=monitor_id))
            
        except Exception as e:
            flash(f'Error updating monitor: {str(e)}', 'error')
    
    return render_template('monitor_form.html', monitor=monitor)

@main_bp.route('/monitors/<int:monitor_id>/delete', methods=['POST'])
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
        db.write_data(db.checks_file, checks_to_keep)

        all_incidents = db.get_all('incident')
        incidents_to_keep = [i for i in all_incidents if i['monitor_id'] != monitor_id]
        db.write_data(db.incidents_file, incidents_to_keep)

        flash(f'Monitor "{monitor["name"]}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting monitor: {str(e)}', 'error')
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/monitors/<int:monitor_id>/toggle', methods=['POST'])
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
def incidents():
    """List all incidents."""
    # Simple pagination logic
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    all_incidents_data = db.get_all('incident')
    all_incidents = sorted([Incident(**i) for i in all_incidents_data], key=lambda i: i.started_at, reverse=True)
    
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
@main_bp.route('/status-pages')
def status_pages():
    """List all status pages."""
    status_pages_data = db.get_all('status_page')
    status_pages = [StatusPage(**sp) for sp in status_pages_data]
    return render_template('status_pages.html', status_pages=status_pages)

@main_bp.route('/status-pages/new', methods=['GET', 'POST'])
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


@main_bp.route('/settings')
def settings():
    """Application settings page."""
    channels_data = db.get_all('notification_channel')
    channels = [NotificationChannel(**c) for c in channels_data]
    return render_template('settings.html', channels=channels)

@main_bp.route('/settings/cleanup', methods=['POST'])
def cleanup_data():
    """Manually trigger a cleanup of old history data."""
    try:
        history = db.read_data(db.history_file)
        # Assuming a 7-day retention period for manual cleanup
        cutoff = datetime.utcnow() - timedelta(days=7)
        
        original_count = len(history)
        history_to_keep = [h for h in history if datetime.fromisoformat(h['checked_at']) >= cutoff]
        cleaned_count = original_count - len(history_to_keep)
        
        db.write_data(db.history_file, history_to_keep)
        
        flash(f'Successfully cleaned up {cleaned_count} old history records.', 'success')
    except Exception as e:
        flash(f'Error during cleanup: {str(e)}', 'error')
        
    return redirect(url_for('main.settings'))

@main_bp.route('/monitors/<int:monitor_id>/download-agent')
def download_agent(monitor_id):
    """Build and serve the agent executable."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        abort(404)

    # Use absolute path from project root
    agent_dir = Path(current_app.root_path).parent / 'agent'
    monitor_agents_dir = agent_dir / 'monitor_agents'
    monitor_agents_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a custom agent script for this monitor
    custom_agent_script = monitor_agents_dir / f'agent_{monitor_id}.py'
    monitor_exe_path = monitor_agents_dir / f'uptime_agent_{monitor_id}.exe'
    
    # Load the template agent code
    with open(agent_dir / 'agent.py', 'r') as f:
        template_code = f.read()
    
    # Replace the API key with the monitor ID
    custom_code = template_code.replace(
        "API_KEY = os.environ.get('UPTIME_API_KEY', 'YOUR_DEFAULT_API_KEY')",
        f"API_KEY = '{monitor_id}'"
    )
    
    # Write the custom agent script
    with open(custom_agent_script, 'w') as f:
        f.write(custom_code)
        
    # Build the custom agent if it doesn't exist
    if not monitor_exe_path.exists():
        try:
            # Copy dependencies file
            if Path(agent_dir / 'requirements.txt').exists():
                import shutil
                shutil.copy2(agent_dir / 'requirements.txt', monitor_agents_dir)

            # Install dependencies
            subprocess.run(['pip', 'install', '-r', 'requirements.txt'], 
                         shell=True, check=True, cwd=str(monitor_agents_dir))
            subprocess.run(['pip', 'install', 'pyinstaller'], 
                         shell=True, check=True, cwd=str(monitor_agents_dir))

            # Create dist directory
            dist_dir = monitor_agents_dir / 'dist'
            dist_dir.mkdir(exist_ok=True)

            # Build the agent
            subprocess.run(['pyinstaller', '--onefile', '--distpath', str(dist_dir),
                          f'--name=uptime_agent_{monitor_id}', f'agent_{monitor_id}.py'], 
                         shell=True, check=True, cwd=str(monitor_agents_dir))

            # Update executable path to include dist directory
            monitor_exe_path = dist_dir / f'uptime_agent_{monitor_id}.exe'

            if not monitor_exe_path.exists():
                flash('Failed to build agent executable', 'error')
                return redirect(url_for('main.edit_monitor', monitor_id=monitor_id))
        except subprocess.CalledProcessError as e:
            flash(f'Error building agent: {str(e)}', 'error')
            return redirect(url_for('main.edit_monitor', monitor_id=monitor_id))

    # Serve the executable
    try:
        return send_file(
            monitor_exe_path,
            as_attachment=True,
            download_name=f'uptime_agent_{monitor_id}.exe',
            mimetype='application/x-msdownloader'
        )
    except Exception as e:
        flash(f'Error downloading agent: {str(e)}', 'error')
        return redirect(url_for('main.edit_monitor', monitor_id=monitor_id))

@main_bp.route('/settings/export', methods=['GET'])
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
def export_monitors():
    """Export just the monitor configurations."""
    try:
        monitors = db.get_all('monitor')
        return jsonify(monitors)
    except Exception as e:
        flash(f'Error exporting monitors: {str(e)}', 'error')
        return redirect(url_for('main.settings'))

@main_bp.route('/settings/import-monitors', methods=['POST'])
def import_monitors():
    """Import monitor configurations from a JSON file."""
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('main.settings'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('main.settings'))
        
    if file and file.filename.endswith('.json'):
        try:
            new_monitors = json.load(file)
            if not isinstance(new_monitors, list):
                flash('Invalid JSON format. Expected a list of monitor objects.', 'error')
                return redirect(url_for('main.settings'))
            
            # Overwrite existing monitors
            db.write_data(db.monitors_file, new_monitors)
            flash(f'Successfully imported {len(new_monitors)} monitors.', 'success')
        except Exception as e:
            flash(f'Error importing file: {str(e)}', 'error')
    else:
        flash('Invalid file type. Please upload a .json file.', 'error')
        
    return redirect(url_for('main.settings'))

@main_bp.route('/settings/reset', methods=['POST'])
def reset_data():
    """Reset all data files to their default empty state."""
    try:
        db.write_data(db.monitors_file, [])
        db.write_data(db.checks_file, [])
        db.write_data(db.incidents_file, [])
        db.write_data(db.history_file, [])
        # Optionally, you might want to keep notification channels
        # db.write_data(db.notification_channels_file, [])
        
        flash('All application data has been reset.', 'success')
    except Exception as e:
        flash(f'Error resetting data: {str(e)}', 'error')
        
    return redirect(url_for('main.settings'))
