# syntax=docker/dockerfile:1
FROM --platform=linux/amd64 debian:bookworm-slim

LABEL maintainer="VaporFetch" \
      description="Lightweight Docker container for VaporFetch Steam game downloader and backup tool"

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    PYTHONUNBUFFERED=1 \
    STEAMCMD_PATH=/opt/steamcmd/steamcmd.sh \
    VAPORFETCH_DATA_DIR=/data \
    VAPORFETCH_DOWNLOADS_DIR=/downloads \
    UMASK=000

# 1. Install prerequisites, 32-bit architecture libraries for SteamCMD, tini, gosu, and Python
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        locales \
        procps \
        lib32gcc-s1 \
        lib32stdc++6 \
        libc6-i386 \
        python3 \
        python3-pip \
        python3-venv \
        tini \
        gosu && \
    sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. Download, install, and pre-bootstrap SteamCMD
RUN mkdir -p /opt/steamcmd && \
    curl -fsSL 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz' | tar -vxz -C /opt/steamcmd && \
    printf '#!/bin/sh\ncd /opt/steamcmd && exec ./steamcmd.sh "$@"\n' > /usr/local/bin/steamcmd && \
    chmod +x /usr/local/bin/steamcmd && \
    chmod -R a+rX /opt/steamcmd && \
    # Bootstrap SteamCMD binaries during build
    /opt/steamcmd/steamcmd.sh +quit || true

# 3. Create app directory and install Python dependencies
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

# 4. Copy VaporFetch application source & entrypoint script
COPY vaporfetch /app/vaporfetch
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 5. Create storage directories
RUN mkdir -p /data /downloads

# Expose Web UI port
EXPOSE 8080

VOLUME ["/data", "/downloads"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python3", "-m", "vaporfetch", "serve", "--host", "0.0.0.0", "--port", "8080"]
