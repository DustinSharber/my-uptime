import json
from datetime import datetime
import pytz

def save_settings(settings_data, path='instance/settings.json'):
    """Save settings to a JSON file."""
    with open(path, 'w') as f:
        json.dump(settings_data, f, indent=4)

def load_settings(path='instance/settings.json'):
    """Load settings from a JSON file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def parse_timestamp(timestamp_val):
    """
    Parses a timestamp from various formats (ISO string, UNIX timestamp)
    and returns a timezone-aware datetime object in UTC.
    """
    if not timestamp_val:
        return None
    
    dt = None
    try:
        if isinstance(timestamp_val, (int, float)):
            # Handle UNIX timestamp
            dt = datetime.fromtimestamp(timestamp_val, tz=pytz.utc)
        elif isinstance(timestamp_val, str):
            # Handle ISO format string, ensuring it's treated as UTC if naive.
            
            # If the string is naive (no 'Z' or timezone offset), append '+00:00' to treat it as UTC.
            if not (timestamp_val.endswith('Z') or '+' in timestamp_val or '-' in timestamp_val[10:]):
                 timestamp_val += '+00:00'
            
            # Replace 'Z' with '+00:00' for full ISO 8601 compatibility
            if timestamp_val.endswith('Z'):
                timestamp_val = timestamp_val[:-1] + '+00:00'

            dt = datetime.fromisoformat(timestamp_val)
            
            # After parsing, ensure everything is normalized to UTC, just in case.
            dt = dt.astimezone(pytz.utc)
    except (ValueError, TypeError):
        # Return None if parsing fails
        return None
        
    return dt

def get_text_color(hex_color):
    """
    Determines if text should be black or white based on the brightness of a background hex color.
    """
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        return '#FFFFFF' if brightness < 128 else '#000000'
    except:
        return '#000000' # Default to black for invalid colors

def format_datetime_filter(value, format='%Y-%m-%d %H:%M:%S'):
    """
    Jinja2 filter to format a datetime object.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value # Return original string if parsing fails
    
    # If the datetime is naive, assume UTC
    if value.tzinfo is None:
        value = pytz.utc.localize(value)
        
    return value.strftime(format)

def clear_application_cache():
    """
    Clear all application-level caches.
    This should be called after restore operations to ensure data consistency.
    """
    try:
        from flask import current_app
        
        cache_cleared = 0
        
        # Clear dashboard cache
        if hasattr(current_app, '_dashboard_cache'):
            delattr(current_app, '_dashboard_cache')
            cache_cleared += 1
            current_app.logger.debug("Dashboard cache cleared")
            
        if hasattr(current_app, '_dashboard_cache_time'):
            delattr(current_app, '_dashboard_cache_time')
            cache_cleared += 1
            current_app.logger.debug("Dashboard cache time cleared")
        
        # Clear all monitors page caches
        attrs_to_remove = []
        for attr_name in dir(current_app):
            if attr_name.startswith('_monitors_cache_'):
                attrs_to_remove.append(attr_name)
        
        for attr_name in attrs_to_remove:
            try:
                delattr(current_app, attr_name)
                cache_cleared += 1
                current_app.logger.debug(f"Monitors cache cleared: {attr_name}")
            except AttributeError:
                # Attribute might have been removed by another thread
                pass
        
        current_app.logger.info(f"Application cache cleared after restore - {cache_cleared} cache items removed")
        
        # Create cache invalidation marker for Docker environments
        from pathlib import Path
        cache_marker = Path('instance/cache_invalidated.marker')
        cache_marker.parent.mkdir(exist_ok=True, parents=True)
        with open(cache_marker, 'w') as f:
            f.write(f"cache_cleared_at_{datetime.now().isoformat()}")
        
    except Exception as e:
        # If current_app is not available (e.g., outside Flask context),
        # we can still clear file-based caches and create the marker
        try:
            import shutil
            from pathlib import Path
            
            cache_patterns = [
                'instance/cache*',
                'instance/*.cache',
                'app_cache*'
            ]
            
            for pattern in cache_patterns:
                for path in Path('.').glob(pattern):
                    try:
                        if path.is_file():
                            path.unlink()
                        elif path.is_dir():
                            shutil.rmtree(path)
                    except Exception:
                        pass
            
            # Create cache invalidation marker
            cache_marker = Path('instance/cache_invalidated.marker')
            cache_marker.parent.mkdir(exist_ok=True, parents=True)
            with open(cache_marker, 'w') as f:
                f.write(f"cache_cleared_at_{datetime.now().isoformat()}")
                
        except Exception:
            # If all else fails, we can't clear cache but restore should still work
            pass

def perform_backup(backup_config, db_instance):
    """
    Perform a backup of the application data.
    
    Args:
        backup_config: BackupConfig object containing backup settings
        db_instance: Database instance to backup
        
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    import os
    import zipfile
    import shutil
    from pathlib import Path
    
    try:
        # Ensure backup directory exists
        backup_dir = Path(backup_config.backup_path)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"uptime_backup_{timestamp}.zip"
        backup_filepath = backup_dir / backup_filename
        
        # Create the backup zip file
        with zipfile.ZipFile(backup_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Backup all data files
            data_folder = Path(db_instance.data_folder)
            for file_path in db_instance.model_files.values():
                if os.path.exists(file_path):
                    # Add to zip with relative path
                    arcname = os.path.relpath(file_path, data_folder.parent)
                    zipf.write(file_path, arcname)
            
            # Backup instance settings
            instance_dir = Path('instance')
            if instance_dir.exists():
                for file_path in instance_dir.glob('*.json'):
                    if file_path.is_file():
                        arcname = f"instance/{file_path.name}"
                        zipf.write(file_path, arcname)
            
            # Backup logs if requested
            if backup_config.include_logs:
                logs_dir = Path('logs')
                if logs_dir.exists():
                    for file_path in logs_dir.glob('*.log'):
                        if file_path.is_file():
                            arcname = f"logs/{file_path.name}"
                            zipf.write(file_path, arcname)
        
        # Clean up old backups based on retention period
        cleanup_old_backups(backup_dir, backup_config.retention_days)
        
        return True, None
        
    except Exception as e:
        return False, str(e)

def cleanup_old_backups(backup_dir, retention_days):
    """
    Remove backup files older than the retention period.
    
    Args:
        backup_dir: Path to backup directory
        retention_days: Number of days to keep backups
    """
    import os
    from pathlib import Path
    
    try:
        backup_dir = Path(backup_dir)
        if not backup_dir.exists():
            return
        
        cutoff_time = datetime.now() - pytz.timedelta(days=retention_days)
        
        for file_path in backup_dir.glob('uptime_backup_*.zip'):
            if file_path.is_file():
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_time:
                    os.remove(file_path)
                    
    except Exception as e:
        # Log the error but don't fail the backup process
        print(f"Warning: Failed to cleanup old backups: {e}")

def create_manual_backup(db_instance):
    """
    Create a manual backup ZIP file for export.
    
    Args:
        db_instance: Database instance to backup
        
    Returns:
        tuple: (backup_file_path: str or None, error_message: str or None)
    """
    import os
    import zipfile
    import tempfile
    from pathlib import Path
    
    try:
        # Create temporary file for the backup
        temp_dir = Path(tempfile.gettempdir())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"manual_backup_{timestamp}.zip"
        backup_filepath = temp_dir / backup_filename
        
        # Create the backup zip file
        with zipfile.ZipFile(backup_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Backup all data files
            data_folder = Path(db_instance.data_folder)
            for file_path in db_instance.model_files.values():
                if os.path.exists(file_path):
                    # Add to zip with relative path
                    arcname = os.path.relpath(file_path, data_folder.parent)
                    zipf.write(file_path, arcname)
            
            # Backup instance settings
            instance_dir = Path('instance')
            if instance_dir.exists():
                for file_path in instance_dir.glob('*.json'):
                    if file_path.is_file():
                        arcname = f"instance/{file_path.name}"
                        zipf.write(file_path, arcname)
            
            # Always include logs in manual backups
            logs_dir = Path('logs')
            if logs_dir.exists():
                for file_path in logs_dir.glob('*.log'):
                    if file_path.is_file():
                        arcname = f"logs/{file_path.name}"
                        zipf.write(file_path, arcname)
        
        return str(backup_filepath), None
        
    except Exception as e:
        return None, str(e)

def restore_from_backup(backup_file_path, db_instance):
    """
    Restore application data from a backup ZIP file.
    
    Args:
        backup_file_path: Path to the backup ZIP file
        db_instance: Database instance to restore to
        
    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    import zipfile
    import shutil
    from pathlib import Path
    
    try:
        # Create backup of current data before restore
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = Path('backup_before_restore')
        backup_dir.mkdir(exist_ok=True)
        
        # Backup current data directory
        data_folder = Path(db_instance.data_folder)
        if data_folder.exists():
            shutil.copytree(data_folder, backup_dir / f"data_{current_time}")
        
        # Backup current instance directory
        instance_dir = Path('instance')
        if instance_dir.exists():
            shutil.copytree(instance_dir, backup_dir / f"instance_{current_time}")
        
        # Extract the backup ZIP
        with zipfile.ZipFile(backup_file_path, 'r') as zipf:
            zipf.extractall('.')
        
        # CRITICAL FIX: Clear application cache after restore
        clear_application_cache()
        
        return True, None
        
    except Exception as e:
        return False, str(e)
