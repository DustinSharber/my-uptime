# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install system dependencies needed for building agents
RUN apt-get update && apt-get install -y \
    build-essential \
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
