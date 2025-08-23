# Python Monitor

A comprehensive uptime monitoring solution similar to UptimeKuma, built entirely in Python with Flask.

## 🚀 Live Demo

**Production URL**: https://3000-ii491u3e7hez8z99xedjf-6532622b.e2b.dev
**API Endpoint**: https://3000-ii491u3e7hez8z99xedjf-6532622b.e2b.dev/api/status

## 📋 Project Overview

Python Monitor is a full-featured uptime monitoring application that tracks the availability and performance of websites, APIs, and services. It provides real-time monitoring, incident tracking, and a beautiful web dashboard.

### ✨ Key Features

- **Real-time Monitoring**: HTTP/HTTPS, Ping, and Port connectivity checks
- **Beautiful Dashboard**: Modern, responsive web interface with TailwindCSS
- **Incident Tracking**: Automatic detection and tracking of downtime incidents
- **Performance Metrics**: Response time monitoring and uptime statistics
- **Flexible Configuration**: Customizable check intervals, timeouts, and retry logic
- **API Access**: RESTful API for programmatic access to monitoring data
- **Background Service**: Dedicated monitoring service with supervisor management
- **Data Retention**: Configurable data retention and automatic cleanup

### 🎯 Currently Completed Features

1. ✅ **Web Dashboard**: Complete dashboard showing monitor status, uptime statistics
2. ✅ **Monitor Management**: Add, edit, delete, pause/resume monitors
3. ✅ **HTTP/HTTPS Monitoring**: Full support with custom headers, methods, expected responses
4. ✅ **Ping Monitoring**: Network connectivity testing
5. ✅ **Port Monitoring**: TCP port connectivity checks
6. ✅ **Incident Management**: Automatic incident creation and resolution
7. ✅ **API Endpoints**: Complete REST API for all functionality
8. ✅ **Background Service**: Continuous monitoring with supervisor
9. ✅ **Database Models**: SQLite with SQLAlchemy ORM
10. ✅ **Responsive UI**: Mobile-friendly interface with real-time updates

### 🔧 Functional Entry URIs

#### Web Interface
- `/` - Main dashboard
- `/monitors` - Monitor management page
- `/monitors/new` - Add new monitor
- `/monitors/{id}` - Monitor details and history
- `/monitors/{id}/edit` - Edit monitor configuration
- `/incidents` - Incident history
- `/settings` - Application settings

#### API Endpoints
- `GET /api/status` - Overall system status
- `GET /api/monitors` - List all monitors
- `GET /api/monitors/{id}` - Monitor details
- `GET /api/monitors/{id}/checks` - Monitor check history
- `GET /api/incidents` - Recent incidents

### 📊 Data Architecture

**Primary Storage**: SQLite database with the following models:

1. **Monitor**: Monitor configurations
   - Basic info (name, URL, type)
   - HTTP settings (method, headers, expected response)
   - Monitoring settings (interval, timeout, retries)

2. **MonitorCheck**: Individual check results
   - Status (up/down), response time, status code
   - Error messages and response text
   - Timestamps for historical tracking

3. **Incident**: Downtime incident tracking
   - Start/end times, duration
   - Error messages and resolution status

4. **NotificationChannel**: Alert configurations (extensible)
   - Email, webhook, and other notification types

**Storage Services Used**: 
- SQLite for relational data
- File system for logs
- In-memory caching for real-time updates

### 👥 User Guide

1. **Getting Started**:
   - Visit the dashboard to see overview of all monitors
   - Click "Add Monitor" to create your first monitoring endpoint
   - Configure URL, check interval, and expected responses

2. **Monitor Management**:
   - View detailed statistics and response time graphs
   - Edit monitor settings anytime
   - Pause/resume monitoring as needed
   - Delete monitors when no longer needed

3. **Incident Tracking**:
   - Automatic incident detection when services go down
   - View incident history and duration
   - Incidents automatically resolve when service comes back up

4. **API Usage**:
   - Use REST API for programmatic access
   - Integrate with external systems
   - Build custom dashboards or alerts

### 🛠 Features Not Yet Implemented

1. **Alerting System**: Email and webhook notifications (framework ready)
2. **User Authentication**: Multi-user support with role-based access
3. **Advanced Monitoring**: SSL certificate expiry, keyword monitoring
4. **Status Pages**: Public status pages for services
5. **Custom Dashboards**: User-configurable dashboard layouts
6. **Data Export**: CSV/JSON export functionality
7. **Integrations**: Slack, Discord, PagerDuty integrations

### 📈 Recommended Next Steps

1. **Implement Notifications**: Add email/webhook alerting for incidents
2. **Add Authentication**: User management and secure access
3. **Status Pages**: Public status pages for customer-facing services
4. **Mobile App**: Native mobile application for monitoring on-the-go
5. **Cloud Deployment**: Production deployment guide and Docker support

## 🚀 Deployment

**Platform**: Python/Flask with Supervisor process management
**Status**: ✅ Active and Running
**Tech Stack**: 
- Backend: Flask + SQLAlchemy
- Frontend: TailwindCSS + Vanilla JavaScript
- Database: SQLite
- Process Management: Supervisor
- Charts: Chart.js

**Last Updated**: August 23, 2025

## 🏗 Installation

1. **Clone and Setup**:
   ```bash
   git clone <repository-url>
   cd webapp
   pip install -r requirements.txt
   ```

2. **Initialize Database**:
   ```bash
   python app.py init-db
   python app.py create-sample-data
   ```

3. **Start Services**:
   ```bash
   supervisord -c supervisord.conf
   ```

4. **Access Application**: 
   - Web Interface: http://localhost:3000
   - API: http://localhost:3000/api/status

## 📁 Project Structure

```
webapp/
├── app/                    # Flask application
│   ├── __init__.py        # App factory
│   ├── models.py          # Database models
│   ├── routes.py          # Web routes
│   ├── api.py            # API endpoints
│   └── monitoring.py      # Background monitoring service
├── templates/             # HTML templates
├── static/               # CSS, JavaScript, images
├── config/               # Configuration files
├── logs/                # Application logs
├── supervisord.conf     # Process management
├── requirements.txt     # Python dependencies
└── app.py              # Main application entry point
```

## 🔧 Configuration

Edit `.env` file to customize:
- Database settings
- Check intervals and timeouts
- Data retention policies
- Email/notification settings

## 🤝 Contributing

This is an open-source monitoring solution. Contributions welcome for:
- New monitoring types
- Notification channels
- UI improvements
- Performance optimizations

---

**Built with ❤️ in Python** | **Ready for production use**