from flask import Blueprint, jsonify, request, send_file, current_app
from werkzeug.utils import secure_filename
from app.database import db
from app.models import Monitor, MonitorCheck, Incident
from app.monitoring import MonitoringService
from datetime import datetime, timedelta
import pytz
import os
import zipfile
import tempfile
import hashlib
import mimetypes
from pathlib import Path

api_bp = Blueprint('api', __name__)

@api_bp.route('/monitors')
def api_monitors():
    """API endpoint to get all monitors."""
    all_monitors_data = db.get_all('monitor')
    active_monitors = [Monitor(**m) for m in all_monitors_data if m.get('is_active', True)]
    all_checks_data = db.get_all('check')
    
    monitors_data = []
    for monitor in active_monitors:
        monitor_checks = [c for c in all_checks_data if c['monitor_id'] == monitor.id]
        last_check = max(monitor_checks, key=lambda c: c['checked_at'], default=None)
        
        monitors_data.append({
            'id': monitor.id,
            'name': monitor.name,
            'url': monitor.url,
            'status': monitor.status,
            'response_time': monitor.response_time,
            'uptime_percentage': monitor.uptime_percentage,
            'last_checked': last_check['checked_at'] if last_check else None
        })
    
    return jsonify(monitors_data)

@api_bp.route('/monitors/<int:monitor_id>')
def api_monitor_detail(monitor_id):
    """API endpoint to get monitor details."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        return jsonify({'error': 'Monitor not found'}), 404
    monitor = Monitor(**monitor_data)
    
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
        'created_at': monitor.created_at,
        'updated_at': monitor.updated_at,
        'log_files': monitor.log_files
    })

@api_bp.route('/monitors/<int:monitor_id>/checks')
def api_monitor_checks(monitor_id):
    """API endpoint to get monitor check history."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        return jsonify({'error': 'Monitor not found'}), 404
    
    hours = request.args.get('hours', 24, type=int)
    since = datetime.utcnow() - timedelta(hours=hours)
    
    all_checks_data = db.get_all('check')
    monitor_checks = [
        c for c in all_checks_data 
        if c['monitor_id'] == monitor_id and datetime.fromisoformat(c['checked_at']) >= since
    ]
    
    checks_data = sorted(monitor_checks, key=lambda c: c['checked_at'], reverse=True)
    
    return jsonify(checks_data)

@api_bp.route('/status')
def api_status():
    """API endpoint for overall system status."""
    all_monitors_data = db.get_all('monitor')
    active_monitors = [Monitor(**m) for m in all_monitors_data if m.get('is_active', True)]
    
    total_monitors = len(active_monitors)
    up_monitors = sum(1 for m in active_monitors if m.status == 'up')
    down_monitors = total_monitors - up_monitors
    
    # Calculate average response time
    all_checks_data = db.get_all('check')
    since = datetime.utcnow() - timedelta(hours=1)
    
    active_monitor_ids = [m.id for m in active_monitors]
    
    recent_checks = [
        c for c in all_checks_data
        if c['monitor_id'] in active_monitor_ids and 
           datetime.fromisoformat(c['checked_at']) >= since and 
           c['is_up'] and 
           c.get('response_time') is not None
    ]
    
    avg_response_time = None
    if recent_checks:
        avg_response_time = sum(check['response_time'] for check in recent_checks) / len(recent_checks)
    
    return jsonify({
        'total_monitors': total_monitors,
        'up_monitors': up_monitors,
        'down_monitors': down_monitors,
        'unknown_monitors': 0, # Simplified, as status is always up or down
        'average_response_time': avg_response_time,
        'overall_status': 'operational' if down_monitors == 0 else 'degraded' if down_monitors < total_monitors else 'outage',
        'timestamp': datetime.utcnow().isoformat()
    })

@api_bp.route('/incidents')
def api_incidents():
    """API endpoint to get recent incidents."""
    limit = request.args.get('limit', 50, type=int)
    all_incidents_data = db.get_all('incident')
    all_monitors_data = db.get_all('monitor')
    
    # Create a lookup for monitor names
    monitor_names = {m['id']: m['name'] for m in all_monitors_data}
    
    sorted_incidents = sorted(all_incidents_data, key=lambda i: i['started_at'], reverse=True)
    
    incidents_data = []
    for incident_data in sorted_incidents[:limit]:
        incident = Incident(**incident_data)
        incidents_data.append({
            'id': incident.id,
            'monitor_id': incident.monitor_id,
            'monitor_name': monitor_names.get(incident.monitor_id, 'Unknown'),
            'started_at': incident.started_at,
            'ended_at': incident.ended_at if hasattr(incident, 'ended_at') else None,
            'duration_formatted': incident.duration_formatted,
            'error_message': incident.error_message,
            'is_resolved': incident.is_resolved
        })
    
    return jsonify(incidents_data)

@api_bp.route('/monitors/test', methods=['POST'])
def api_test_monitor():
    """API endpoint to test a monitor configuration."""
    config = request.json
    if not config:
        return jsonify({'error': 'Invalid configuration provided'}), 400

    try:
        # Create a temporary monitor object from the provided config
        # A dummy ID is fine since this monitor isn't saved.
        config['id'] = 0
        monitor = Monitor(**config)
        
        # Use the monitoring service to perform the check
        service = MonitoringService()
        result = service.check_monitor(monitor)
        
        # We don't want to save the check, just return the result
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'is_up': False,
            'status_code': None,
            'response_time': 0,
            'error_message': str(e)
        }), 500

@api_bp.route('/agent/data', methods=['POST'])
def api_agent_data():
    """API endpoint for agents to post system metrics."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Authorization header missing or invalid'}), 401
    
    api_key = auth_header.split(' ')[1]
    
    # Find the monitor associated with this API key
    # In a real app, you'd have a secure way to look this up.
    # For now, we'll assume the API key IS the monitor ID for simplicity.
    try:
        monitor_id = int(api_key)
        monitor = db.get_by_id('monitor', monitor_id)
        if not monitor:
            return jsonify({'error': 'Invalid API Key'}), 403
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid API Key format'}), 403

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Save the metrics data
    # Convert timestamp to ISO format for consistent storage
    timestamp = data.get('timestamp')
    if isinstance(timestamp, (int, float)):
        # Use utcfromtimestamp to ensure all timestamps are in UTC
        timestamp = datetime.utcfromtimestamp(timestamp).isoformat()

    # Process metrics
    if 'metrics' in data:
        metric_data = {
            'monitor_id': monitor_id,
            'timestamp': timestamp,
            **data['metrics']
        }
        db.add('agent_metric', metric_data)

    # Process logs
    if 'logs' in data and data['logs']:
        log_data = {
            'monitor_id': monitor_id,
            'timestamp': timestamp,
            'logs': data['logs']
        }
        db.add('agent_log', log_data)

    return jsonify({'status': 'success'}), 200

def get_logs_directory():
    """Get the logs storage directory, creating it if needed."""
    logs_dir = Path(current_app.root_path).parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    return logs_dir

def calculate_file_hash(file_path):
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

@api_bp.route('/agent/logs/upload', methods=['POST'])
def api_agent_logs_upload():
    """API endpoint for agents to upload log files."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Authorization header missing or invalid'}), 401
    
    api_key = auth_header.split(' ')[1]
    
    try:
        monitor_id = int(api_key)
        monitor = db.get_by_id('monitor', monitor_id)
        if not monitor:
            return jsonify({'error': 'Invalid API Key'}), 403
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid API Key format'}), 403

    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400
    
    # Get timestamp for this upload batch
    timestamp = datetime.utcnow()
    timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')
    
    # Create monitor-specific directory
    logs_dir = get_logs_directory()
    monitor_dir = logs_dir / str(monitor_id) / timestamp_str
    monitor_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded_files = []
    
    try:
        for file in files:
            if file and file.filename:
                # Secure the filename
                filename = secure_filename(file.filename)
                if not filename:
                    continue
                
                # Save the file
                file_path = monitor_dir / filename
                file.save(str(file_path))
                
                # Calculate file info
                file_size = file_path.stat().st_size
                file_hash = calculate_file_hash(file_path)
                
                # Determine content type
                content_type, _ = mimetypes.guess_type(str(file_path))
                if not content_type:
                    content_type = 'text/plain'
                
                uploaded_files.append({
                    'original_filename': file.filename,
                    'stored_filename': filename,
                    'stored_path': str(file_path.relative_to(logs_dir)),
                    'file_size': file_size,
                    'checksum': file_hash,
                    'content_type': content_type
                })
        
        if uploaded_files:
            # Save log entry with file references
            log_data = {
                'monitor_id': monitor_id,
                'timestamp': timestamp.isoformat(),
                'uploaded_files': uploaded_files,
                'upload_count': len(uploaded_files)
            }
            db.add('agent_log', log_data)
            
            return jsonify({
                'status': 'success',
                'uploaded_files': len(uploaded_files),
                'files': uploaded_files
            }), 200
        else:
            return jsonify({'error': 'No valid files processed'}), 400
            
    except Exception as e:
        current_app.logger.error(f"Error uploading log files: {str(e)}")
        return jsonify({'error': 'File upload failed'}), 500

@api_bp.route('/monitors/<int:monitor_id>/logs/files', methods=['GET'])
def api_monitor_log_files(monitor_id):
    """API endpoint to list available log files for a monitor."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        return jsonify({'error': 'Monitor not found'}), 404
    
    monitor = Monitor(**monitor_data)
    if not monitor.server_client:
        return jsonify({'error': 'This monitor is not configured as a server client'}), 400
    
    # Get time filter
    hours = request.args.get('hours', 24, type=int)
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # Get log entries with files
    all_logs = db.get_all('agent_log')
    monitor_logs = [
        log for log in all_logs
        if log['monitor_id'] == monitor_id and 
           'uploaded_files' in log and 
           datetime.fromisoformat(log['timestamp']) >= since
    ]
    
    # Organize files by upload batch
    file_batches = []
    logs_dir = get_logs_directory()
    
    for log_entry in sorted(monitor_logs, key=lambda x: x['timestamp'], reverse=True):
        batch_files = []
        for file_info in log_entry.get('uploaded_files', []):
            full_path = logs_dir / file_info['stored_path']
            if full_path.exists():
                batch_files.append({
                    'filename': file_info['original_filename'],
                    'stored_filename': file_info['stored_filename'],
                    'file_size': file_info['file_size'],
                    'content_type': file_info.get('content_type', 'text/plain'),
                    'checksum': file_info.get('checksum'),
                    'download_url': f"/api/monitors/{monitor_id}/logs/download/{file_info['stored_path']}"
                })
        
        if batch_files:
            file_batches.append({
                'timestamp': log_entry['timestamp'],
                'files': batch_files,
                'total_files': len(batch_files),
                'total_size': sum(f['file_size'] for f in batch_files)
            })
    
    return jsonify({
        'monitor_id': monitor_id,
        'batches': file_batches,
        'total_batches': len(file_batches),
        'total_files': sum(batch['total_files'] for batch in file_batches)
    })

@api_bp.route('/monitors/<int:monitor_id>/logs/download/<path:file_path>', methods=['GET'])
def api_download_log_file(monitor_id, file_path):
    """API endpoint to download a specific log file."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        return jsonify({'error': 'Monitor not found'}), 404
    
    monitor = Monitor(**monitor_data)
    if not monitor.server_client:
        return jsonify({'error': 'This monitor is not configured as a server client'}), 400
    
    # Validate the file path belongs to this monitor
    if not file_path.startswith(str(monitor_id) + '/'):
        return jsonify({'error': 'Access denied'}), 403
    
    logs_dir = get_logs_directory()
    full_file_path = logs_dir / file_path
    
    # Security check - ensure the path is within logs directory
    try:
        full_file_path.resolve().relative_to(logs_dir.resolve())
    except ValueError:
        return jsonify({'error': 'Invalid file path'}), 400
    
    if not full_file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    # Determine content type
    content_type, _ = mimetypes.guess_type(str(full_file_path))
    if not content_type:
        content_type = 'text/plain'
    
    return send_file(
        str(full_file_path),
        as_attachment=True,
        download_name=full_file_path.name,
        mimetype=content_type
    )

@api_bp.route('/monitors/<int:monitor_id>/logs/download-batch/<timestamp>', methods=['GET'])
def api_download_log_batch(monitor_id, timestamp):
    """API endpoint to download all log files from a specific upload batch as a zip."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        return jsonify({'error': 'Monitor not found'}), 404
    
    monitor = Monitor(**monitor_data)
    if not monitor.server_client:
        return jsonify({'error': 'This monitor is not configured as a server client'}), 400
    
    # Find the log entry for this timestamp
    all_logs = db.get_all('agent_log')
    log_entry = None
    for log in all_logs:
        if (log['monitor_id'] == monitor_id and 
            log.get('timestamp') == timestamp and 
            'uploaded_files' in log):
            log_entry = log
            break
    
    if not log_entry:
        return jsonify({'error': 'Log batch not found'}), 404
    
    logs_dir = get_logs_directory()
    
    # Create a temporary zip file
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip.close()
    
    try:
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_info in log_entry['uploaded_files']:
                file_path = logs_dir / file_info['stored_path']
                if file_path.exists():
                    # Use original filename in the zip
                    zipf.write(str(file_path), file_info['original_filename'])
        
        # Determine zip filename
        timestamp_formatted = datetime.fromisoformat(timestamp).strftime('%Y%m%d_%H%M%S')
        zip_filename = f"logs_{monitor.name}_{timestamp_formatted}.zip"
        
        return send_file(
            temp_zip.name,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error creating zip file: {str(e)}")
        return jsonify({'error': 'Failed to create zip file'}), 500
    finally:
        # Cleanup will happen when the file is sent
        pass

@api_bp.route('/monitors/<int:monitor_id>/logs/cleanup', methods=['POST'])
def api_cleanup_log_files(monitor_id):
    """API endpoint to cleanup old log files."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        return jsonify({'error': 'Monitor not found'}), 404
    
    # Get cleanup parameters
    data = request.get_json() or {}
    days_to_keep = data.get('days_to_keep', 7)
    
    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    
    logs_dir = get_logs_directory()
    monitor_logs_dir = logs_dir / str(monitor_id)
    
    if not monitor_logs_dir.exists():
        return jsonify({'status': 'success', 'deleted_files': 0, 'freed_space': 0})
    
    deleted_files = 0
    freed_space = 0
    
    try:
        # Get all log entries for this monitor
        all_logs = db.get_all('agent_log')
        logs_to_delete = []
        
        for log_entry in all_logs:
            if (log_entry['monitor_id'] == monitor_id and 
                'uploaded_files' in log_entry):
                log_timestamp = datetime.fromisoformat(log_entry['timestamp'])
                
                if log_timestamp < cutoff_date:
                    # Delete physical files
                    for file_info in log_entry.get('uploaded_files', []):
                        file_path = logs_dir / file_info['stored_path']
                        if file_path.exists():
                            freed_space += file_path.stat().st_size
                            file_path.unlink()
                            deleted_files += 1
                    
                    logs_to_delete.append(log_entry['id'])
        
        # Remove database entries
        if logs_to_delete:
            updated_logs = [log for log in all_logs if log['id'] not in logs_to_delete]
            db.write_data(db.model_files['agent_log'], updated_logs)
        
        # Clean up empty directories
        for timestamp_dir in monitor_logs_dir.iterdir():
            if timestamp_dir.is_dir() and not any(timestamp_dir.iterdir()):
                timestamp_dir.rmdir()
        
        return jsonify({
            'status': 'success',
            'deleted_files': deleted_files,
            'freed_space': freed_space,
            'deleted_entries': len(logs_to_delete)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error during cleanup: {str(e)}")
        return jsonify({'error': 'Cleanup failed'}), 500

@api_bp.route('/monitors/<int:monitor_id>/metrics')
def api_monitor_metrics(monitor_id):
    """API endpoint to get monitor system metrics history."""
    monitor_data = db.get_by_id('monitor', monitor_id)
    if not monitor_data:
        return jsonify({'error': 'Monitor not found'}), 404
    
    monitor = Monitor(**monitor_data)
    if not monitor.server_client:
        return jsonify({'error': 'This monitor is not configured as a server client'}), 400
    
    hours = request.args.get('hours', 24, type=int)
    # Make 'since' timezone-aware (UTC)
    since = datetime.utcnow().replace(tzinfo=pytz.utc) - timedelta(hours=hours)
    
    all_metrics = db.get_all('agent_metric')
    monitor_metrics = [
        m for m in all_metrics 
        if m['monitor_id'] == monitor_id and 
           # Make the stored timestamp timezone-aware for correct comparison
           datetime.fromisoformat(m['timestamp']).replace(tzinfo=pytz.utc) >= since
    ]
    
    # Ensure timestamps are in the correct format
    for metric in monitor_metrics:
        if isinstance(metric['timestamp'], str):
            metric['timestamp'] = datetime.fromisoformat(metric['timestamp']).timestamp()

    metrics_data = sorted(monitor_metrics, key=lambda m: m['timestamp'])
    
    return jsonify(metrics_data)

@api_bp.route('/agent/commands', methods=['GET'])
def agent_commands():
    """Endpoint for agents to fetch pending commands."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Authorization header missing or invalid'}), 401
    
    api_key = auth_header.split(' ')[1]
    
    try:
        monitor_id = int(api_key)
        monitor = db.get_by_id('monitor', monitor_id)
        if not monitor:
            return jsonify({'error': 'Invalid API Key'}), 403
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid API Key format'}), 403

    all_pending_commands = db.get_all('pending_command')
    
    commands_for_agent = [
        cmd for cmd in all_pending_commands 
        if cmd['monitor_id'] == monitor_id and cmd['status'] == 'pending'
    ]
    
    # Mark fetched commands as 'in_progress'
    for cmd in commands_for_agent:
        db.update('pending_command', cmd['id'], {'status': 'in_progress'})
        
    return jsonify(commands_for_agent)

@api_bp.route('/agent/commands/<int:command_id>/update', methods=['POST'])
def update_command_status(command_id):
    """Endpoint for agents to update the status of an executed command."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Authorization header missing or invalid'}), 401
    
    api_key = auth_header.split(' ')[1]
    
    try:
        monitor_id = int(api_key)
        monitor = db.get_by_id('monitor', monitor_id)
        if not monitor:
            return jsonify({'error': 'Invalid API Key'}), 403
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid API Key format'}), 403

    pending_command = db.get_by_id('pending_command', command_id)
    if not pending_command or pending_command['monitor_id'] != monitor_id:
        return jsonify({'error': 'Command not found or access denied'}), 404

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    update_data = {
        'status': data.get('status'),
        'output': data.get('output'),
        'executed_at': datetime.utcnow().isoformat()
    }
    db.update('pending_command', command_id, update_data)

    return jsonify({'status': 'success'}), 200
