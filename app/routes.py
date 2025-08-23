from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Monitor, MonitorCheck, Incident, NotificationChannel
from datetime import datetime, timedelta
import json

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def dashboard():
    """Main dashboard showing all monitors."""
    monitors = Monitor.query.filter_by(is_active=True).all()
    
    # Get summary statistics
    total_monitors = len(monitors)
    up_monitors = sum(1 for m in monitors if m.status == 'up')
    down_monitors = sum(1 for m in monitors if m.status == 'down')
    
    # Get recent incidents
    recent_incidents = Incident.query.order_by(Incident.started_at.desc()).limit(5).all()
    
    return render_template('dashboard.html',
                         monitors=monitors,
                         total_monitors=total_monitors,
                         up_monitors=up_monitors,
                         down_monitors=down_monitors,
                         recent_incidents=recent_incidents)

@main_bp.route('/monitors')
def monitors():
    """List all monitors."""
    page = request.args.get('page', 1, type=int)
    monitors = Monitor.query.paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('monitors.html', monitors=monitors)

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
                    return render_template('monitor_form.html')
            
            monitor = Monitor(
                name=request.form['name'],
                url=request.form['url'],
                monitor_type=request.form.get('monitor_type', 'http'),
                method=request.form.get('method', 'GET'),
                expected_status=int(request.form.get('expected_status', 200)),
                expected_text=request.form.get('expected_text', '').strip() or None,
                timeout=int(request.form.get('timeout', 30)),
                interval=int(request.form.get('interval', 60)),
                retries=int(request.form.get('retries', 3)),
                headers=headers or None,
                body=request.form.get('body', '').strip() or None
            )
            
            db.session.add(monitor)
            db.session.commit()
            flash(f'Monitor "{monitor.name}" created successfully!', 'success')
            return redirect(url_for('main.dashboard'))
            
        except Exception as e:
            flash(f'Error creating monitor: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('monitor_form.html')

@main_bp.route('/monitors/<int:monitor_id>')
def monitor_detail(monitor_id):
    """Monitor detail page with history."""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    # Get check history (last 24 hours by default)
    hours = request.args.get('hours', 24, type=int)
    since = datetime.utcnow() - timedelta(hours=hours)
    
    checks = monitor.checks.filter(
        MonitorCheck.checked_at >= since
    ).order_by(MonitorCheck.checked_at.desc()).all()
    
    # Get incidents for this monitor
    incidents = monitor.incidents.order_by(Incident.started_at.desc()).limit(10).all()
    
    return render_template('monitor_detail.html',
                         monitor=monitor,
                         checks=checks,
                         incidents=incidents,
                         hours=hours)

@main_bp.route('/monitors/<int:monitor_id>/edit', methods=['GET', 'POST'])
def edit_monitor(monitor_id):
    """Edit monitor configuration."""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    if request.method == 'POST':
        try:
            # Parse headers if provided
            headers = request.form.get('headers', '').strip()
            if headers:
                try:
                    json.loads(headers)  # Validate JSON
                except json.JSONDecodeError:
                    flash('Invalid JSON format in headers', 'error')
                    return render_template('monitor_form.html', monitor=monitor)
            
            monitor.name = request.form['name']
            monitor.url = request.form['url']
            monitor.monitor_type = request.form.get('monitor_type', 'http')
            monitor.method = request.form.get('method', 'GET')
            monitor.expected_status = int(request.form.get('expected_status', 200))
            monitor.expected_text = request.form.get('expected_text', '').strip() or None
            monitor.timeout = int(request.form.get('timeout', 30))
            monitor.interval = int(request.form.get('interval', 60))
            monitor.retries = int(request.form.get('retries', 3))
            monitor.headers = headers or None
            monitor.body = request.form.get('body', '').strip() or None
            monitor.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash(f'Monitor "{monitor.name}" updated successfully!', 'success')
            return redirect(url_for('main.monitor_detail', monitor_id=monitor.id))
            
        except Exception as e:
            flash(f'Error updating monitor: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('monitor_form.html', monitor=monitor)

@main_bp.route('/monitors/<int:monitor_id>/delete', methods=['POST'])
def delete_monitor(monitor_id):
    """Delete monitor."""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    try:
        db.session.delete(monitor)
        db.session.commit()
        flash(f'Monitor "{monitor.name}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting monitor: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/monitors/<int:monitor_id>/toggle', methods=['POST'])
def toggle_monitor(monitor_id):
    """Toggle monitor active status."""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    try:
        monitor.is_active = not monitor.is_active
        monitor.updated_at = datetime.utcnow()
        db.session.commit()
        
        status = "enabled" if monitor.is_active else "disabled"
        flash(f'Monitor "{monitor.name}" {status}!', 'success')
    except Exception as e:
        flash(f'Error updating monitor: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/incidents')
def incidents():
    """List all incidents."""
    page = request.args.get('page', 1, type=int)
    incidents = Incident.query.order_by(Incident.started_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('incidents.html', incidents=incidents)

@main_bp.route('/settings')
def settings():
    """Application settings page."""
    channels = NotificationChannel.query.all()
    return render_template('settings.html', channels=channels)