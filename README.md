# VaporFetch 💨🎮

**VaporFetch** is a lightweight, Docker-based Steam game downloader and backup tool powered by `steamcmd`. It allows you to sign into your Steam account (with full Steam Guard 2FA support), browse your game library, and download/backup select games or your entire library with cross-platform depot targeting (Windows, Linux, macOS).

![VaporFetch UI Preview](https://raw.githubusercontent.com/theretrogeekyt-dev/VaporFetch/main/docs/preview.png)

---

## Features

- 🐳 **Docker-Ready**: Packaged with a lightweight Debian Bookworm container configured with 32-bit compatibility libraries and pre-bootstrapped `steamcmd`.
- 🔐 **Steam Authentication & 2FA**:
  - Log in using your Steam credentials.
  - Interactive Steam Guard support for both **Email codes** and **Mobile Authenticator (Steam Guard App) codes**.
  - Persistent credential sessions across container restarts using volume mounts.
- 📚 **Library Discovery**:
  - Automatically queries owned account licenses directly via SteamCMD (`licenses_print`).
  - Resolves AppIDs to game titles, headers, and metadata.
  - Detects existing backups and validates installed sizes.
- 🎯 **Backup Select or All Games**:
  - **Select Games**: Filter, search, and check individual games to queue for download.
  - **Backup All**: One-click command to backup your entire Steam library sequentially.
  - **Manual AppID**: Directly queue any Steam AppID or dedicated server.
- 🪟 **Cross-Platform Depot Support**:
  - Most PC games on Steam only provide Windows depots. VaporFetch supports forcing target depot platforms (e.g. `@sSteamCmdForcePlatformType windows`), allowing Linux/Docker containers to backup Windows game files without issues.
- ⚡ **Modern Dark Web UI & CLI**:
  - Single-page dashboard with real-time Server-Sent Events (SSE) streaming progress, download speeds, and ETA.
  - Live SteamCMD console log viewer.
  - Full-featured CLI for headless, terminal, or script automation.

---

## Quickstart (Synology NAS / Docker Compose)

You do **not** need to manually clone or download code to run VaporFetch. You can deploy it using only the `docker-compose.yml` file:

### On Synology NAS (Container Manager)
1. Open **Container Manager** > **Project** > **Create**.
2. Set Project Name to `vaporfetch` and Path to `/docker/vaporfetch`.
3. Select **Create docker-compose.yaml** and paste:
   ```yaml
   services:
     vaporfetch:
       image: ghcr.io/theretrogeekyt-dev/vaporfetch:latest
       container_name: vaporfetch
       platform: linux/amd64
       restart: unless-stopped
       ports:
         - "8080:8080"
       environment:
         - DEFAULT_PLATFORM=windows
         - VALIDATE_DOWNLOADS=true
         - PORT=8080
       volumes:
         - ./data:/data
         - ./downloads:/downloads
         - ./data/steam_root:/root/.steam
         - ./data/steam_share:/root/.local/share/Steam
   ```
4. Click **Next** and **Done**. Synology will automatically download the image and launch it.
5. Open `http://<synology-ip>:8080` in your browser.

### On Standard Docker Host
Save the snippet above as `docker-compose.yml` and run:
```bash
docker compose up -d
```

---

## Docker Volumes

| Host Path | Container Path | Purpose |
| :--- | :--- | :--- |
| `./data` | `/data` | Configuration, cache, settings, and Steam session tokens (`session.json`, `library_cache.json`) |
| `./downloads` | `/downloads` | Destination directory where games and Steam appmanifest files are saved |
| `./data/steam_root` | `/root/.steam` | SteamCMD client cache and credential tokens |

---

## CLI Usage

You can also run VaporFetch in interactive terminal mode or execute commands directly inside the running container:

### Check Status
```bash
docker exec -it vaporfetch python3 -m vaporfetch status
```

### Log In via CLI
```bash
docker exec -it vaporfetch python3 -m vaporfetch login
```
*(Prompts for username, password, and Steam Guard 2FA code)*

### List Owned Games
```bash
docker exec -it vaporfetch python3 -m vaporfetch list
docker exec -it vaporfetch python3 -m vaporfetch list --missing # Only games not yet backed up
docker exec -it vaporfetch python3 -m vaporfetch list --downloaded # Only backed up games
```

### Backup Games
```bash
# Backup specific games by AppID (with live terminal progress)
docker exec -it vaporfetch python3 -m vaporfetch backup --appid 730,400 --watch

# Backup entire Steam library
docker exec -it vaporfetch python3 -m vaporfetch backup --all

# Backup with target platform override
docker exec -it vaporfetch python3 -m vaporfetch backup --appid 1086940 --platform windows
```

---

## How to Restore Backups to a Steam Client

Every game backed up by VaporFetch preserves standard Steam file layouts, including game files and Steam manifests (`steamapps/appmanifest_<appid>.acf`).

To restore a game into your official Steam client on your gaming PC:

1. Copy the game folder (or contents) into your Steam library folder:
   - **Windows**: `C:\Program Files (x86)\Steam\steamapps\common\<GameFolder>`
   - **Linux**: `~/.steam/steam/steamapps/common/<GameFolder>`
2. Copy `appmanifest_<appid>.acf` from the backup directory into the parent `steamapps/` folder.
3. Restart or start Steam.
4. Steam will recognize the existing files immediately and verify the installation without needing to re-download.

---

## Configuration & Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8080` | Web server port |
| `DEFAULT_PLATFORM` | `windows` | Default platform depot (`windows`, `linux`, `macos`) |
| `VALIDATE_DOWNLOADS`| `true` | Runs file checksum verification with SteamCMD after download |
| `VAPORFETCH_DATA_DIR` | `/data` | Directory for persistent state and settings |
| `VAPORFETCH_DOWNLOADS_DIR` | `/downloads` | Directory for game backups |
| `STEAM_API_KEY` | *(empty)* | Optional Steam Web API key for additional metadata |

---

## Development & Local Testing

You can run VaporFetch locally without Docker using Python 3:

```bash
# Create virtual environment and install requirements
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run unit tests
python3 -m unittest discover -s tests -v

# Launch local development server
python3 -m vaporfetch serve --port 8080
```

---

## License

This project is licensed under the [The Unlicense](LICENSE) (Public Domain).

