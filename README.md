# VaporFetch 🎮

[![Docker Image](https://img.shields.io/badge/docker-ready-blue.svg)](https://github.com/theretrogeekyt-dev/VaporFetch/pkgs/container/vaporfetch)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![SteamCMD](https://img.shields.io/badge/Engine-SteamCMD-black.svg)](https://developer.valvesoftware.com/wiki/SteamCMD)

A lightweight, containerized Steam game download utility designed to download Steam games and dedicated servers directly to **Network Attached Storage (NAS)** devices (Synology, Unraid, TrueNAS, QNAP, or Linux SMB/NFS mounts).

Built with **SteamCMD** under the hood, **VaporFetch** features a sleek, responsive Web UI with real-time log streaming, progress tracking, dynamic NAS permission management (`PUID`/`PGID`), and interactive Steam Guard 2FA support.

**No source code needed on your NAS!** Deploy instantly via pre-built image from GitHub Container Registry (`ghcr.io/theretrogeekyt-dev/vaporfetch:latest`).

---

## 🚀 Traditional NAS Deployment (No Source Code Required)

You do **not** need to clone this repository or copy any application source files to your NAS. Use any of the traditional Docker methods below:

### Option A: Single `docker run` Command (Fastest)

Run this command directly in your NAS SSH terminal:

```bash
docker run -d \
  --name vaporfetch \
  --restart unless-stopped \
  -p 8080:8080 \
  -e PUID=1000 \
  -e PGID=1000 \
  -e UMASK=002 \
  -v /mnt/nas/games:/downloads \
  -v /path/to/appdata/vaporfetch:/config \
  ghcr.io/theretrogeekyt-dev/vaporfetch:latest
```

*(Replace `/mnt/nas/games` with your actual game folder path on your NAS, and `/path/to/appdata/vaporfetch` with where you want to store Steam credentials).*

---

### Option B: Standalone `docker-compose.yml`

Create a single file named `docker-compose.yml` anywhere on your NAS (no other files needed):

```yaml
version: '3.8'

services:
  vaporfetch:
    image: ghcr.io/theretrogeekyt-dev/vaporfetch:latest
    container_name: vaporfetch
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      # Match the user on your NAS (run `id $USER` to check)
      - PUID=1000
      - PGID=1000
      - UMASK=002
      - PORT=8080
      # Optional: Default credentials (or enter on-demand in the Web UI)
      - STEAM_USERNAME=
      - STEAM_PASSWORD=
    volumes:
      # 1. Map your NAS games folder to /downloads
      - /mnt/nas/games:/downloads
      # 2. Map persistent config (holds Steam Guard tokens and session cache)
      - /path/to/appdata/vaporfetch/config:/config
```

Then start the container:
```bash
docker compose up -d
```

---

### Option C: Synology Container Manager / Portainer / Unraid GUI

You can deploy directly through your NAS web interface without touching the command line:

1. **Image Name**: `ghcr.io/theretrogeekyt-dev/vaporfetch:latest`
2. **Port Forwarding**: Local Port `8080` ➡️ Container Port `8080`
3. **Volume Bindings**:
   - Local NAS Games folder (e.g. `/volume1/games` or `/mnt/user/games`) ➡️ `/downloads`
   - AppData folder (e.g. `/volume1/docker/vaporfetch/config`) ➡️ `/config`
4. **Environment Variables**:
   - `PUID`: Your NAS user ID (e.g., `1026` for Synology, `99` for Unraid, `1000` for Linux)
   - `PGID`: Your NAS group ID (e.g., `100` for Synology/Unraid, `1000` for Linux)
   - `UMASK`: `002`

---

## 🌐 Accessing the Web UI

Once running, open your web browser:
```
http://<your-nas-ip>:8080
```

---

## 🗄️ NAS Permission Mapping (`PUID` & `PGID`)

Standard Docker containers run as `root` (UID 0). When a container creates files on an SMB, CIFS, or NFS share, standard users are blocked from editing or deleting them.

**VaporFetch** dynamically matches the permissions of your NAS user:

| Platform | Recommended `PUID` | Recommended `PGID` | Where to find it |
| :--- | :--- | :--- | :--- |
| **Synology DSM** | `1026` | `100` | SSH into DSM and run `id` on your admin user |
| **Unraid** | `99` | `100` | Standard Unraid `nobody:users` ID |
| **TrueNAS** | `1000` | `1000` | Owner UID/GID of your dataset in TrueNAS UI |
| **Linux (Ubuntu/Debian)**| `1000` | `1000` | Run `id -u` and `id -g` in your terminal |

---

## ✨ Features

- **🚀 SteamCMD Engine**: Automatic installation of SteamCMD with all 32-bit Debian dependencies (`i386`) pre-configured.
- **💾 Direct NAS Writing**: Files are saved directly with proper permissions to eliminate NAS access issues.
- **🖥️ Modern Web UI**:
  - **Live Steam Info**: Instant AppID lookup queries the Steam Store API for game title and cover art.
  - **Quick-Select Presets**: One-click configuration for popular dedicated servers (Palworld, CS2, Valheim, Enshrouded, Rust, Ark, Project Zomboid, etc.).
  - **Live Progress & Speed**: Real-time progress bar, transfer rate (MB/s), downloaded size, and validation stage via Server-Sent Events (SSE).
  - **Integrated Terminal Console**: Live streaming stdout/stderr with ANSI colors, auto-scroll, and copy-to-clipboard.
- **🔐 Flexible Authentication**:
  - **Anonymous Mode**: Fast downloads for free dedicated game servers.
  - **Steam Account Mode**: Download owned games with Steam credentials.
  - **Steam Guard 2FA Support**: Interactive pop-up prompt in the Web UI to submit two-factor authentication codes when requested by SteamCMD.
- **⚙️ Advanced Controls**:
  - **Force Platform Override**: Toggle `+@sSteamCmdForcePlatformType windows` to download Windows-specific server/game binaries directly to your Linux NAS.
  - **File Validation**: Optional `validate` flag to verify game integrity.
  - **Beta Branches**: Specify beta branches and branch passwords.

---

## 🎮 Popular Dedicated Server AppIDs

| Game Server | AppID | Anonymous Download | Recommended Platform |
| :--- | :--- | :--- | :--- |
| **Palworld Dedicated Server** | `2394010` | ✅ Yes | Windows / Linux |
| **Counter-Strike 2 Dedicated Server** | `730` | ✅ Yes | Linux |
| **Valheim Dedicated Server** | `896660` | ✅ Yes | Linux |
| **Enshrouded Dedicated Server** | `2278520` | ✅ Yes | Windows |
| **Rust Dedicated Server** | `258550` | ✅ Yes | Linux |
| **Ark: Survival Ascended Server** | `2430930` | ✅ Yes | Windows |
| **Project Zomboid Dedicated Server** | `380870` | ✅ Yes | Linux |
| **Sons of the Forest Server** | `2465200` | ✅ Yes | Windows |
| **7 Days to Die Dedicated Server** | `294420` | ✅ Yes | Linux |
| **Garry's Mod Dedicated Server** | `4020` | ✅ Yes | Linux |
| **Team Fortress 2 Server** | `232250` | ✅ Yes | Linux |
| **Left 4 Dead 2 Dedicated Server** | `222860` | ✅ Yes | Linux |
| **Satisfactory Dedicated Server** | `1690800` | ✅ Yes | Linux |

*All of these are available as 1-click presets in the Web UI.*

---

## 🔄 Updating the Container

Since the container runs from a pre-built image, updating is seamless:

```bash
docker compose pull
docker compose up -d
```

Or for `docker run`:
```bash
docker pull ghcr.io/theretrogeekyt-dev/vaporfetch:latest
docker stop vaporfetch && docker rm vaporfetch
# Re-run your docker run command
```

---

## 🛠️ Local Development & Building from Source

If you want to build the container image locally from source:

```bash
git clone https://github.com/theretrogeekyt-dev/VaporFetch.git
cd VaporFetch
docker build -t vaporfetch:latest .
```

---

## 📄 License

MIT License. Feel free to use, modify, and distribute.
