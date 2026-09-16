# VaporFetch 🎮

[![Build & Publish Docker Image](https://github.com/theretrogeekyt-dev/VaporFetch/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/theretrogeekyt-dev/VaporFetch/actions/workflows/docker-publish.yml)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://github.com/theretrogeekyt-dev/VaporFetch/pkgs/container/vaporfetch)

A lightweight, self-hosted web application packaged in a single Docker container to batch-download Steam games directly to a mounted Network Attached Storage (NAS) directory.

Featuring modern **Steam Guard QR code authentication** (scan from your phone without entering credentials into web forms), a clean multi-select game library interface, and a sequential batch download queue manager powered by **SteamCMD**.

---

## 🚀 Quick Setup Without Source Code (Recommended)

You do **NOT** need to clone the repository or build from source. A pre-built, automated Docker image is compiled and published to the GitHub Container Registry (`ghcr.io`) upon every push.

### Option 1: Using `docker-compose.yml` (Fastest)

1. Create a folder and download the standalone `docker-compose.yml`:
   ```bash
   mkdir -p vaporfetch && cd vaporfetch
   curl -fsSL https://raw.githubusercontent.com/theretrogeekyt-dev/VaporFetch/main/docker-compose.yml -o docker-compose.yml
   ```

2. Open `docker-compose.yml` in your editor and adjust your storage paths:
   ```yaml
   services:
     vaporfetch:
       image: ghcr.io/theretrogeekyt-dev/vaporfetch:latest
       container_name: vaporfetch
       restart: unless-stopped
       ports:
         - "8080:8080"
       environment:
         - PUID=1000                  # Your NAS user ID (id -u)
         - PGID=1000                  # Your NAS group ID (id -g)
         - UMASK=002                  # Ensures group-writable permissions
         - STEAM_API_KEY=             # Optional: https://steamcommunity.com/dev/apikey
         - FORCE_PLATFORM=windows     # Download Windows game depots on Linux NAS
         - UPDATE_CHANNEL=main        # Optional branch channel for update checks
         - UPDATE_IMAGE_TAG=latest    # Optional image tag for 1-click in-app updates
       volumes:
         - ./data:/app/data           # Stores settings, sessions & Steam cache
         - /mnt/storage/games:/downloads  # Mount path to your NAS share
   ```

3. Launch the container:
   ```bash
   docker compose up -d
   ```

4. Open **`http://<nas-ip>:8080`** in your web browser.

---

### Option 2: Single `docker run` Command (Zero Files Needed)

You can spin up VaporFetch with a single CLI command without creating any files:

```bash
docker run -d \
  --name vaporfetch \
  --restart unless-stopped \
  -p 8080:8080 \
  -e PUID=1000 \
  -e PGID=1000 \
  -e UMASK=002 \
  -e FORCE_PLATFORM=windows \
  -v /path/to/nas/data:/app/data \
  -v /path/to/nas/downloads:/downloads \
  ghcr.io/theretrogeekyt-dev/vaporfetch:latest
```

---

### Option 3: Synology / Unraid / TrueNAS / Portainer Web UI

- **Container Image**: `ghcr.io/theretrogeekyt-dev/vaporfetch:latest`
- **Port Mapping**: `8080` (host) &rarr; `8080` (container)
- **Volumes**:
  - `/downloads` &rarr; Host path to your NAS game library folder
  - `/app/data` &rarr; Host path to app data storage
- **Environment Variables**:
  - `PUID`: `1000` (or `99` on Unraid)
  - `PGID`: `1000` (or `100` on Unraid)
  - `UMASK`: `002`

---

## 🔄 Automated Updates via GitHub Actions

VaporFetch includes an automated GitHub Actions CI/CD pipeline (`.github/workflows/docker-publish.yml`). 
Whenever new commits are pushed to any branch, the workflow:
1. Builds a fresh, verified Docker image with Debian bookworm, SteamCMD, and Python 3.
2. Publishes branch tags to **GitHub Container Registry** (`ghcr.io/theretrogeekyt-dev/vaporfetch:<branch-tag>`) and `latest` for the default branch.

### How to Update Your Container

To update to the latest version at any time:
```bash
docker compose pull
docker compose up -d
```
*Or use [Watchtower](https://containrrr.dev/watchtower/) for 100% automated updates.*

---

## 🌟 Key Features

- 📱 **Steam Guard QR Code Login & One-Time Setup**: Scan an animated QR code displayed on the Web UI using your Steam Mobile app. Once approved, you are prompted for your password once to authorize SteamCMD downloads—persisting credentials and auto-refreshing access tokens so you never have to sign in repeatedly.
- 📚 **Game Library & Multi-Selection**: Browse your entire Steam library with official banner artwork, playtime stats, search filtering, and multi-select checkboxes to queue batches of games at once.
- ⚡ **Sequential Batch Downloader**: Built-in queue manager powered by SteamCMD that downloads games sequentially into `/downloads/<GameName>`.
- 🧹 **Clean Directory Restructuring**: Automatically removes nested `steamapps/common` hierarchies post-download, flattens game files to the root game directory, and renames `_CommonRedist` to `Redistrutables`.
- 🕹️ **DRM-Free Offline Wrapper (Goldberg Emulator)**: Optional integration of Goldberg Steam Emulator for DRM-free offline play of compatible games directly from your backup NAS share. Safely backs up authentic Steam DLLs as `.orig`, writes `steam_appid.txt`, and supports both auto-patching and per-game Apply/Revert controls.
- 🚀 **Startup Update Notifications & 1-Click Self-Update**: Automatically notifies you on startup when a new container image/release is published. Supports 1-click in-app container recreation via Docker socket (`/var/run/docker.sock`) so you never have to touch your NAS Container Manager GUI.
- 📊 **Real-Time Progress & Telemetry**: Live progress bars, downloaded/total size metrics, download speed (MB/s), ETA calculations, and a collapsible live SteamCMD terminal stream powered by Server-Sent Events (SSE).
- 🗄️ **True NAS Compatibility**: Native support for `PUID`, `PGID`, and `UMASK` ensures that all downloaded game files match your host NAS user permissions (e.g. Unraid, Synology, TrueNAS, QNAP).
- 🪟 **Cross-Platform Depot Support**: Configurable to download Windows game depots (`+@sSteamCmdForcePlatformType windows`) directly onto a Linux NAS for Proton/Steam Deck/PC network sharing.
- 📦 **Zero-Bloat Packaging**: Single lightweight Docker container with a Python FastAPI backend and a responsive dark-mode frontend with zero build steps or heavy node modules.

---

## 📁 Project File Tree

```
VaporFetch/
├── .github/
│   └── workflows/
│       └── docker-publish.yml  # GitHub Actions CI/CD to build & push to ghcr.io on push
├── Dockerfile                  # Single multi-arch container with SteamCMD, Goldberg & Python
├── docker-compose.yml          # Pre-configured compose file with NAS volume mounts
├── entrypoint.sh               # Handles dynamic PUID/PGID and NAS file permissions
├── requirements.txt            # Minimal Python dependencies
├── README.md                   # Documentation & setup guide
└── app/
    ├── __init__.py             # Package marker
    ├── main.py                 # FastAPI server, REST API, & SSE live stream
    ├── auth.py                 # Steam Guard QR session authentication & JWT refresh
    ├── steam_api.py            # Steam Web API client (GetOwnedGames, avatars, caching)
    ├── queue_manager.py        # Sequential download queue, SteamCMD runner, & post-processing
    ├── goldberg.py             # Goldberg Steam Emulator manager, patcher & restoration
    ├── updater.py              # Startup update checker and 1-click Docker container updater
    ├── config.py               # Paths, settings, and persistent storage
    └── static/
        ├── index.html          # Clean, responsive single-page dashboard
        ├── style.css           # Sleek dark gaming theme with animations
        └── app.js              # Client controller for QR auth, library, queue & Goldberg
```

---

## 🔑 How Steam Guard QR Login Works (One-Time Setup)

1. Open the VaporFetch web interface and click **"Steam Guard Login"**.
2. A unique challenge QR code will be generated on the screen.
3. Open the **Steam Mobile App** on your smartphone.
4. Tap the **Steam Guard** icon (shield) and scan the QR code displayed on the screen.
5. Tap **"Sign In"** on your phone to approve the session.
6. VaporFetch automatically detects the confirmation, validates your session, and transitions to **Stage 2: Password Prompt**.
7. Enter your Steam password once to authorize SteamCMD to download commercial games you own.
8. Credentials and session tokens are persisted locally in `/app/data/`. VaporFetch automatically refreshes your Web API tokens, so you never need to scan or log in again!

> [!NOTE]
> **Steam Web API Key**: If your Steam profile's game details are set to "Friends-Only" or "Private", you can add a Steam Web API key in the UI settings or via the `STEAM_API_KEY` environment variable. You can generate a free key at [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey).

---

## 🧹 Automatic Directory Restructuring

SteamCMD downloads game content into a deep, cumbersome folder hierarchy:
`.../steamapps/common/<GameFolder>/...` along with an external `appmanifest_<appid>.acf` file.

VaporFetch's built-in post-processing pipeline automatically cleans this up after every completed download:
1. **Flattens Game Files**: Moves all game files directly into `/downloads/<GameName>/`, eliminating the intermediate `steamapps/common` path.
2. **Relocates ACF Manifest**: Moves the `appmanifest_<appid>.acf` into the root of `/downloads/<GameName>/` and completely deletes the empty `steamapps` folder.
3. **Renames Redistributables**: Detects any `_CommonRedist` or `CommonRedist` folder and renames it to `Redistrutables`.

---

## 🕹️ DRM-Free Offline Backup Wrapper (Goldberg Emulator)

For users creating offline game archives for long-term preservation, VaporFetch includes built-in support for the open-source **Goldberg Steam Emulator**.

### How It Works
- **Compatibility**: Scans for standard Steamworks binaries (`steam_api.dll` for 32-bit and `steam_api64.dll` for 64-bit).
- **Safety First**: Your authentic Steam binaries are **never deleted**—they are saved alongside the patched file as `steam_api.dll.orig` or `steam_api64.dll.orig`.
- **Offline Configuration**: Generates `steam_appid.txt` and `steam_settings/force_account_name.txt` so games run DRM-free without needing the Steam client running or an internet connection.
- **Clean Reversion**: Reverting instantly restores the `.orig` binaries and deletes the generated emulator files.

### Configuration Options
1. **Automatic Mode**: Turn on **"Auto-apply Goldberg Emulator to downloaded games"** in the Settings modal to patch all compatible games as soon as they finish downloading.
2. **Per-Game Control**: In the **Completed Downloads** section of the UI, click the **"Offline Wrapper"** button on any game to check compatibility, review current patch status, apply the emulator, or revert back to authentic files.

---

## 🎮 Commercial Games & SteamCMD

- **Free Dedicated Servers & Tools**: Download immediately with no additional credentials needed (`anonymous` mode).
- **Commercial Owned Games**: SteamCMD requires an account with game ownership. VaporFetch captures your username from your QR login and your password from the one-time setup step. Because the SteamCMD login token is persisted in `/app/data/steam_home`, SteamCMD remembers your machine authorization across container restarts.

---

## 🛠️ NAS Permission Details (PUID / PGID)

When running on systems like **Synology DSM**, **Unraid**, or **TrueNAS SCALE**:
- Setting `PUID` and `PGID` ensures that any folder or file created by SteamCMD inside `/downloads` is owned by that specific host user/group.
- Setting `UMASK=002` ensures that files are group-writable, allowing other services (such as Samba, NFS, or game launchers) to read and modify downloaded files without permission errors.

---

## 🚀 In-App Container Updates & Startup Notifications

VaporFetch automatically queries the configured update channel on page startup to check if a new commit has been published.

### How It Works
1. **Startup Alert Banner**: If an update is detected, a blue notification banner appears at the top of your dashboard displaying the new commit message, short SHA, and an **"Update Now"** button.
2. **1-Click Self-Update (Zero NAS GUI Required)**:
   - If you mount the host Docker socket (`-v /var/run/docker.sock:/var/run/docker.sock`), clicking **"Update Now"** instructs VaporFetch to pull the newest image from `ghcr.io` and recreate itself in-place using Watchtower automation.
   - The web interface displays a sleek reconnect countdown screen while the container restarts, then automatically refreshes the page once back online!
3. **No-Socket Fallback**:
   - If the Docker socket is not mounted, the update modal displays the release changelog and provides a 1-click copyable terminal command (`docker compose pull && docker compose up -d`) so you can update instantly via SSH without navigating Synology Container Manager.

### Optional Branch Channel Configuration

If you want a non-main deployment/update channel (for example a feature branch image):
- Set `UPDATE_CHANNEL` to the Git branch to monitor for update checks (e.g. `copilot/add-mobile-friendly-web-ui`).
- Set `UPDATE_IMAGE_TAG` to the published image tag for that branch (e.g. `copilot-add-mobile-friendly-web-ui`).
- Change your container image tag to match the same branch channel if you want runtime and updater behavior aligned.

---

## 📡 REST & Streaming API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/qr/begin` | Generates a new Steam Guard QR auth session |
| `POST` | `/api/auth/qr/poll` | Polls authentication status until mobile approval |
| `GET` | `/api/auth/session` | Returns the active user session and setup status |
| `POST` | `/api/auth/logout` | Clears current session |
| `GET` | `/api/games` | Returns owned games list with banner images |
| `GET` | `/api/queue` | Returns current download queue and active item |
| `POST` | `/api/queue` | Adds a batch of selected games to the download queue |
| `DELETE`| `/api/queue/{id}` | Cancels or removes an item from the queue |
| `POST` | `/api/queue/{id}/retry` | Retries a failed download |
| `GET` | `/api/queue/stream` | Server-Sent Events (SSE) live progress & log stream |
| `GET` | `/api/system/status` | Returns NAS storage disk usage and container info |
| `POST` | `/api/settings` | Updates container settings (including Goldberg toggle) |
| `GET` | `/api/games/{appid}/goldberg` | Inspects compatibility and patch status of a downloaded game |
| `POST` | `/api/games/{appid}/goldberg/apply` | Applies Goldberg emulator, backs up `.orig`, creates `steam_appid.txt` |
| `POST` | `/api/games/{appid}/goldberg/revert` | Restores original Steam DLLs and removes emulator configuration |
| `GET` | `/api/system/version` | Returns container version, commit SHA, and Docker socket status |
| `GET` | `/api/system/update/check` | Checks upstream GitHub repository for new commits/releases |
| `POST` | `/api/system/update/apply` | Triggers container self-update via Docker socket |
