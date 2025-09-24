#!/usr/bin/env python3
"""
Data Cleanup Service for Uptime Monitor
Manages old data cleanup and database optimization
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
import pytz
from .database import db
from .utils import parse_timestamp

logger = logging.getLogger(__name__)

class DataCleanupService:
    """Service for cleaning up old monitoring data to improve performance."""
    
    def __init__(self, app=None):
        self.app = app
        # Default retention periods (can be overridden by app config)
        self.default_config = {
            'CHECKS_RETENTION_DAYS': 7,      # Keep check data for 7 days (reduced from 30)
            'HISTORY_RETENTION_DAYS': 30,    # Keep history for 30 days  
            'INCIDENTS_RETENTION_DAYS': 90,  # Keep resolved incidents for 90 days
            'AGENT_METRICS_RETENTION_DAYS': 14,  # Keep agent metrics for 14 days
            'AGENT_LOGS_RETENTION_DAYS': 7,   # Keep agent logs for 7 days
            'PENDING_COMMANDS_RETENTION_DAYS': 30,  # Keep old pending commands for 30 days
        }
    
    def get_retention_config(self):
        """Get retention configuration from app config or defaults."""
        if self.app:
            return {
                key: self.app.config.get(key, default_value) 
                for key, default_value in self.default_config.items()
            }
        return self.default_config
    
    def cleanup_checks(self):
        """Clean up old check data - this is the biggest performance impact."""
        try:
            config = self.get_retention_config()
            cutoff_date = datetime.now(pytz.utc) - timedelta(days=config['CHECKS_RETENTION_DAYS'])
            
            all_checks = db.get_all('check')
            original_count = len(all_checks)
            
            # Keep only recent checks
            checks_to_keep = []
            for check in all_checks:
                checked_at = parse_timestamp(check.get('checked_at'))
                if checked_at and checked_at >= cutoff_date:
                    checks_to_keep.append(check)
            
            removed_count = original_count - len(checks_to_keep)
            
            if removed_count > 0:
                db.write_data(db.model_files['check'], checks_to_keep)
                logger.info(f'Cleanup: Removed {removed_count} old checks (kept {len(checks_to_keep)} recent checks)')
                
                # Clear any cached dashboard data after cleanup
                if self.app and hasattr(self.app, '_dashboard_cache'):
                    delattr(self.app, '_dashboard_cache')
                if self.app and hasattr(self.app, '_dashboard_cache_time'):
                    delattr(self.app, '_dashboard_cache_time')
                
                return removed_count
            else:
                logger.debug('Cleanup: No old checks to remove')
                return 0
                
        except Exception as e:
            logger.error(f'Error cleaning up checks: {str(e)}')
            return 0
    
    def cleanup_history(self):
        """Clean up old history data."""
        try:
            config = self.get_retention_config()
            cutoff_date = datetime.now(pytz.utc) - timedelta(days=config['HISTORY_RETENTION_DAYS'])
            
            all_history = db.get_all('history')
            original_count = len(all_history)
            
            history_to_keep = []
            for history_entry in all_history:
                checked_at = parse_timestamp(history_entry.get('checked_at'))
                if checked_at and checked_at >= cutoff_date:
                    history_to_keep.append(history_entry)
            
            removed_count = original_count - len(history_to_keep)
            
            if removed_count > 0:
                db.write_data(db.model_files['history'], history_to_keep)
                logger.info(f'Cleanup: Removed {removed_count} old history entries')
                return removed_count
            else:
                logger.debug('Cleanup: No old history to remove')
                return 0
                
        except Exception as e:
            logger.error(f'Error cleaning up history: {str(e)}')
            return 0
    
    def cleanup_incidents(self):
        """Clean up old resolved incidents."""
        try:
            config = self.get_retention_config()
            cutoff_date = datetime.now(pytz.utc) - timedelta(days=config['INCIDENTS_RETENTION_DAYS'])
            
            all_incidents = db.get_all('incident')
            original_count = len(all_incidents)
            
            incidents_to_keep = []
            for incident in all_incidents:
                # Keep unresolved incidents regardless of age
                if not incident.get('is_resolved', False):
                    incidents_to_keep.append(incident)
                    continue
                
                # For resolved incidents, check the end date
                ended_at = incident.get('ended_at')
                if ended_at:
                    ended_at_dt = parse_timestamp(ended_at)
                    if ended_at_dt and ended_at_dt >= cutoff_date:
                        incidents_to_keep.append(incident)
                else:
                    # Keep resolved incidents without end date (shouldn't happen but be safe)
                    incidents_to_keep.append(incident)
            
            removed_count = original_count - len(incidents_to_keep)
            
            if removed_count > 0:
                db.write_data(db.model_files['incident'], incidents_to_keep)
                logger.info(f'Cleanup: Removed {removed_count} old resolved incidents')
                return removed_count
            else:
                logger.debug('Cleanup: No old incidents to remove')
                return 0
                
        except Exception as e:
            logger.error(f'Error cleaning up incidents: {str(e)}')
            return 0
    
    def cleanup_agent_metrics(self):
        """Clean up old agent metrics."""
        try:
            config = self.get_retention_config()
            cutoff_date = datetime.now(pytz.utc) - timedelta(days=config['AGENT_METRICS_RETENTION_DAYS'])
            
            all_metrics = db.get_all('agent_metric')
            original_count = len(all_metrics)
            
            metrics_to_keep = []
            for metric in all_metrics:
                timestamp = metric.get('timestamp')
                if timestamp:
                    # Handle different timestamp formats
                    timestamp_dt = None
                    try:
                        if isinstance(timestamp, str):
                            timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            if timestamp_dt.tzinfo is None:
                                timestamp_dt = timestamp_dt.replace(tzinfo=pytz.utc)
                        elif isinstance(timestamp, (int, float)):
                            timestamp_dt = datetime.fromtimestamp(timestamp, tz=pytz.utc)
                    except (ValueError, TypeError):
                        continue
                    
                    if timestamp_dt and timestamp_dt >= cutoff_date:
                        metrics_to_keep.append(metric)
            
            removed_count = original_count - len(metrics_to_keep)
            
            if removed_count > 0:
                db.write_data(db.model_files['agent_metric'], metrics_to_keep)
                logger.info(f'Cleanup: Removed {removed_count} old agent metrics')
                return removed_count
            else:
                logger.debug('Cleanup: No old agent metrics to remove')
                return 0
                
        except Exception as e:
            logger.error(f'Error cleaning up agent metrics: {str(e)}')
            return 0
    
    def cleanup_agent_logs(self):
        """Clean up old agent logs."""
        try:
            config = self.get_retention_config()
            cutoff_date = datetime.now(pytz.utc) - timedelta(days=config['AGENT_LOGS_RETENTION_DAYS'])
            
            all_logs = db.get_all('agent_log')
            original_count = len(all_logs)
            
            logs_to_keep = []
            for log_entry in all_logs:
                timestamp = log_entry.get('timestamp')
                if timestamp:
                    timestamp_dt = None
                    try:
                        if isinstance(timestamp, str):
                            timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            if timestamp_dt.tzinfo is None:
                                timestamp_dt = timestamp_dt.replace(tzinfo=pytz.utc)
                        elif isinstance(timestamp, (int, float)):
                            timestamp_dt = datetime.fromtimestamp(timestamp, tz=pytz.utc)
                    except (ValueError, TypeError):
                        continue
                    
                    if timestamp_dt and timestamp_dt >= cutoff_date:
                        logs_to_keep.append(log_entry)
            
            removed_count = original_count - len(logs_to_keep)
            
            if removed_count > 0:
                db.write_data(db.model_files['agent_log'], logs_to_keep)
                logger.info(f'Cleanup: Removed {removed_count} old agent logs')
                return removed_count
            else:
                logger.debug('Cleanup: No old agent logs to remove')
                return 0
                
        except Exception as e:
            logger.error(f'Error cleaning up agent logs: {str(e)}')
            return 0
    
    def cleanup_pending_commands(self):
        """Clean up old pending commands that have been executed."""
        try:
            config = self.get_retention_config()
            cutoff_date = datetime.now(pytz.utc) - timedelta(days=config['PENDING_COMMANDS_RETENTION_DAYS'])
            
            all_commands = db.get_all('pending_command')
            original_count = len(all_commands)
            
            commands_to_keep = []
            for command in all_commands:
                # Keep pending commands
                if command.get('status') == 'pending':
                    commands_to_keep.append(command)
                    continue
                
                # For completed/failed commands, check execution date
                executed_at = command.get('executed_at')
                if executed_at:
                    executed_at_dt = parse_timestamp(executed_at)
                    if executed_at_dt and executed_at_dt >= cutoff_date:
                        commands_to_keep.append(command)
                else:
                    # Keep commands without execution date (shouldn't happen but be safe)
                    commands_to_keep.append(command)
            
            removed_count = original_count - len(commands_to_keep)
            
            if removed_count > 0:
                db.write_data(db.model_files['pending_command'], commands_to_keep)
                logger.info(f'Cleanup: Removed {removed_count} old pending commands')
                return removed_count
            else:
                logger.debug('Cleanup: No old pending commands to remove')
                return 0
                
        except Exception as e:
            logger.error(f'Error cleaning up pending commands: {str(e)}')
            return 0
    
    def run_full_cleanup(self):
        """Run all cleanup operations and return summary."""
        logger.info('Starting comprehensive data cleanup...')
        
        total_removed = 0
        cleanup_results = {}
        
        # Run each cleanup operation
        cleanup_operations = [
            ('checks', self.cleanup_checks),
            ('history', self.cleanup_history),
            ('incidents', self.cleanup_incidents),
            ('agent_metrics', self.cleanup_agent_metrics),
            ('agent_logs', self.cleanup_agent_logs),
            ('pending_commands', self.cleanup_pending_commands),
        ]
        
        for operation_name, operation_func in cleanup_operations:
            try:
                removed_count = operation_func()
                cleanup_results[operation_name] = removed_count
                total_removed += removed_count
                logger.debug(f'Cleanup operation {operation_name}: removed {removed_count} items')
            except Exception as e:
                logger.error(f'Error in cleanup operation {operation_name}: {str(e)}')
                cleanup_results[operation_name] = 0
        
        # Create cache invalidation marker for dashboard
        self.create_cache_invalidation_marker()
        
        logger.info(f'Data cleanup completed. Total items removed: {total_removed}')
        logger.info(f'Cleanup results: {cleanup_results}')
        
        return {
            'total_removed': total_removed,
            'results': cleanup_results,
            'timestamp': datetime.now(pytz.utc).isoformat()
        }
    
    def create_cache_invalidation_marker(self):
        """Create a marker file to indicate cache should be invalidated."""
        try:
            marker_file = Path('instance/cache_invalidated.marker')
            marker_file.parent.mkdir(exist_ok=True)
            marker_file.write_text(datetime.now(pytz.utc).isoformat())
            logger.debug('Created cache invalidation marker')
        except Exception as e:
            logger.warning(f'Could not create cache invalidation marker: {e}')
    
    def get_data_statistics(self):
        """Get current data statistics for monitoring cleanup effectiveness."""
        try:
            stats = {}
            
            # Get file sizes and record counts
            for model_name, file_path in db.model_files.items():
                try:
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        records = len(db.get_all(model_name))
                        stats[model_name] = {
                            'file_size_kb': round(file_size / 1024, 2),
                            'record_count': records
                        }
                    else:
                        stats[model_name] = {
                            'file_size_kb': 0,
                            'record_count': 0
                        }
                except Exception as e:
                    logger.warning(f'Error getting stats for {model_name}: {e}')
                    stats[model_name] = {'error': str(e)}
            
            return stats
            
        except Exception as e:
            logger.error(f'Error getting data statistics: {str(e)}')
            return {}

# Convenience function for manual cleanup
def run_cleanup():
    """Run cleanup manually - useful for cron jobs or admin scripts."""
    cleanup_service = DataCleanupService()
    return cleanup_service.run_full_cleanup()

if __name__ == '__main__':
    # Allow running cleanup as a standalone script
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("Running data cleanup...")
    result = run_cleanup()
    print(f"Cleanup completed: {result}")
