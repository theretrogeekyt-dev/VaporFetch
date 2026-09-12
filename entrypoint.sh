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

# Prepare persistent Steam cache directories inside /app/data
mkdir -p /app/data/steam_home
mkdir -p /home/steam/.steam
mkdir -p /home/steam/.local/share/Steam
mkdir -p /downloads

# Symlink persistent Steam cache if needed
chown -R "$PUID:$PGID" /app/data /home/steam /app

# Ensure /downloads is writable by the user
if [ -d "/downloads" ]; then
    chown "$PUID:$PGID" /downloads 2>/dev/null || true
fi

echo "[VaporFetch] Running as ${USER_NAME} (${PUID}:${PGID})"

# Drop privileges to PUID:PGID and run the application
exec gosu "$PUID:$PGID" "$@"

