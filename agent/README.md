# Python Monitor

A comprehensive Python-based uptime monitoring system similar to UptimeKuma, built with Flask and modern web technologies.

## 📋 Features

- **Real-time Monitoring**: Monitor HTTP/HTTPS endpoints, ping hosts, and custom services
- **Agent Support**: Deploy lightweight monitoring agents on remote systems
- **Dashboard**: Modern web interface with real-time status updates
- **Notifications**: Email and webhook notifications for incidents
- **Maintenance Windows**: Schedule maintenance periods to prevent false alerts
- **Status Pages**: Public status pages for your services
- **Command Execution**: Run remote commands on monitored systems
- **Log Monitoring**: Monitor and analyze log files from agents
- **Historical Data**: Track uptime history and performance metrics

## 🚀 Quick Start with Docker

### Prerequisites

- Docker
- Docker Compose (optional)

### Docker Deployment

**Build and Run with Docker**

```bash
# Clone the repository
git clone <repository-url>
cd my-uptime

# Build the Docker image
docker build -t my-uptime .

# Run the Docker container
docker run -d -p 5000:5000 --name my-uptime-container my-uptime
```

Access the application at `http://localhost:5000`.

## 🛠️ Local Development Setup

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Git

### Step 1: Clone and Setup Environment

```bash
# Clone the repository
git clone <repository-url>
cd my-uptime

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Environment Configuration

Create a `.env` file in the root directory (optional, uses defaults if not provided):

```bash
# .env file (optional)
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///monitoring.db
FLASK_ENV=development
DEFAULT_CHECK_INTERVAL=60
MAX_RESPONSE_TIME=30
KEEP_HISTORY_DAYS=30
TIMEZONE=UTC
LOGIN_REQUIRED=False
```

### Step 3: Database Setup

The application uses SQLite by default and will automatically create the database on first run.

```bash
# Create necessary directories
mkdir -p logs data instance

# The database will be created automatically when you run the app
# Default location: monitoring.db in the root directory
```

### Step 4: Run the Application

```bash
# Make sure your virtual environment is activated
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Run the development server
python app.py

# Or use Flask CLI
flask run
```

The application will be available at:
- **Main Application**: `http://localhost:5000`
- **Development Mode**: Includes debugging and auto-reload

### Step 5: First Time Setup

1. Open `http://localhost:5000` in your browser
2. The application will create default database tables automatically
3. Start adding monitors and configuring your monitoring setup

## 🏗️ Project Structure

```
my-uptime/
├── app/                    # Main application package
│   ├── __init__.py        # App factory and configuration
│   ├── models.py          # Database models
│   ├── routes.py          # Web routes and views
│   ├── api.py            # REST API endpoints
│   ├── monitoring.py     # Monitoring service logic
│   ├── scheduler.py      # Background task scheduler
│   ├── notifications.py  # Notification handlers
│   └── utils.py          # Utility functions
├── agent/                 # Monitoring agents
│   ├── agent.py          # Main agent script
│   ├── build_*.sh        # Build scripts for different platforms
│   └── requirements.txt  # Agent dependencies
├── config/               # Configuration files
├── templates/           # Jinja2 HTML templates
├── static/             # CSS, JS, and other static files
├── instance/           # Instance-specific configuration
├── logs/              # Application logs
├── data/              # Application data
├── app.py             # Application entry point
├── requirements.txt   # Python dependencies
├── Dockerfile        # Docker configuration
└── README.md         # This file
```

## 🔧 Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Flask secret key |
| `DATABASE_URL` | `sqlite:///monitoring.db` | Database connection string |
| `FLASK_ENV` | `development` | Flask environment |
| `DEFAULT_CHECK_INTERVAL` | `60` | Default monitoring interval (seconds) |
| `MAX_RESPONSE_TIME` | `30` | Maximum response time (seconds) |
| `KEEP_HISTORY_DAYS` | `30` | Days to keep monitoring history |
| `TIMEZONE` | `UTC` | Application timezone |
| `LOGIN_REQUIRED` | `False` | Require authentication |
| `PORT` | `5000` | Application port |

### Instance Settings

Edit `instance/settings.json` for runtime configuration:

```json
{
    "timezone": "US/Central",
    "login_required": false,
    "site_name": "My Uptime Monitor",
    "footer_text": "Powered by Python Monitor",
    "site_icon": "",
    "favicon_url": ""
}
```

## 🤖 Monitoring Agents

The system includes lightweight monitoring agents that can be deployed on remote systems to collect metrics and logs.

### Building Agents

```bash
cd agent

# Build for Linux (native)
./build_linux.sh

# Build for Windows (requires Wine or Windows system)
./build_windows.bat

# Build compatible Linux version (older GLIBC)
./build_compatible_linux.sh

# Cross-platform build
./build_cross_platform.sh agent.py uptime_agent_linux linux
```

### Running Agents

```bash
# Set environment variables
export UPTIME_API_KEY="your-monitor-api-key"
export UPTIME_API_ENDPOINT="http://your-server:5000/api"

# Run the agent
./dist/uptime_agent_linux
```

For detailed agent setup and troubleshooting, see `agent/GLIBC_COMPATIBILITY_GUIDE.md`.

## 🔍 Development Commands

```bash
# Run with debug mode
FLASK_ENV=development python app.py

# Run with custom port
PORT=8080 python app.py

# Run with custom database
DATABASE_URL=postgresql://user:pass@localhost/db python app.py

# View logs
tail -f logs/app.log
```

## 🚀 Production Deployment

### Using Gunicorn

```bash
# Install gunicorn (included in requirements.txt)
pip install gunicorn

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:application
```

### Environment Variables for Production

```bash
export SECRET_KEY="your-production-secret-key"
export DATABASE_URL="postgresql://user:pass@localhost/production_db"
export FLASK_ENV="production"
export LOGIN_REQUIRED="True"
```

## 🐛 Troubleshooting

### Common Issues

1. **Database not created**: Ensure the `data` directory exists and is writable
2. **Port already in use**: Change the PORT environment variable
3. **Agent connection issues**: Verify API_ENDPOINT and API_KEY are correct
4. **GLIBC compatibility**: Use the compatible Linux build script for older systems

### Logs

- Application logs: `logs/app.log`
- Monitor service logs: Check the application output
- Agent logs: Agents log to stdout/stderr

### Getting Help

1. Check the logs for error messages
2. Verify your environment variables are set correctly
3. Ensure all dependencies are installed
4. For agent issues, see `agent/GLIBC_COMPATIBILITY_GUIDE.md`

## 📄 License

This project is provided as-is for monitoring purposes.
