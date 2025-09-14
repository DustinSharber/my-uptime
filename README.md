# Python Monitor

A comprehensive Python-based uptime monitoring system similar to UptimeKuma, built with Flask and modern web technologies.

## 🚀 Quick Start

### Prerequisites

- Docker

### Docker Deployment

This project can be deployed using Docker.

**Build the Docker Image**

```bash
docker build -t my-uptime .
```

**Run the Docker Container**

```bash
docker run -d -p 5000:5000 --name my-uptime-container my-uptime
```

This will run the application in detached mode and map port 5000 on the host to port 5000 in the container.

You can then access the application at `http://localhost:5000`.
