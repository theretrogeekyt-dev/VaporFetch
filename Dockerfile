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
    && rm -rf /var/lib/apt/lists/*

# Install SteamCMD directly from Valve and configure permissions
RUN mkdir -p /steamcmd \
    && curl -fsSL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar -zxvf - -C /steamcmd \
    && chmod -R 777 /steamcmd \
    && chmod -R +x /steamcmd \
    && mkdir -p /usr/games \
    && ln -sf /steamcmd/steamcmd.sh /usr/games/steamcmd \
    && mkdir -p /home/steam \
    && chmod -R 777 /home/steam

# Pre-populate and initialize SteamCMD during build so all runtime binaries exist
RUN /steamcmd/steamcmd.sh +quit || true \
    && chmod -R 777 /steamcmd \
    && chmod -R +x /steamcmd

# Set up Python virtual environment
RUN python3 -m venv /opt/venv

# Install Python dependencies
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
COPY app /app/app

# Define default volumes
VOLUME ["/downloads", "/app/data"]

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
