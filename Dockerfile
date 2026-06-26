FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron curl git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY requirements.txt* ./

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null \
    || pip install --no-cache-dir \
        requests \
        beautifulsoup4 \
        lxml \
        playwright \
        python-dotenv \
        schedule

# Copy application (exclude git, state, secrets)
COPY . .

# Health check server
COPY run_mode.sh /app/run_mode.sh
RUN chmod +x /app/run_mode.sh

# Volume mount point for persistent data
VOLUME ["/app/data"]

# Entrypoint
ENTRYPOINT ["python", "docker-healthcheck.py"]
