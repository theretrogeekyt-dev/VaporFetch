#!/usr/bin/env bash
set -e

# VaporFetch Docker Entrypoint Script
# Handles permissions, persistent Steam storage, and clean process lifecycle.

echo "======================================================="
echo "   Starting VaporFetch Container"
echo "======================================================="

# 1. Apply umask so downloaded game files are accessible on host (SMB, File Station)
UMASK_VAL="${UMASK:-000}"
umask "${UMASK_VAL}"
echo "[VaporFetch] Applied umask: ${UMASK_VAL}"

# 2. Configure base directories
DATA_DIR="${VAPORFETCH_DATA_DIR:-/data}"
DOWNLOADS_DIR="${VAPORFETCH_DOWNLOADS_DIR:-/downloads}"
STEAM_DIR="${DATA_DIR}/steam"

mkdir -p "${DATA_DIR}" "${DOWNLOADS_DIR}"
mkdir -p "${STEAM_DIR}/.steam/steam/config"
mkdir -p "${STEAM_DIR}/Steam/config"
mkdir -p "${STEAM_DIR}/.local/share/Steam"
mkdir -p "${STEAM_DIR}/logs"
mkdir -p "${STEAM_DIR}/.steam/sdk32"
mkdir -p "${STEAM_DIR}/.steam/sdk64"

# 3. Migrate legacy storage directories if present from earlier versions
if [ -d "${DATA_DIR}/steam_home" ] && [ ! -d "${STEAM_DIR}/Steam/config/loginusers.vdf" ]; then
    echo "[VaporFetch] Migrating legacy steam_home data..."
    cp -rn "${DATA_DIR}/steam_home/"* "${STEAM_DIR}/Steam/" 2>/dev/null || true
fi
if [ -d "${DATA_DIR}/steam_root" ] && [ ! -d "${STEAM_DIR}/.steam/steam/config/config.vdf" ]; then
    echo "[VaporFetch] Migrating legacy steam_root data..."
    cp -rn "${DATA_DIR}/steam_root/"* "${STEAM_DIR}/.steam/" 2>/dev/null || true
fi

# 4. Wire system symlinks to point directly into persistent /data/steam
mkdir -p /root/.local/share
rm -rf /root/.steam /root/Steam /root/.local/share/Steam 2>/dev/null || true
ln -sfn "${STEAM_DIR}/.steam" /root/.steam || true
ln -sfn "${STEAM_DIR}/Steam" /root/Steam || true
ln -sfn "${STEAM_DIR}/.local/share/Steam" /root/.local/share/Steam || true

# 5. Wire steamclient.so so SteamAPI never logs missing libraries
if [ -f /opt/steamcmd/linux32/steamclient.so ]; then
    ln -sf /opt/steamcmd/linux32/steamclient.so "${STEAM_DIR}/.steam/sdk32/steamclient.so" || true
fi
if [ -f /opt/steamcmd/linux64/steamclient.so ]; then
    ln -sf /opt/steamcmd/linux64/steamclient.so "${STEAM_DIR}/.steam/sdk64/steamclient.so" || true
fi

# 6. Pre-seed Steam update packages to avoid initial download delay
if [ -d /opt/steamcmd/package ] && [ ! -d "${STEAM_DIR}/Steam/package" ]; then
    cp -r /opt/steamcmd/package "${STEAM_DIR}/Steam/package" 2>/dev/null || true
fi

export HOME="${STEAM_DIR}"
export STEAMCMD_PATH="${STEAMCMD_PATH:-/opt/steamcmd/steamcmd.sh}"
export VAPORFETCH_DATA_DIR="${DATA_DIR}"
export VAPORFETCH_DOWNLOADS_DIR="${DOWNLOADS_DIR}"

# 7. User & Group ID (PUID / PGID) Handling
PUID="${PUID:-0}"
PGID="${PGID:-0}"

if [ "${PUID}" -ne 0 ] && [ "${PGID}" -ne 0 ]; then
    echo "[VaporFetch] Configuring user permissions (PUID=${PUID}, PGID=${PGID})"
    # Check if group GID already exists
    TARGET_GROUP=$(getent group "${PGID}" | cut -d: -f1 || true)
    if [ -z "${TARGET_GROUP}" ]; then
        groupadd -g "${PGID}" vaporfetch 2>/dev/null || true
    fi
    # Check if user UID already exists
    TARGET_USER=$(getent passwd "${PUID}" | cut -d: -f1 || true)
    if [ -z "${TARGET_USER}" ]; then
        useradd -u "${PUID}" -g "${PGID}" -d "${STEAM_DIR}" -M -s /bin/bash vaporfetch 2>/dev/null || true
    fi

    # Ensure ownership of /data and /downloads
    chown "${PUID}:${PGID}" "${DATA_DIR}" "${DOWNLOADS_DIR}" 2>/dev/null || true
    chown -R "${PUID}:${PGID}" "${STEAM_DIR}" 2>/dev/null || true

    # Hand off execution cleanly via gosu with tini
    GOSU_BIN=$(command -v gosu || echo "/usr/sbin/gosu")
    exec "${GOSU_BIN}" "${PUID}:${PGID}" /usr/bin/tini -- "$@"
else
    # Running as root (default for Docker)
    echo "[VaporFetch] Running with container root privileges (umask=${UMASK_VAL})"
    exec /usr/bin/tini -- "$@"
fi
