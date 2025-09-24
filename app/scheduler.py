from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.database import db
from app.models import Command, BackupConfig
from app.utils import perform_backup
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def queue_command(command_id):
    """Queue a command for execution."""
    command_data = db.get_by_id('command', command_id)
    if not command_data:
        return

    command = Command(**command_data)
    
    pending_command_data = {
        'command_id': command.id,
        'monitor_id': command.monitor_id,
        'script': command.script,
        'status': 'pending',
    }
    db.add('pending_command', pending_command_data)
    print(f"Queued scheduled command: {command.name}")

def execute_backup(backup_config_id):
    """Execute a scheduled backup."""
    backup_config_data = db.get_by_id('backup_config', backup_config_id)
    if not backup_config_data:
        print(f"Backup configuration {backup_config_id} not found")
        return

    backup_config = BackupConfig(**backup_config_data)
    print(f"Starting backup: {backup_config.name}")
    
    # Perform the backup
    success, error_message = perform_backup(backup_config, db)
    
    # Update backup status
    update_data = {
        'last_backup_at': datetime.utcnow().isoformat(),
        'last_backup_status': 'success' if success else 'failed',
        'last_backup_error': error_message if not success else None
    }
    
    db.update('backup_config', backup_config_id, update_data)
    
    if success:
        print(f"Backup '{backup_config.name}' completed successfully")
    else:
        print(f"Backup '{backup_config.name}' failed: {error_message}")

def execute_data_cleanup():
    """Execute automatic data cleanup for performance optimization."""
    try:
        from app.cleanup import DataCleanupService
        
        logger.info("Starting scheduled data cleanup...")
        cleanup_service = DataCleanupService()
        result = cleanup_service.run_full_cleanup()
        
        total_removed = result.get('total_removed', 0)
        if total_removed > 0:
            logger.info(f"Scheduled cleanup completed: {total_removed} items removed")
            print(f"Data cleanup completed: {total_removed} old records removed for better performance")
        else:
            logger.debug("Scheduled cleanup completed: no old data to remove")
            
    except Exception as e:
        logger.error(f"Error during scheduled cleanup: {str(e)}")
        print(f"Data cleanup failed: {str(e)}")

def init_scheduler():
    """Initializes and starts the scheduler."""
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    # Load all commands with 'schedule' trigger
    all_commands = db.get_all('command')
    for cmd_data in all_commands:
        if cmd_data.get('trigger') == 'schedule' and cmd_data.get('schedule'):
            command = Command(**cmd_data)
            try:
                scheduler.add_job(
                    func=queue_command,
                    trigger=CronTrigger.from_crontab(command.schedule),
                    args=[command.id],
                    id=f'command_{command.id}',
                    replace_existing=True
                )
                print(f"Scheduled command '{command.name}' with schedule: {command.schedule}")
            except Exception as e:
                print(f"Failed to schedule command '{command.name}': {e}")
    
    # Load all active backup configurations
    all_backup_configs = db.get_all('backup_config')
    for backup_data in all_backup_configs:
        if backup_data.get('is_active'):
            backup_config = BackupConfig(**backup_data)
            cron_expression = backup_config.get_cron_expression()
            
            if cron_expression:
                try:
                    scheduler.add_job(
                        func=execute_backup,
                        trigger=CronTrigger.from_crontab(cron_expression),
                        args=[backup_config.id],
                        id=f'backup_{backup_config.id}',
                        replace_existing=True
                    )
                    print(f"Scheduled backup '{backup_config.name}' with schedule: {cron_expression}")
                except Exception as e:
                    print(f"Failed to schedule backup '{backup_config.name}': {e}")
    
    # Schedule automatic data cleanup for performance optimization
    # Run daily at 3 AM to clean up old monitoring data
    try:
        scheduler.add_job(
            func=execute_data_cleanup,
            trigger=CronTrigger.from_crontab('0 3 * * *'),  # Daily at 3:00 AM
            id='auto_data_cleanup',
            replace_existing=True
        )
        print("Scheduled automatic data cleanup: daily at 3:00 AM")
        logger.info("Automatic data cleanup scheduled for daily execution at 3:00 AM")
    except Exception as e:
        print(f"Failed to schedule automatic cleanup: {e}")
        logger.error(f"Failed to schedule automatic cleanup: {e}")
    
    return scheduler
