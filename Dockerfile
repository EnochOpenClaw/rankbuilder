FROM python:3.11-slim

WORKDIR /app

# Install system deps + Playwright browser dependencies + himalaya email CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron curl git wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 libx11-xcb1 \
    libgraphite2-3 \
    && rm -rf /var/lib/apt/lists/*

# Install himalaya email CLI
RUN curl -sSL https://raw.githubusercontent.com/pimalaya/himalaya/master/install.sh | sh -s -- -p /usr/local/bin

# Copy requirements first (for layer caching)
COPY requirements.txt* ./

# Install Python deps + Playwright with Chromium
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null \
    || pip install --no-cache-dir \
        requests beautifulsoup4 lxml python-dotenv schedule imapclient html2text

RUN pip install --no-cache-dir playwright && \
    playwright install chromium && \
    playwright install-deps

# Copy application (exclude git, state, secrets)
COPY . .

# Health check server
COPY run_mode.sh /app/run_mode.sh
RUN chmod +x /app/run_mode.sh

# Volume mount point for persistent data
VOLUME ["/app/state"]

# Entrypoint
ENTRYPOINT ["python", "docker-healthcheck.py"]
