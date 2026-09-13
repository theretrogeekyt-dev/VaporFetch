#!/usr/bin/env bash
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}
UMASK=${UMASK:-002}

echo "[VaporFetch] Starting with PUID=${PUID}, PGID=${PGID}, UMASK=${UMASK}"

# Apply umask for NAS permissions (002 allows group write)
umask "$UMASK"

# Handle group
if getent group "$PGID" >/dev/null 2>&1; then
    GROUP_NAME=$(getent group "$PGID" | cut -d: -f1)
else
    GROUP_NAME="steam"
    groupadd -g "$PGID" "$GROUP_NAME"
fi

# Handle user
if getent passwd "$PUID" >/dev/null 2>&1; then
    USER_NAME=$(getent passwd "$PUID" | cut -d: -f1)
    # Ensure group matches
    usermod -g "$PGID" "$USER_NAME" >/dev/null 2>&1 || true
else
    USER_NAME="steam"
    useradd -u "$PUID" -g "$PGID" -m -d /home/steam -s /bin/bash "$USER_NAME"
fi

# Set HOME environment variable explicitly to /home/steam
export HOME="/home/steam"

# Prepare persistent Steam cache directories inside /app/data (mounted volume)
mkdir -p /app/data/steam_home/.steam
mkdir -p /app/data/steam_home/.local/share/Steam
mkdir -p /app/data/steam_home/steamcmd_config
mkdir -p /downloads

# Ensure /home/steam is symlinked directly to /app/data/steam_home so all credentials,
# config.vdf, and Steam Guard sentry files (ssfn*) persist across container updates
if [ -d "/home/steam" ] && [ ! -L "/home/steam" ]; then
    cp -rn /home/steam/. /app/data/steam_home/ 2>/dev/null || true
    rm -rf /home/steam
fi
if [ ! -L "/home/steam" ]; then
    ln -s /app/data/steam_home /home/steam
fi

# Link /steamcmd/config to persistent storage
if [ -d "/steamcmd/config" ] && [ ! -L "/steamcmd/config" ]; then
    cp -rn /steamcmd/config/. /app/data/steam_home/steamcmd_config/ 2>/dev/null || true
    rm -rf /steamcmd/config
fi
if [ ! -L "/steamcmd/config" ]; then
    ln -s /app/data/steam_home/steamcmd_config /steamcmd/config
fi

# Link any persistent sentry files (ssfn*) into /steamcmd and ~/.steam
for ssfn in /app/data/steam_home/ssfn*; do
    if [ -f "$ssfn" ]; then
        fname=$(basename "$ssfn")
        ln -sf "$ssfn" "/steamcmd/$fname" 2>/dev/null || true
        ln -sf "$ssfn" "/app/data/steam_home/.steam/$fname" 2>/dev/null || true
        mkdir -p "/app/data/steam_home/.steam/steam"
        ln -sf "$ssfn" "/app/data/steam_home/.steam/steam/$fname" 2>/dev/null || true
    fi
done

# If SteamCMD created ssfn files directly in /steamcmd, preserve them to persistent storage
for ssfn in /steamcmd/ssfn*; do
    if [ -f "$ssfn" ] && [ ! -L "$ssfn" ]; then
        cp -u "$ssfn" /app/data/steam_home/ 2>/dev/null || true
    fi
done

# Ensure /steamcmd is fully writable and executable by non-root users
chmod -R 777 /steamcmd 2>/dev/null || true
chmod -R +x /steamcmd 2>/dev/null || true

# Set ownership across data, steam_home, and app
chown -R "$PUID:$PGID" /app/data /steamcmd /app 2>/dev/null || true

# Ensure /downloads is writable by the user
if [ -d "/downloads" ]; then
    chown "$PUID:$PGID" /downloads 2>/dev/null || true
fi

echo "[VaporFetch] Running as ${USER_NAME} (${PUID}:${PGID}) with HOME=${HOME}"

# Drop privileges to PUID:PGID and run the application
exec gosu "$PUID:$PGID" env HOME=/home/steam "$@"
