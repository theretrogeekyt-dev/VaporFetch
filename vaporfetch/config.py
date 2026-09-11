import os
import json
import shutil
from pathlib import Path
from typing import Dict, Any

# Base directories
def is_in_docker() -> bool:
    """Check if the current process is running inside a Docker container."""
    return (
        os.path.exists("/.dockerenv")
        or (os.path.exists("/proc/1/cgroup") and "docker" in Path("/proc/1/cgroup").read_text(errors="ignore"))
    )

# Determine default paths based on environment
DEFAULT_DATA_DIR = "/data" if is_in_docker() and os.path.exists("/data") else os.path.abspath("./data")
DEFAULT_DOWNLOADS_DIR = "/downloads" if is_in_docker() and os.path.exists("/downloads") else os.path.abspath("./downloads")

DATA_DIR = Path(os.environ.get("VAPORFETCH_DATA_DIR", DEFAULT_DATA_DIR))
DOWNLOADS_DIR = Path(os.environ.get("VAPORFETCH_DOWNLOADS_DIR", DEFAULT_DOWNLOADS_DIR))

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

def ensure_steam_environment() -> None:
    """
    Ensure SteamCMD configuration and cached credentials persist across container restarts.
    If running inside Docker, symlinks SteamCMD home directories to persistent /data subdirectories
    unless they are already mounted directly.
    """
    if not is_in_docker():
        return

    steam_dirs = [
        (Path("/root/Steam"), DATA_DIR / "steam_home"),
        (Path("/root/.steam"), DATA_DIR / "steam_root"),
        (Path("/root/.local/share/Steam"), DATA_DIR / "steam_share"),
    ]
    for link_target, persistent_dir in steam_dirs:
        try:
            persistent_dir.mkdir(parents=True, exist_ok=True)
            # If target is already a symlink or an active mountpoint, do not touch it
            if os.path.islink(str(link_target)) or os.path.ismount(str(link_target)):
                continue
            if link_target.exists():
                if link_target.is_dir():
                    try:
                        has_items = any(persistent_dir.iterdir())
                    except Exception:
                        has_items = False
                    # Migrate initial files if persistent directory is empty
                    if not has_items:
                        for item in link_target.iterdir():
                            dest = persistent_dir / item.name
                            if item.is_dir():
                                shutil.copytree(item, dest, dirs_exist_ok=True)
                            else:
                                shutil.copy2(item, dest)
                    shutil.rmtree(link_target)
                else:
                    link_target.unlink()
            else:
                link_target.parent.mkdir(parents=True, exist_ok=True)
            link_target.symlink_to(persistent_dir)
        except Exception:
            pass

ensure_steam_environment()

# Settings file
SETTINGS_FILE = DATA_DIR / "settings.json"
SESSION_FILE = DATA_DIR / "session.json"
APP_CACHE_FILE = DATA_DIR / "steam_apps_cache.json"
LIBRARY_CACHE_FILE = DATA_DIR / "library_cache.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_platform": os.environ.get("DEFAULT_PLATFORM", "windows"),
    "validate_downloads": os.environ.get("VALIDATE_DOWNLOADS", "true").lower() in ("true", "1", "yes"),
    "folder_format": "{name}",  # Options: '{name}', '{name} ({appid})', '{appid}'
    "steam_api_key": os.environ.get("STEAM_API_KEY", ""),
    "speed_limit_kb": 0,  # 0 for unlimited
}

def load_settings() -> Dict[str, Any]:
    """Load settings from JSON file or return defaults."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                merged = dict(DEFAULT_SETTINGS)
                merged.update(saved)
                return merged
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)

def save_settings(settings: Dict[str, Any]) -> None:
    """Save updated settings to disk."""
    current = load_settings()
    current.update(settings)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)

def find_steamcmd_path() -> str:
    """Locate the steamcmd binary in system path or standard install locations."""
    if os.path.isfile("/opt/steamcmd/steamcmd.sh") and os.access("/opt/steamcmd/steamcmd.sh", os.X_OK):
        return "/opt/steamcmd/steamcmd.sh"

    custom_path = os.environ.get("STEAMCMD_PATH")
    if custom_path and os.path.isfile(custom_path) and os.access(custom_path, os.X_OK):
        return os.path.realpath(custom_path)

    # Check standard system paths
    candidates = [
        "/opt/steamcmd/steamcmd.sh",
        shutil.which("steamcmd"),
        "/usr/games/steamcmd",
        "/usr/bin/steamcmd",
        "/steamcmd/steamcmd.sh",
        str(Path.home() / ".steam" / "steamcmd" / "steamcmd.sh"),
        str(Path.home() / ".local" / "share" / "Steam" / "steamcmd.sh"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.realpath(candidate)

    return "steamcmd"

def get_storage_stats() -> Dict[str, Any]:
    """Return free, used, and total storage space for the downloads directory."""
    try:
        usage = shutil.disk_usage(str(DOWNLOADS_DIR))
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "percent_used": round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0,
        }
    except Exception as e:
        return {
            "total_bytes": 0,
            "used_bytes": 0,
            "free_bytes": 0,
            "total_gb": 0.0,
            "free_gb": 0.0,
            "used_gb": 0.0,
            "percent_used": 0.0,
            "error": str(e),
        }

