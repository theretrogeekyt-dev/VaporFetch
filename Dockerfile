FROM debian:bookworm-slim

# Prevent interactive debconf prompts
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PUID=1000 \
    PGID=1000 \
    UMASK=002 \
    HOME=/home/steam \
    DOWNLOAD_DIR=/downloads \
    DATA_DIR=/app/data \
    STEAMCMD_PATH=/steamcmd/steamcmd.sh \
    PATH="/opt/venv/bin:$PATH"

# Install system dependencies, 32-bit libs for SteamCMD, and Python 3
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       tar \
       gosu \
       python3 \
       python3-pip \
       python3-venv \
       lib32gcc-s1 \
       lib32stdc++6 \
       libc6:i386 \
       libstdc++6:i386 \
       libcurl4:i386 \
       libbz2-1.0:i386 \
       locales \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# Install SteamCMD directly from Valve and configure permissions
RUN mkdir -p /steamcmd \
    && curl -fsSL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" -o /tmp/steamcmd.tar.gz \
    && tar -zxf /tmp/steamcmd.tar.gz -C /steamcmd \
    && rm /tmp/steamcmd.tar.gz \
    && mkdir -p /usr/games \
    && ln -sf /steamcmd/steamcmd.sh /usr/games/steamcmd \
    && mkdir -p /home/steam

# Pre-populate and initialize SteamCMD during build so all runtime binaries exist
RUN /steamcmd/steamcmd.sh +quit || true

# Set up Python virtual environment
RUN python3 -m venv /opt/venv

# Install Python dependencies
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Build arguments for version and commit tracking
ARG APP_COMMIT_SHA=dev
ARG APP_VERSION=1.0.0
ENV APP_COMMIT_SHA=${APP_COMMIT_SHA}
ENV APP_VERSION=${APP_VERSION}

# Copy application source code and entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
COPY app /app/app

# Define default volumes
VOLUME ["/downloads", "/app/data"]

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl --fail --silent http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "5"]
