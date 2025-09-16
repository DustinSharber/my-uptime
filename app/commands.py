import click
from flask.cli import with_appcontext
from .database import db

@click.command('create-sample-data')
@with_appcontext
def create_sample_data_command():
    """Create sample monitors and data."""
    if not db.get_all('monitor'):
        monitors = [
            {
                'name': 'Google',
                'url': 'https://www.google.com',
                'monitor_type': 'https',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 30,
                'interval': 60,
                'retries': 3,
                'is_active': True
            },
            {
                'name': 'GitHub',
                'url': 'https://github.com',
                'monitor_type': 'https',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 30,
                'interval': 120,
                'retries': 3,
                'is_active': True
            },
            {
                'name': 'Local API',
                'url': 'http://localhost:5000/api/status',
                'monitor_type': 'http',
                'method': 'GET',
                'expected_status': 200,
                'timeout': 10,
                'interval': 30,
                'retries': 3,
                'is_active': True
            }
        ]
        
        for monitor_data in monitors:
            db.add('monitor', monitor_data)
        
        print(f"Created {len(monitors)} sample monitors")
    else:
        print("Monitors already exist, skipping sample data creation")

def init_app(app):
    app.cli.add_command(create_sample_data_command)
