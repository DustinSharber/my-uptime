# Use Ubuntu 20.04 for better compatibility with older GLIBC systems
FROM ubuntu:20.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set timezone to ensure consistent time handling
ENV TZ=UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python 3.11 and system dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3.11-distutils \
    python3-pip \
    build-essential \
    wget \
    gnupg2 \
    iputils-ping \
    net-tools \
    dnsutils \
    telnet \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Create symlinks for python3.11
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.11 /usr/bin/python

# Install pip for Python 3.11
RUN wget https://bootstrap.pypa.io/get-pip.py && \
    python3.11 get-pip.py && \
    rm get-pip.py

# Install Wine for Windows cross-compilation (using Ubuntu's Wine)
RUN apt-get update && apt-get install -y \
    wine \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install pyinstaller for agent building
RUN pip install pyinstaller

# Copy the rest of the application's code into the container at /app
COPY . .

# Create necessary directories and set proper permissions
RUN mkdir -p /app/agent/dist /app/data /app/logs /app/instance && \
    chmod +x /app/agent/build_linux.sh && \
    ls -la /app/agent/dist/ && \
    echo "Pre-built agents available:" && \
    find /app/agent/dist -name "*.exe" -o -name "*.tar.gz" -o -name "uptime_agent" | head -10 && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Run wsgi.py when the container launches
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "120", "wsgi:app"]

