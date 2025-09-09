from flask import Flask
from config.settings import config
import os
from datetime import datetime
import pytz

def create_app(config_name=None):
    """Application factory pattern."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    # Set the correct template and static folders
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    app.config.from_object(config[config_name])
    
    # Register blueprints
    from app.routes import main_bp
    from app.api import api_bp
    from app.utils import format_datetime_filter
    
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Register custom Jinja2 filter
    app.jinja_env.filters['format_datetime'] = format_datetime_filter

    def format_datetime_tz(value, format='%Y-%m-%d %H:%M:%S'):
        if value is None:
            return ""
        
        # If the datetime is naive, assume it's in UTC and make it aware.
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            utc_dt = pytz.utc.localize(value)
        else:
            # It's already aware.
            utc_dt = value
        
        # Convert to target timezone
        target_tz_str = app.config.get('TIMEZONE', 'UTC')
        try:
            target_tz = pytz.timezone(target_tz_str)
        except pytz.UnknownTimeZoneError:
            target_tz = pytz.utc # Fallback to UTC
            
        local_dt = utc_dt.astimezone(target_tz)
        
        return local_dt.strftime(f"{format} ({target_tz_str})")

    app.jinja_env.filters['format_datetime_tz'] = format_datetime_tz

    def format_datetime_schedule(value, tz_name='UTC', format='%Y-%m-%d %H:%M:%S'):
        """
        Jinja2 filter to format a UTC datetime into a specific timezone.
        """
        if value is None:
            return ""
        
        # Ensure the source datetime is UTC-aware
        if value.tzinfo is None:
            utc_dt = pytz.utc.localize(value)
        else:
            utc_dt = value.astimezone(pytz.utc)
            
        # Convert to the target timezone
        try:
            target_tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            target_tz = pytz.utc # Fallback
            
        local_dt = utc_dt.astimezone(target_tz)
        
        return local_dt.strftime(f"{format} ({tz_name})")

    app.jinja_env.filters['format_datetime_schedule'] = format_datetime_schedule

    @app.context_processor
    def inject_now_utc():
        return {'now_utc': datetime.utcnow}
    
    return app
