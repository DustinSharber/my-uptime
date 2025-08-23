from flask import Blueprint, jsonify, request
from app import db
from app.models import Monitor, MonitorCheck, Incident
from datetime import datetime, timedelta

api_bp = Blueprint('api', __name__)

@api_bp.route('/monitors')
def api_monitors():
    """API endpoint to get all monitors."""
    monitors = Monitor.query.filter_by(is_active=True).all()
    
    monitors_data = []
    for monitor in monitors:
        monitors_data.append({
            'id': monitor.id,
            'name': monitor.name,
            'url': monitor.url,
            'status': monitor.status,
            'response_time': monitor.response_time,
            'uptime_percentage': monitor.uptime_percentage,
            'last_checked': monitor.checks.order_by(MonitorCheck.checked_at.desc()).first().checked_at.isoformat() if monitor.checks.first() else None
        })
    
    return jsonify(monitors_data)

@api_bp.route('/monitors/<int:monitor_id>')
def api_monitor_detail(monitor_id):
    """API endpoint to get monitor details."""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    return jsonify({
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
        'status': monitor.status,
        'response_time': monitor.response_time,
        'uptime_percentage': monitor.uptime_percentage,
        'is_active': monitor.is_active,
        'created_at': monitor.created_at.isoformat(),
        'updated_at': monitor.updated_at.isoformat()
    })

@api_bp.route('/monitors/<int:monitor_id>/checks')
def api_monitor_checks(monitor_id):
    """API endpoint to get monitor check history."""
    monitor = Monitor.query.get_or_404(monitor_id)
    
    # Get optional time range parameters
    hours = request.args.get('hours', 24, type=int)
    since = datetime.utcnow() - timedelta(hours=hours)
    
    checks = monitor.checks.filter(
        MonitorCheck.checked_at >= since
    ).order_by(MonitorCheck.checked_at.desc()).all()
    
    checks_data = []
    for check in checks:
        checks_data.append({
            'id': check.id,
            'is_up': check.is_up,
            'response_time': check.response_time,
            'status_code': check.status_code,
            'error_message': check.error_message,
            'checked_at': check.checked_at.isoformat()
        })
    
    return jsonify(checks_data)

@api_bp.route('/status')
def api_status():
    """API endpoint for overall system status."""
    monitors = Monitor.query.filter_by(is_active=True).all()
    
    total_monitors = len(monitors)
    up_monitors = sum(1 for m in monitors if m.status == 'up')
    down_monitors = sum(1 for m in monitors if m.status == 'down')
    unknown_monitors = total_monitors - up_monitors - down_monitors
    
    # Calculate average response time
    recent_checks = db.session.query(MonitorCheck).join(Monitor).filter(
        Monitor.is_active == True,
        MonitorCheck.checked_at >= datetime.utcnow() - timedelta(hours=1),
        MonitorCheck.is_up == True,
        MonitorCheck.response_time.is_not(None)
    ).all()
    
    avg_response_time = None
    if recent_checks:
        avg_response_time = sum(check.response_time for check in recent_checks) / len(recent_checks)
    
    return jsonify({
        'total_monitors': total_monitors,
        'up_monitors': up_monitors,
        'down_monitors': down_monitors,
        'unknown_monitors': unknown_monitors,
        'average_response_time': avg_response_time,
        'overall_status': 'operational' if down_monitors == 0 else 'degraded' if down_monitors < total_monitors else 'outage',
        'timestamp': datetime.utcnow().isoformat()
    })

@api_bp.route('/incidents')
def api_incidents():
    """API endpoint to get recent incidents."""
    limit = request.args.get('limit', 50, type=int)
    incidents = Incident.query.order_by(Incident.started_at.desc()).limit(limit).all()
    
    incidents_data = []
    for incident in incidents:
        incidents_data.append({
            'id': incident.id,
            'monitor_id': incident.monitor_id,
            'monitor_name': incident.monitor.name,
            'started_at': incident.started_at.isoformat(),
            'ended_at': incident.ended_at.isoformat() if incident.ended_at else None,
            'duration_formatted': incident.duration_formatted,
            'error_message': incident.error_message,
            'is_resolved': incident.is_resolved
        })
    
    return jsonify(incidents_data)