import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///monitoring.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Monitoring settings
    DEFAULT_CHECK_INTERVAL = int(os.environ.get('DEFAULT_CHECK_INTERVAL', '60'))  # seconds
    MAX_RESPONSE_TIME = int(os.environ.get('MAX_RESPONSE_TIME', '30'))  # seconds
    KEEP_HISTORY_DAYS = int(os.environ.get('KEEP_HISTORY_DAYS', '30'))  # days
    
    # Application settings
    ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', '20'))
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    
class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}