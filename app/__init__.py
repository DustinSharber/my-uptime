from flask import Flask
from config.settings import config
from app.utils import load_settings
import os
from datetime import datetime
import pytz
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from app.models import User

login_manager = LoginManager()
bcrypt = Bcrypt()

@login_manager.user_loader
def load_user(user_id):
    from app.database import db
    return User.get(db, int(user_id))

def create_app(config_name=None):
    """Application factory pattern."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    # Set the correct template and static folders
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    app.config.from_object(config[config_name])

    # Load and apply settings from file, ensuring they override defaults
    user_settings = load_settings()
    if user_settings:
        # The value from the JSON file might be a boolean, which is what we want.
        # The config from the object might be a string 'True'/'False'.
        # We'll directly update the config.
        if 'login_required' in user_settings:
            app.config['LOGIN_REQUIRED'] = user_settings['login_required']
        if 'timezone' in user_settings:
            app.config['TIMEZONE'] = user_settings['timezone']

    # Initialize extensions
    login_manager.init_app(app)
    bcrypt.init_app(app)
    login_manager.login_view = 'main.login'
    
    # Register blueprints
    from app.routes import main_bp
    from app.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Register custom Jinja2 filters and globals
    from app.utils import get_text_color, format_datetime_filter
    app.jinja_env.globals['get_text_color'] = get_text_color
    app.jinja_env.filters['format_datetime'] = format_datetime_filter
    
    def get_setting(key, default=None):
        """Get a setting value from the settings file."""
        settings = load_settings()
        return settings.get(key, default)
    
    app.jinja_env.globals['get_setting'] = get_setting

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

    def from_iso_format(iso_str):
        """Converts an ISO format string to a datetime object."""
        if not iso_str:
            return None
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.utc)
        return dt

    def from_unix_timestamp(unix_ts):
        """Converts a UNIX timestamp to a UTC datetime object."""
        if unix_ts is None:
            return ""
        return datetime.fromtimestamp(unix_ts, tz=pytz.utc)

    def from_utc(dt):
        """Converts a naive datetime (assumed UTC) to an aware datetime."""
        if dt is None:
            return None
        return pytz.utc.localize(dt)

    app.jinja_env.filters['from_iso_format'] = from_iso_format
    app.jinja_env.filters['from_unix_timestamp'] = from_unix_timestamp
    app.jinja_env.filters['from_utc'] = from_utc

    @app.context_processor
    def inject_now_utc():
        return {'now_utc': datetime.utcnow}

    # Initialize CLI commands
    from . import commands
    commands.init_app(app)

    with app.app_context():
        from .database import db
        
        if not User.find_by_username(db, 'admin'):
            print("Admin user not found, creating one...")
            hashed_password = bcrypt.generate_password_hash("password").decode('utf-8')
            user_data = {
                'username': 'admin',
                'password': hashed_password,
                'role': 'edit',
                'password_reset_required': False
            }
            db.add('user', user_data)
            print("Admin user created with username 'admin' and password 'password'.")
    
    return app
