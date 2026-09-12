FROM node:20-bookworm-slim

LABEL maintainer="VaporFetch Contributors" \
      description="SteamCMD game download utility with Web UI and NAS PUID/PGID storage integration"

ENV DEBIAN_FRONTEND=noninteractive \
    STEAMCMD_DIR=/usr/local/steamcmd \
    STEAMCMD_PATH=/usr/local/steamcmd/steamcmd.sh \
    PATH="/usr/local/steamcmd:${PATH}" \
    PUID=1000 \
    PGID=1000 \
    UMASK=002 \
    PORT=8080 \
    DOWNLOADS_DIR=/downloads \
    CONFIG_DIR=/config

# 1. Enable 32-bit architecture and install SteamCMD runtime dependencies
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gosu \
        libc6:i386 \
        libstdc++6:i386 \
        lib32gcc-s1 \
        lib32stdc++6 \
        libsdl2-2.0-0:i386 \
        locales \
        procps && \
    locale-gen en_US.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

# 2. Download and set up SteamCMD
# Use a wrapper script instead of a symlink so dirname $0 evaluates to /usr/local/steamcmd
RUN mkdir -p ${STEAMCMD_DIR} && \
    curl -fsSL 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz' | tar -xz -C ${STEAMCMD_DIR} && \
    chmod +x ${STEAMCMD_DIR}/steamcmd.sh && \
    printf '#!/bin/sh\nexec /usr/local/steamcmd/steamcmd.sh "$@"\n' > /usr/local/bin/steamcmd && \
    chmod +x /usr/local/bin/steamcmd && \
    chmod -R 777 ${STEAMCMD_DIR}

# 3. Bootstrap SteamCMD during build so container startup doesn't stall on downloading core engine
RUN /usr/local/steamcmd/steamcmd.sh +quit || true && \
    chmod -R 777 ${STEAMCMD_DIR}

# 4. Prepare Application Directory
WORKDIR /app

# Copy dependency manifests and install dependencies
COPY package.json ./
RUN npm install --omit=dev

# Copy application files
COPY server.js ./
COPY src/ ./src/
COPY public/ ./public/
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && \
    mkdir -p /config /downloads

# Persistent configuration and target NAS download directory
VOLUME ["/config", "/downloads"]

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
CMD ["node", "server.js"]

