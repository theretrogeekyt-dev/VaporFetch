import os
import json
import shutil
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Data directory for persistent app state, sessions, and settings
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data" if Path("/app/data").exists() else str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Downloads directory where SteamCMD installs games
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "/downloads" if Path("/downloads").exists() else str(BASE_DIR / "downloads")))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Version, commit tracking, and Docker socket
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_COMMIT_SHA = os.getenv("APP_COMMIT_SHA", "dev")
DOCKER_SOCKET_PATH = Path(os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock"))

# Path to SteamCMD executable
def find_steamcmd() -> str:
    env_path = os.getenv("STEAMCMD_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    
    candidates = [
        "/usr/games/steamcmd",
        "/steamcmd/steamcmd.sh",
        "/usr/bin/steamcmd",
        shutil.which("steamcmd")
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return "steamcmd"

STEAMCMD_BIN = find_steamcmd()

# Settings file
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "steam_api_key": os.getenv("STEAM_API_KEY", ""),
    "force_platform": os.getenv("FORCE_PLATFORM", "windows"),  # "windows" or "linux"
    "validate_downloads": True,
    "enable_goldberg": False,
    "steamcmd_username": "",
    "steamcmd_password": "",
    "steamcmd_authorized": False,
    "custom_steamcmd_args": "",
}

STEAM_HOME_DIR = DATA_DIR / "steam_home"
STEAM_HOME_DIR.mkdir(parents=True, exist_ok=True)

def sync_steam_sentry_files():
    """Syncs any Steam Guard sentry files (ssfn*) between steam directories and persistent storage."""
    try:
        STEAM_HOME_DIR.mkdir(parents=True, exist_ok=True)
        search_dirs = [
            Path("/steamcmd"),
            Path(os.path.expanduser("~/.steam")),
            Path(os.path.expanduser("~/.steam/steam")),
            Path("/home/steam/.steam"),
            Path("/home/steam/.steam/steam"),
            Path("/home/steam"),
            STEAM_HOME_DIR,
        ]
        sentry_files = set()
        for d in search_dirs:
            if d.exists() and d.is_dir():
                for f in d.glob("ssfn*"):
                    if f.is_file() and not f.is_symlink():
                        sentry_files.add(f)
        
        # Copy newly found physical sentry files into STEAM_HOME_DIR
        for sf in sentry_files:
            dest = STEAM_HOME_DIR / sf.name
            if sf != dest and not dest.exists():
                shutil.copy2(sf, dest)

        # Link from STEAM_HOME_DIR into /steamcmd and ~/.steam
        for psf in STEAM_HOME_DIR.glob("ssfn*"):
            if psf.is_file():
                for target_dir in [Path("/steamcmd"), Path("/home/steam/.steam"), Path("/home/steam/.steam/steam")]:
                    try:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        link_path = target_dir / psf.name
                        if not link_path.exists():
                            link_path.symlink_to(psf)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Config] Error syncing Steam sentry files: {e}")

def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = {**DEFAULT_SETTINGS, **data}
                return merged
        except Exception:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(new_settings: dict) -> dict:
    current = load_settings()
    current.update(new_settings)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current

