# Python Monitor

A comprehensive Python-based uptime monitoring system similar to UptimeKuma, built with Flask and modern web technologies.

## 🌐 Live Demo

- **Web Interface**: https://3000-ii491u3e7hez8z99xedjf-6532622b.e2b.dev
- **API Endpoints**: https://3000-ii491u3e7hez8z99xedjf-6532622b.e2b.dev/api/status

## ✨ Features

### Currently Implemented

- **📊 Responsive Web Dashboard** - Modern, mobile-friendly interface built with TailwindCSS
- **🔍 Multiple Monitor Types**: HTTP/HTTPS, Ping, and Port monitoring
- **📈 Real-time Status Tracking** - Live monitoring with automatic refresh
- **⚠️ Incident Management** - Automatic incident creation and resolution tracking
- **🔔 Multiple Notification Channels**:
  - Email notifications (SMTP support)
  - Webhook notifications (REST API)
  - Slack integration
- **📊 RESTful API** - Complete API for external integrations
- **📱 Responsive Design** - Works seamlessly on desktop and mobile
- **⏱️ Configurable Monitoring**:
  - Custom check intervals (30s - 1h)
  - Timeout settings (5s - 2m)
  - Retry logic (1-10 attempts)
  - Expected status codes and content verification
- **📈 Historical Data**:
  - Response time tracking and charts
  - Uptime percentage calculations
  - Incident history and duration tracking
- **🚦 Status Indicators**:
  - Real-time status updates
  - Animated pulse indicators
  - Color-coded status badges

### Features Not Yet Implemented

- **🔐 User Authentication & Authorization** - Multi-user support with role-based access
- **📊 Advanced Analytics & Reporting** - Detailed charts, trends, and reporting features
- **🌍 Status Page** - Public status pages for external users
- **📱 Mobile App** - Native mobile applications
- **🔄 Backup & Restore** - Automated backup and restore functionality
- **🔌 Plugin System** - Extensible plugin architecture
- **🌐 Multi-language Support** - Internationalization (i18n)
- **📧 Advanced Alerting Rules** - Complex alerting conditions and escalation

## 🏗️ Architecture

### Data Models

The application uses SQLAlchemy with the following core models:

- **Monitor**: Configuration for each monitoring target
  - URL, method, expected responses, intervals, timeouts
  - Support for custom headers and request bodies
  - Active/inactive status management

- **MonitorCheck**: Individual check results
  - Response time, status code, success/failure
  - Error messages and response content (first 1000 chars)
  - Timestamp indexing for performance

- **Incident**: Downtime tracking
  - Automatic creation when monitors go down
  - Duration calculation and resolution tracking
  - Human-readable duration formatting

- **NotificationChannel**: Alerting configuration
  - Email, webhook, and Slack integrations
  - JSON configuration storage
  - Active/inactive channel management

### Storage Services

- **SQLite Database** - Lightweight, file-based database for development
- **File-based Logging** - Structured logging to `/logs/` directory
- **Local File Storage** - Static assets and templates served by Flask

### Technology Stack

- **Backend**: Python 3.12, Flask 2.3.3, SQLAlchemy 2.0.21
- **Frontend**: HTML5, TailwindCSS, Vanilla JavaScript, Chart.js
- **Database**: SQLite (development), easily upgradable to PostgreSQL/MySQL
- **Process Management**: Supervisor for daemon management
- **Monitoring**: Background service with scheduler
- **API**: RESTful JSON API with CORS support

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip package manager
- Git (optional, for version control)

### Installation

1. **Clone the repository** (or download the source code):
```bash
git clone <repository-url>
cd webapp
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Initialize the database**:
```bash
python app.py init-db
python app.py create-sample-data
```

4. **Start the services**:
```bash
# Start both web app and monitoring service with supervisor
supervisord -c supervisord.conf

# Check service status
supervisorctl -c supervisord.conf status
```

5. **Access the application**:
   - Open http://localhost:3000 in your browser
   - API available at http://localhost:3000/api/status

### Manual Startup (Alternative)

If you prefer to run services manually:

```bash
# Terminal 1: Start web application
python app.py

# Terminal 2: Start monitoring service
python monitoring_service.py
```

## 📖 User Guide

### Adding Monitors

1. **Navigate to Dashboard** - Click "Add Monitor" button
2. **Configure Monitor**:
   - **Name**: Descriptive name for your service
   - **URL**: Full URL to monitor (https://example.com)
   - **Type**: HTTP/HTTPS, Ping, or Port monitoring
   - **Method**: GET, POST, PUT, HEAD (for HTTP monitors)
   - **Expected Status**: HTTP status code (usually 200)
   - **Expected Text**: Optional text that should be in response
   - **Headers**: Custom HTTP headers in JSON format
   - **Body**: Request body for POST/PUT requests
3. **Set Monitoring Options**:
   - **Interval**: How often to check (30s - 1h)
   - **Timeout**: Maximum wait time (5s - 2m)
   - **Retries**: Number of retry attempts (1-10)

### Viewing Monitor Status

- **Dashboard**: Overview of all monitors with status indicators
- **Monitor Details**: Click on any monitor for detailed view including:
  - Real-time status and response times
  - Response time charts (1h, 6h, 24h, 7d)
  - Recent check history
  - Incident timeline
  - Uptime statistics

### Setting Up Notifications

1. **Go to Settings** - Navigate to Settings page
2. **Add Notification Channel**:
   - **Email**: Configure SMTP server and recipient
   - **Webhook**: Set up REST API endpoint
   - **Slack**: Use Slack webhook URL
3. **Test Notifications** - Verify delivery before enabling

### Managing Incidents

- **Automatic Detection**: Incidents are created automatically when monitors fail
- **Resolution Tracking**: Incidents are resolved when monitors recover
- **View History**: See all past incidents with duration and error details
- **Duration Formatting**: Human-readable format (e.g., "2h 30m", "45s")

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Flask Configuration
FLASK_ENV=development
SECRET_KEY=your-secret-key-change-in-production

# Database
DATABASE_URL=sqlite:///monitoring.db

# Monitoring Settings
DEFAULT_CHECK_INTERVAL=60
MAX_RESPONSE_TIME=30
KEEP_HISTORY_DAYS=30
ITEMS_PER_PAGE=20

# Email Configuration (optional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=monitor@yourcompany.com
```

### Supervisor Configuration

The `supervisord.conf` file manages both services:

- **webapp**: Flask web application on port 3000
- **monitoring_service**: Background monitoring daemon
- **Logging**: Automatic log rotation and management
- **Auto-restart**: Services restart automatically on failure

### Notification Examples

**Email Configuration**:
```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "username": "alerts@yourcompany.com",
  "password": "app-specific-password",
  "from_email": "monitor@yourcompany.com",
  "to_email": "admin@yourcompany.com",
  "use_tls": true
}
```

**Webhook Configuration**:
```json
{
  "url": "https://hooks.slack.com/your-webhook-url",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer your-token"
  },
  "timeout": 30
}
```

**Slack Configuration**:
```json
{
  "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
}
```

## 📊 API Documentation

### Authentication

Currently, no authentication is required. API endpoints are publicly accessible.

### Endpoints

**System Status**:
```
GET /api/status
```
Returns overall system status and statistics.

**All Monitors**:
```
GET /api/monitors
```
Returns list of all active monitors with current status.

**Monitor Details**:
```
GET /api/monitors/{id}
```
Returns detailed information for a specific monitor.

**Monitor History**:
```
GET /api/monitors/{id}/checks?hours=24
```
Returns check history for a monitor (last N hours).

**Recent Incidents**:
```
GET /api/incidents?limit=50
```
Returns list of recent incidents.

### Response Format

All API responses use JSON format:
```json
{
  "status": "success|error",
  "data": {...},
  "message": "Optional message",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## 🔨 Deployment

### Development Deployment

The application is currently configured for development with:
- Debug mode enabled
- SQLite database
- Local file storage
- Console logging

### Production Recommendations

For production deployment, consider:

1. **Database**: Upgrade to PostgreSQL or MySQL
2. **Web Server**: Use Gunicorn + Nginx
3. **Environment**: Set `FLASK_ENV=production`
4. **Security**: Configure proper SECRET_KEY
5. **HTTPS**: Enable SSL/TLS certificates
6. **Monitoring**: Set up external monitoring for the monitor
7. **Backup**: Regular database and configuration backups

### Docker Deployment (Future)

A Dockerfile and docker-compose.yml will be provided for easy containerized deployment.

## 🤝 Contributing

This is an open-source project. Contributions are welcome!

### Development Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run tests: `python -m pytest tests/`
4. Start development server: `python app.py`

### Code Style

- Follow PEP 8 Python style guide
- Use meaningful variable and function names
- Add docstrings for all classes and functions
- Include type hints where appropriate

## 📄 License

This project is open-source. Feel free to use, modify, and distribute as needed.

## 🆘 Support

### Common Issues

**Services won't start**:
- Check logs: `tail -f logs/webapp.log logs/monitoring_service.log`
- Verify dependencies: `pip list`
- Check ports: `netstat -tlnp | grep 3000`

**Database errors**:
- Recreate database: `rm monitoring.db && python app.py init-db`
- Check permissions on database file

**Notifications not working**:
- Test SMTP settings with telnet
- Verify webhook URLs are accessible
- Check notification channel configuration

### Getting Help

For issues and questions:
1. Check the logs in `/logs/` directory
2. Verify configuration in `.env` file
3. Test individual components manually
4. Review the error messages in the web interface

## 📈 Roadmap

### Next Steps for Development

1. **User Authentication**: Implement login system with role-based access
2. **Advanced Charts**: Add trend analysis and comparative charts
3. **Public Status Pages**: Create public-facing status pages
4. **Mobile App**: Develop React Native mobile application
5. **Plugin System**: Create extensible architecture for custom monitors
6. **Cloud Deployment**: Add support for major cloud providers

### Recommended Extensions

- **Database Optimization**: Connection pooling and query optimization
- **Caching Layer**: Redis for improved performance
- **Load Balancing**: Support for multiple monitor instances
- **Advanced Alerting**: Complex rules and escalation policies
- **Integration APIs**: Support for popular DevOps tools

---

**Last Updated**: 2024-08-23  
**Version**: 1.0.0  
**Tech Stack**: Python + Flask + SQLAlchemy + TailwindCSS  
**Status**: ✅ Production Ready for Basic Monitoring Needs