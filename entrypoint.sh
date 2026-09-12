#!/usr/bin/env bash
set -e

# VaporFetch Docker Entrypoint
# Dynamically configures non-root user/group based on PUID and PGID
# to ensure zero-permission issues when writing to NAS shares (SMB/NFS/CIFS).

PUID=${PUID:-1000}
PGID=${PGID:-1000}
UMASK=${UMASK:-002}

echo "===================================================="
echo "  VaporFetch - SteamCMD NAS Downloader"
echo "  Target User UID (PUID)  : ${PUID}"
echo "  Target Group GID (PGID) : ${PGID}"
echo "  File Creation Mask      : ${UMASK}"
echo "===================================================="

# Apply umask so new files created are group-writable for NAS users
umask "${UMASK}"

# 1. Setup Group
if getent group "${PGID}" >/dev/null 2>&1; then
    GROUP_NAME=$(getent group "${PGID}" | cut -d: -f1)
    echo "[VaporFetch] Reusing existing group '${GROUP_NAME}' with GID ${PGID}"
else
    GROUP_NAME="steam"
    echo "[VaporFetch] Creating group '${GROUP_NAME}' with GID ${PGID}"
    groupadd -g "${PGID}" "${GROUP_NAME}"
fi

# 2. Setup User
if getent passwd "${PUID}" >/dev/null 2>&1; then
    USER_NAME=$(getent passwd "${PUID}" | cut -d: -f1)
    echo "[VaporFetch] Reusing existing user '${USER_NAME}' with UID ${PUID}"
    usermod -g "${GROUP_NAME}" "${USER_NAME}" 2>/dev/null || true
else
    USER_NAME="steam"
    echo "[VaporFetch] Creating user '${USER_NAME}' with UID ${PUID} and GID ${PGID}"
    useradd -u "${PUID}" -g "${GROUP_NAME}" -d /config -s /bin/bash "${USER_NAME}"
fi

# 3. Ensure Directories and Home Environment
export HOME=/config
mkdir -p /config /downloads /config/Steam /config/.steam /config/.local

# Symlink standard SteamCMD directories to /config to persist credentials & Guard tokens
ln -sf /config/.steam /root/.steam 2>/dev/null || true
ln -sf /config/Steam /root/Steam 2>/dev/null || true

# 4. Permissions on /config
chown -R "${PUID}:${PGID}" /config /app 2>/dev/null || true

# 5. Check /downloads permissions
if [ -d "/downloads" ]; then
    chown "${PUID}:${PGID}" /downloads 2>/dev/null || true
    # Verify write access as the target PUID:PGID
    if ! gosu "${PUID}:${PGID}" touch /downloads/.vaporfetch_perm_check 2>/dev/null; then
        echo "[WARNING] Target user (${PUID}:${PGID}) cannot write to /downloads!"
        echo "          Please verify the permissions or PUID/PGID of your mounted NAS volume."
    else
        rm -f /downloads/.vaporfetch_perm_check
        echo "[VaporFetch] NAS directory /downloads is writable by UID ${PUID}:GID ${PGID}."
    fi
fi

echo "[VaporFetch] Dropping privileges to ${USER_NAME} (${PUID}:${PGID}) and starting application..."
exec gosu "${PUID}:${PGID}" "$@"

