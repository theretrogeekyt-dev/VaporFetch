# syntax=docker/dockerfile:1
FROM --platform=linux/amd64 debian:bookworm-slim

LABEL maintainer="VaporFetch" \
      description="Docker-based Steam game downloader and backup program using SteamCMD"

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    PYTHONUNBUFFERED=1 \
    STEAMCMD_PATH=/opt/steamcmd/steamcmd.sh \
    VAPORFETCH_DATA_DIR=/data \
    VAPORFETCH_DOWNLOADS_DIR=/downloads

# 1. Install prerequisites, 32-bit architecture libraries for SteamCMD, and Python
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        locales \
        lib32gcc-s1 \
        lib32stdc++6 \
        python3 \
        python3-pip \
        python3-venv \
        tini && \
    sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. Download and install SteamCMD
RUN mkdir -p /opt/steamcmd && \
    curl -fsSL 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz' | tar -vxz -C /opt/steamcmd && \
    printf '#!/bin/sh\ncd /opt/steamcmd && exec ./steamcmd.sh "$@"\n' > /usr/local/bin/steamcmd && \
    chmod +x /usr/local/bin/steamcmd && \
    # Bootstrap SteamCMD binaries during build
    /opt/steamcmd/steamcmd.sh +quit || true

# 3. Create app directory and install Python dependencies
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

# 4. Copy VaporFetch application source
COPY vaporfetch /app/vaporfetch

# 5. Create storage and persistent data directories
RUN mkdir -p /data /downloads /root/.steam /root/.local/share/Steam

# Expose Web UI port
EXPOSE 8080

VOLUME ["/data", "/downloads"]

# Use tini for proper signal handling in Docker
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "-m", "vaporfetch"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]

