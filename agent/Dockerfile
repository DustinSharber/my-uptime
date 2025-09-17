# Dockerfile for building the uptime agent
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app/agent

# Copy agent files
COPY requirements.txt .
COPY agent.py .
COPY build_linux.sh .

# Make build script executable
RUN chmod +x build_linux.sh

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pyinstaller

# Build the agent executable
RUN pyinstaller --onefile --name uptime_agent_linux agent.py --distpath dist

# Make the executable runnable
RUN chmod +x dist/uptime_agent_linux

# Create output directory
RUN mkdir -p /output

# Copy the built executable to output directory
RUN cp dist/uptime_agent_linux /output/

# Set the default command
CMD ["cp", "/output/uptime_agent_linux", "/app/dist/"]
