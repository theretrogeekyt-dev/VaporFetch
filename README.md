# VaporFetch

VaporFetch queues Steam downloads on a self-hosted Linux NAS. Browse your Steam library or enter an App ID, choose a download platform, and watch SteamCMD progress from a desktop or mobile browser.

## Quick start

VaporFetch ships as a Linux x86-64 Docker image. Download the [Compose file](docker-compose.yml) into an empty directory:

```sh
curl -fsSLO https://raw.githubusercontent.com/theretrogeekyt-dev/VaporFetch/main/docker-compose.yml
```

1. Set the `/downloads` bind mount to your game share. Keep the `/app/data` bind mount across container updates.
2. Match `PUID` and `PGID` to the NAS account that should own downloads. Use `UMASK=002` for group-writable files.
3. Set a dashboard password in a local `.env` file if the dashboard is accessible to other people.

   ```dotenv
   VAPORFETCH_ADMIN_USER=admin
   VAPORFETCH_ADMIN_PASSWORD=replace-with-a-unique-password
   ```

4. Run `docker compose up -d`, then open `http://<nas-ip>:8080`. Use HTTPS at your reverse proxy when sending credentials over a network. Preserve the original `Host` header and disable response buffering for `/api/queue/stream`.

VaporFetch is a single-operator dashboard. With the dashboard password unset, anyone who can reach the service can operate it. Keep it on a trusted network or behind your own access controls. The data volume contains Steam session material and may contain a saved Steam password. Restrict who can read that volume and its backups.

## Queue downloads

- **Dedicated servers and tools.** Open **Download Queue** and enter the Steam App ID. With no Steam account configured, SteamCMD signs in anonymously. Valve enables anonymous access for selected apps.
- **Owned games.** Sign in to Steam. On desktop, scan the QR code with Steam Guard, then authorize SteamCMD when prompted. On mobile, sign in and approve the Steam Guard notification or enter the requested code. Select games in the library and queue the batch. Downloads reuse SteamCMD's saved authorization. If it expires, authorize SteamCMD again in Settings and retry the download. If Steam withholds your library, check your Steam game-details privacy or configure a Steam Web API key in Settings.
- **Progress and history.** Downloads run one at a time. Cancel an active item, retry a failed or cancelled item, or dismiss items from history. Clearing history leaves downloaded files on disk.

New installations use `/downloads/<title> [<appid>]`. VaporFetch keeps SteamCMD's native folder layout, including its manifests, so validation and retries can reuse the existing depot. Recognized installations from older versions keep their existing location. SteamCMD can ask for Steam Guard again if its saved authorization expires or Valve requires a new approval. See [Valve's SteamCMD documentation](https://developer.valvesoftware.com/wiki/SteamCMD) for app compatibility and depot behavior.

The optional Goldberg offline wrapper supports selected Windows games that use the standard Steamworks DLLs. It saves the original DLLs as `.orig` files. Use **Offline Wrapper** in desktop download history to inspect, apply, or revert a patch.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `PUID` / `PGID` | `1000` / `1000` | UID and GID used to write files on the NAS |
| `UMASK` | `002` | Permission mask for new files |
| `FORCE_PLATFORM` | `windows` | Default depot platform. The dashboard also supports Linux and macOS. |
| `STEAM_API_KEY` | Empty | Optional Steam Web API key. A saved dashboard setting overrides the environment default. |
| `VAPORFETCH_ADMIN_USER` | `admin` | Dashboard HTTP Basic username |
| `VAPORFETCH_ADMIN_PASSWORD` | Empty | Enables dashboard sign-in when set |

The service health endpoint is `GET /healthz`. The API schema is available under `/docs`.

## Update

```sh
docker compose pull
docker compose up -d
```

The optional in-app updater requires a dashboard password and access to the host Docker socket. Mounting the socket gives the container control over Docker on the host. Standard Compose updates work with the two data mounts alone.

## Development

Use Python 3.11 or newer. A working SteamCMD install is required for live download and device authorization flows.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Set `DATA_DIR` and `DOWNLOAD_DIR` to isolate test data from a real library. Set `STEAMCMD_PATH` to a local SteamCMD launcher when developing on Linux. The automated suite uses a simulated SteamCMD process and needs no Steam account.

To test the same image used for deployment:

```sh
docker build -t vaporfetch:local .
docker run --rm -p 127.0.0.1:8080:8080 vaporfetch:local
```
