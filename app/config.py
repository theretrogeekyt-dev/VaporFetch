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
    "custom_steamcmd_args": "",
}

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

