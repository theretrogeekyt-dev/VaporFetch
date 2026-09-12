# VaporFetch 🎮

[![Docker Image](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-20-green.svg)](https://nodejs.org/)
[![SteamCMD](https://img.shields.io/badge/Engine-SteamCMD-black.svg)](https://developer.valvesoftware.com/wiki/SteamCMD)

A lightweight, containerized Steam game download utility designed to download Steam games and dedicated servers directly to **Network Attached Storage (NAS)** devices (Synology, Unraid, TrueNAS, QNAP, or Linux SMB/NFS mounts).

Built with **SteamCMD** under the hood, **VaporFetch** features a sleek, responsive Web UI with real-time log streaming, progress tracking, dynamic NAS permission management (`PUID`/`PGID`), and interactive Steam Guard 2FA support.

---

## ✨ Features

- **🚀 SteamCMD Engine**: Automatic installation of SteamCMD with all 32-bit Debian dependencies (`i386`) pre-configured.
- **💾 NAS Storage Integration**: Built-in `PUID`/`PGID` permission mapping ensures downloaded files are owned by your NAS user—eliminating `root` permission conflicts on SMB/CIFS and NFS shares.
- **🖥️ Sleek Web UI**:
  - **Live Steam Info**: Instant AppID lookup queries the Steam Store API for game title and cover art.
  - **Quick-Select Presets**: One-click configuration for popular dedicated servers (Palworld, CS2, Valheim, Enshrouded, Rust, Ark, Project Zomboid, etc.).
  - **Live Progress & Speed**: Real-time progress bar, transfer rate (MB/s), downloaded size, and validation stage via Server-Sent Events (SSE).
  - **Integrated Terminal Console**: Live streaming stdout/stderr with ANSI colors, auto-scroll, and copy-to-clipboard.
- **🔐 Flexible Authentication**:
  - **Anonymous Mode**: Fast downloads for free dedicated game servers.
  - **Steam Account Mode**: Download owned games with Steam username/password.
  - **Steam Guard 2FA Support**: Interactive pop-up prompt in the Web UI to submit two-factor authentication codes when requested by SteamCMD.
- **⚙️ Advanced Controls**:
  - **Force Platform Override**: Toggle `+@sSteamCmdForcePlatformType windows` to download Windows-specific server/game binaries directly to your Linux NAS.
  - **File Validation**: Optional `validate` flag to verify game integrity.
  - **Beta Branches**: Specify beta branches and branch passwords.

---

## 🚀 Quickstart with Docker Compose

### 1. Clone the repository
```bash
git clone https://github.com/theretrogeekyt-dev/VaporFetch.git
cd VaporFetch
```

### 2. Configure `docker-compose.yml`
Edit `docker-compose.yml` to point `/downloads` to your NAS share and set your user permissions:

```yaml
version: '3.8'

services:
  vaporfetch:
    image: vaporfetch:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: vaporfetch
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      # PUID and PGID of the user on your NAS (run `id` on host)
      - PUID=1000
      - PGID=1000
      - UMASK=002
      - PORT=8080
      # Optional default Steam account (leave blank if entering via Web UI)
      - STEAM_USERNAME=
      - STEAM_PASSWORD=
    volumes:
      # Map your NAS share here:
      - /mnt/nas/games:/downloads
      # Persistent config (holds Steam Guard tokens and download history):
      - ./config:/config
```

### 3. Launch the container
```bash
docker compose up -d --build
```

### 4. Access the Web UI
Open your browser and navigate to:
```
http://<your-server-ip>:8080
```

---

## 🗄️ NAS Permission Integration (`PUID` & `PGID`)

When running Docker on a NAS or host mounting SMB/NFS shares, standard containers run as `root` (UID 0). Files written to the share become locked and cannot be edited, moved, or deleted by standard NAS users over network shares.

**VaporFetch** solves this by dynamically dropping privileges to your configured `PUID` and `PGID` using `gosu`:

| Platform | Recommended `PUID` | Recommended `PGID` | Notes |
| :--- | :--- | :--- | :--- |
| **Synology DSM** | `1026` | `100` | SSH into DSM and run `id` to verify your admin user |
| **Unraid** | `99` | `100` | Standard `nobody:users` permissions on Unraid |
| **TrueNAS** | `1000` | `1000` | Check the UID/GID of your dataset owner in TrueNAS UI |
| **Linux (Ubuntu/Debian)**| `1000` | `1000` | Run `id -u` and `id -g` in your terminal |

### Finding your UID and GID:
On your host or NAS terminal, run:
```bash
id $USER
# Example output: uid=1000(john) gid=1000(john) groups=1000(john),...
```

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

## 🔐 Steam Guard & Authentication

1. **Anonymous Downloads**:
   - For dedicated servers (e.g., Palworld, CS2, Rust), select **Anonymous**. No account is needed.
2. **Account Downloads**:
   - For games requiring an active purchase license, select **Steam Account** and enter your username and password.
   - If Steam Guard (Email or Mobile Authenticator) is enabled on your account, SteamCMD will pause and request a verification code.
   - **VaporFetch** detects this in real time and presents an interactive dialog in the Web UI. Enter your 5-character code and click **Submit Code**.
   - Your session token is saved in `/config`, so subsequent downloads won't prompt for 2FA again.

---

## 📁 Volume Layout

```
/
├── downloads/    <-- Mapped to your NAS share (games saved into subfolders here)
└── config/       <-- Persistent storage (SteamCMD credentials, 2FA tokens, history)
```

---

## 🛠️ REST API Endpoints

For automation scripts or remote triggers, VaporFetch provides a full REST API:

- `GET /api/status`: Current download status, active task progress, and NAS disk capacity.
- `GET /api/stream`: Server-Sent Events (SSE) streaming real-time logs and progress.
- `POST /api/download`: Start a download task.
  ```json
  {
    "appId": "2394010",
    "installDir": "palworld",
    "anonymous": true,
    "platform": "windows",
    "validate": true
  }
  ```
- `POST /api/cancel`: Gracefully abort the active download.
- `POST /api/steamguard`: Submit 2FA code (`{ "code": "ABC12" }`).
- `GET /api/appinfo/:appId`: Query Steam metadata for any AppID.
- `GET /api/storage`: Storage capacity, free space, and directory listing of `/downloads`.
- `GET /api/history`: List past download tasks.
- `GET /health`: Healthcheck endpoint.

---

## 📄 License

MIT License. Feel free to use, modify, and distribute.

