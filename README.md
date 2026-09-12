# VaporFetch 🎮

A lightweight, self-hosted web application packaged in a single Docker container to batch-download Steam games directly to a mounted Network Attached Storage (NAS) directory.

Featuring modern **Steam Guard QR code authentication** (scan from your phone without entering credentials into web forms), a clean multi-select game library interface, and a sequential batch download queue manager powered by **SteamCMD**.

---

## 🌟 Key Features

- 📱 **Steam Guard QR Code Login**: Users scan an animated QR code displayed on the Web UI using their Steam Mobile app. No manual password or credential entry in web forms.
- 📚 **Game Library & Multi-Selection**: Browse your entire Steam library with official banner artwork, playtime stats, search filtering, and multi-select checkboxes to queue batches of games at once.
- ⚡ **Sequential Batch Downloader**: Built-in queue manager powered by SteamCMD that downloads games sequentially into `/downloads/<GameName>`.
- 📊 **Real-Time Progress & Telemetry**: Live progress bars, downloaded/total size metrics, download speed (MB/s), ETA calculations, and a collapsible live SteamCMD terminal stream powered by Server-Sent Events (SSE).
- 🗄️ **True NAS Compatibility**: Native support for `PUID`, `PGID`, and `UMASK` ensures that all downloaded game files match your host NAS user permissions (e.g. Unraid, Synology, TrueNAS, QNAP).
- 🪟 **Cross-Platform Depot Support**: Configurable to download Windows game depots (`+@sSteamCmdForcePlatformType windows`) directly onto a Linux NAS for Proton/Steam Deck/PC network sharing.
- 📦 **Zero-Bloat Packaging**: Single lightweight Docker container with a Python FastAPI backend and a responsive dark-mode frontend with zero build steps or heavy node modules.

---

## 📁 Project File Tree

```
VaporFetch/
├── Dockerfile                  # Single multi-arch container with SteamCMD & Python
├── docker-compose.yml          # Pre-configured compose file with NAS volume mounts
├── entrypoint.sh               # Handles dynamic PUID/PGID and NAS file permissions
├── requirements.txt            # Minimal Python dependencies
├── README.md                   # Documentation & setup guide
└── app/
    ├── __init__.py             # Package marker
    ├── main.py                 # FastAPI server, REST API, & SSE live stream
    ├── auth.py                 # Steam Guard QR session authentication
    ├── steam_api.py            # Steam Web API client (GetOwnedGames, avatars)
    ├── queue_manager.py        # Sequential download queue & SteamCMD runner
    ├── config.py               # Paths, settings, and persistent storage
    └── static/
        ├── index.html          # Clean, responsive single-page dashboard
        ├── style.css           # Sleek dark gaming theme with animations
        └── app.js              # Client controller for QR auth, library & queue
```

---

## 🚀 Quick Start with Docker Compose

### 1. Clone or Download Repository
```bash
git clone https://github.com/theretrogeekyt-dev/VaporFetch.git
cd VaporFetch
```

### 2. Check Host PUID & PGID
Find your NAS or host user's UID and GID so the container writes files with matching permissions:
```bash
id $USER
# Example output: uid=1000(joshua) gid=1000(joshua)
```

### 3. Configure `docker-compose.yml`
Edit `docker-compose.yml` and point `/downloads` to your host storage or NAS share:

```yaml
services:
  vaporfetch:
    build: .
    image: vaporfetch:latest
    container_name: vaporfetch
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - PUID=1000                  # Match host user ID
      - PGID=1000                  # Match host group ID
      - UMASK=002                  # Group-writable permissions
      - STEAM_API_KEY=             # Optional: https://steamcommunity.com/dev/apikey
      - FORCE_PLATFORM=windows     # Download Windows depots on Linux NAS
    volumes:
      - ./data:/app/data           # Persistent app state & SteamCMD login cache
      - /mnt/storage/games:/downloads  # Your NAS game storage mount path
```

### 4. Start Container
```bash
docker compose up -d
```

Open your browser at **`http://<nas-ip>:8080`**.

---

## 🔑 How Steam Guard QR Login Works

1. Open the VaporFetch web interface and click **"Steam Guard Login"**.
2. A unique challenge QR code will be generated on the screen.
3. Open the **Steam Mobile App** on your smartphone.
4. Tap the **Steam Guard** icon (shield) and scan the QR code displayed on the screen.
5. Tap **"Sign In"** to approve the session.
6. VaporFetch automatically detects the confirmation, authenticates your session, and loads your owned game library!

> [!NOTE]
> **Steam Web API Key**: If your Steam profile's game details are set to "Friends-Only" or "Private", you can add a Steam Web API key in the UI settings or via the `STEAM_API_KEY` environment variable. You can generate a free key at [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey).

---

## 🎮 Commercial Games & SteamCMD

- **Free Dedicated Servers & Tools**: Download immediately with no additional credentials needed (`anonymous` mode).
- **Commercial Owned Games**: SteamCMD requires an account with game ownership. VaporFetch auto-populates your username from your QR login. You can supply your password in the Settings modal (or container config). Because the SteamCMD login token is persisted in `/app/data/steam_home`, SteamCMD remembers your machine authorization across container restarts.

---

## 🛠️ NAS Permission Details (PUID / PGID)

When running on systems like **Synology DSM**, **Unraid**, or **TrueNAS SCALE**:
- Setting `PUID` and `PGID` ensures that any folder or file created by SteamCMD inside `/downloads` is owned by that specific host user/group.
- Setting `UMASK=002` ensures that files are group-writable, allowing other services (such as Samba, NFS, or game launchers) to read and modify downloaded files without permission errors.

---

## 📡 REST & Streaming API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/qr/begin` | Generates a new Steam Guard QR auth session |
| `POST` | `/api/auth/qr/poll` | Polls authentication status until mobile approval |
| `GET` | `/api/auth/session` | Returns the active user session and profile |
| `POST` | `/api/auth/logout` | Clears current session |
| `GET` | `/api/games` | Returns owned games list with banner images |
| `GET` | `/api/queue` | Returns current download queue and active item |
| `POST` | `/api/queue` | Adds a batch of selected games to the download queue |
| `DELETE`| `/api/queue/{id}` | Cancels or removes an item from the queue |
| `POST` | `/api/queue/{id}/retry` | Retries a failed download |
| `GET` | `/api/queue/stream` | Server-Sent Events (SSE) live progress & log stream |
| `GET` | `/api/system/status` | Returns NAS storage disk usage and container info |
| `POST` | `/api/settings` | Updates container settings |

