import os
import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

from vaporfetch.config import (
    DATA_DIR,
    DOWNLOADS_DIR,
    APP_CACHE_FILE,
    LIBRARY_CACHE_FILE,
    load_settings,
)
from vaporfetch.steamcmd import get_current_session, fetch_licenses

# Pre-populated dictionary of common Steam games for instant offline lookup
COMMON_STEAM_APPS = {
    10: "Counter-Strike",
    70: "Half-Life",
    220: "Half-Life 2",
    240: "Counter-Strike: Source",
    400: "Portal",
    440: "Team Fortress 2",
    550: "Left 4 Dead 2",
    570: "Dota 2",
    620: "Portal 2",
    730: "Counter-Strike 2",
    105600: "Terraria",
    252490: "Rust",
    271590: "Grand Theft Auto V",
    292030: "The Witcher 3: Wild Hunt",
    359550: "Tom Clancy's Rainbow Six Siege",
    381210: "Dead by Daylight",
    413150: "Stardew Valley",
    578080: "PUBG: BATTLEGROUNDS",
    1086940: "Baldur's Gate 3",
    1091500: "Cyberpunk 2077",
    1172470: "Apex Legends",
    1245620: "ELDEN RING",
    1623730: "Palworld",
    2050650: "Resident Evil 4",
}

class AppResolver:
    """Resolves Steam AppIDs to game titles using local cache and Steam Web API."""
    def __init__(self):
        self.app_map: Dict[int, str] = dict(COMMON_STEAM_APPS)
        self._has_attempted_update = False
        self._load_cache()

    def _load_cache(self) -> None:
        if APP_CACHE_FILE.exists():
            try:
                with open(APP_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.app_map[int(k)] = v
            except Exception as e:
                print(f"[VaporFetch] Warning: Failed to load app cache: {e}")

    def save_cache(self) -> None:
        try:
            with open(APP_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.app_map, f)
        except Exception as e:
            print(f"[VaporFetch] Warning: Failed to save app cache: {e}")

    def update_from_steam_api(self) -> bool:
        """Download Steam AppID master list if available."""
        if self._has_attempted_update:
            return False
        self._has_attempted_update = True

        settings = load_settings()
        api_key = settings.get("steam_api_key") or settings.get("api_key") or os.environ.get("STEAM_API_KEY", "")

        # 1. Try IStoreService if an API key is configured
        if api_key:
            try:
                url = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?key={api_key}&max_results=50000"
                req = urllib.request.Request(url, headers={"User-Agent": "VaporFetch/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    apps = payload.get("response", {}).get("apps", [])
                    for item in apps:
                        aid = item.get("appid")
                        name = item.get("name", "").strip()
                        if aid and name:
                            self.app_map[int(aid)] = name
                    if apps:
                        self.save_cache()
                        return True
            except Exception:
                pass

        # 2. Try legacy public endpoint if available
        try:
            url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
            req = urllib.request.Request(url, headers={"User-Agent": "VaporFetch/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                apps = payload.get("applist", {}).get("apps", [])
                for item in apps:
                    aid = item.get("appid")
                    name = item.get("name", "").strip()
                    if aid and name:
                        self.app_map[int(aid)] = name
                if apps:
                    self.save_cache()
                    return True
        except Exception:
            # Endpoint deprecated by Valve; titles fall back seamlessly to per-app store API lookup
            pass

        return False

    def resolve_name(self, appid: int) -> str:
        """Get the title for an AppID, querying store API if missing."""
        if appid in self.app_map:
            return self.app_map[appid]

        # Try online store API lookup for single app
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "VaporFetch/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if str(appid) in data and data[str(appid)].get("success"):
                    name = data[str(appid)]["data"].get("name", "").strip()
                    if name:
                        self.app_map[appid] = name
                        self.save_cache()
                        return name
        except Exception:
            pass

        return f"Steam App {appid}"

resolver = AppResolver()


def sanitize_folder_name(name: str) -> str:
    """Sanitize game title for safe folder creation across Linux/Windows/Mac."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or "Unknown_Game"


def get_game_install_dir(name: str, appid: int) -> Path:
    """Return the destination path for an app backup based on user settings."""
    settings = load_settings()
    fmt = settings.get("folder_format", "{name}")
    safe_name = sanitize_folder_name(name)
    folder_name = fmt.format(name=safe_name, appid=appid)
    return DOWNLOADS_DIR / sanitize_folder_name(folder_name)


def check_backup_status(name: str, appid: int) -> Dict[str, Any]:
    """
    Check if a game is already downloaded / backed up in DOWNLOADS_DIR.
    Returns status ('downloaded', 'incomplete', 'not_downloaded') and size.
    """
    game_dir = get_game_install_dir(name, appid)
    if not game_dir.exists():
        # Also check fallback directory names
        fallback_dir = DOWNLOADS_DIR / str(appid)
        if fallback_dir.exists():
            game_dir = fallback_dir
        else:
            return {"status": "not_downloaded", "size_bytes": 0, "size_formatted": "0 B"}

    # Check for steam manifest or game files
    manifest = game_dir / "steamapps" / f"appmanifest_{appid}.acf"
    total_size = 0
    file_count = 0

    try:
        for entry in os.scandir(str(game_dir)):
            if entry.is_file():
                total_size += entry.stat().st_size
                file_count += 1
            elif entry.is_dir():
                for root, _, files in os.walk(entry.path):
                    for f in files:
                        p = os.path.join(root, f)
                        try:
                            total_size += os.path.getsize(p)
                            file_count += 1
                        except OSError:
                            pass
    except Exception:
        pass

    if file_count == 0 or total_size == 0:
        return {"status": "not_downloaded", "size_bytes": 0, "size_formatted": "0 B"}

    # Format human-readable size
    size_str = format_bytes(total_size)

    # If manifest exists or files exist with substantial size
    if manifest.exists() or total_size > 1024 * 1024:
        return {
            "status": "downloaded",
            "size_bytes": total_size,
            "size_formatted": size_str,
            "install_dir": str(game_dir),
        }

    return {
        "status": "incomplete",
        "size_bytes": total_size,
        "size_formatted": size_str,
        "install_dir": str(game_dir),
    }


def format_bytes(size: float) -> str:
    """Convert bytes to human-readable string (KB, MB, GB, TB)."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}" if unit in ("GB", "TB") else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def populate_and_cache_games(app_ids: Set[int]) -> List[Dict[str, Any]]:
    """
    Resolve titles and build game library metadata for a set of AppIDs,
    persisting results to LIBRARY_CACHE_FILE.
    """
    if not app_ids:
        return []

    # Attempt updating app cache if needed
    if len(resolver.app_map) <= len(COMMON_STEAM_APPS):
        resolver.update_from_steam_api()

    games = []
    for aid in sorted(app_ids):
        name = resolver.resolve_name(aid)
        status_info = check_backup_status(name, aid)
        games.append({
            "appid": aid,
            "name": name,
            "image": f"https://steamcdn-a.akamaihd.net/steam/apps/{aid}/header.jpg",
            "backup_status": status_info["status"],
            "backup_size": status_info["size_formatted"],
            "backup_size_bytes": status_info["size_bytes"],
        })

    # Save to cache
    try:
        with open(LIBRARY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=2)
    except Exception as e:
        print(f"[VaporFetch] Error saving library cache: {e}")

    return games


def get_library_with_status(force_refresh: bool = False) -> Tuple[List[Dict[str, Any]], str]:
    """
    Retrieve user's owned games library along with any status or error messages.
    Uses cached licenses list, Web API if key/steamid available, or refreshes via SteamCMD.
    """
    session = get_current_session()
    username = session.get("username", "")

    if not force_refresh and LIBRARY_CACHE_FILE.exists():
        try:
            with open(LIBRARY_CACHE_FILE, "r", encoding="utf-8") as f:
                games = json.load(f)
                # Update dynamic backup status
                for g in games:
                    status_info = check_backup_status(g["name"], g["appid"])
                    g["backup_status"] = status_info["status"]
                    g["backup_size"] = status_info["size_formatted"]
                    g["backup_size_bytes"] = status_info["size_bytes"]
                return games, ""
        except Exception:
            pass

    if not username:
        return [], "Not signed in. Please log in with your Steam account."

    app_ids: Set[int] = set()
    error_msg = ""

    # 1. If we have steam_id and (access_token or api_key), query official Steam Web API GetOwnedGames
    steam_id = session.get("steam_id")
    access_token = session.get("access_token")
    settings = load_settings()
    api_key = settings.get("steam_api_key") or settings.get("api_key") or os.environ.get("STEAM_API_KEY", "")

    if steam_id and (access_token or api_key):
        try:
            query = {
                "steamid": steam_id,
                "include_appinfo": 1,
                "include_played_free_games": 1,
            }
            if access_token:
                query["access_token"] = access_token
            if api_key:
                query["key"] = api_key
            url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?{urllib.parse.urlencode(query)}"
            headers = {"User-Agent": "VaporFetch/1.0"}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for game in data.get("response", {}).get("games", []):
                    aid = game.get("appid")
                    name = game.get("name")
                    if aid:
                        app_ids.add(int(aid))
                        if name:
                            resolver.app_map[int(aid)] = name
            if app_ids:
                print(f"[VaporFetch] Retrieved {len(app_ids)} games via Steam Web API for SteamID {steam_id}")
        except Exception as e:
            print(f"[VaporFetch] Notice: Web API GetOwnedGames query: {e}")

    # 2. Try SteamCMD licenses if not populated via Web API
    if not app_ids and username:
        auth_method = session.get("auth_method", "steamcmd")
        from vaporfetch.steamcmd import auth_session, has_steamcmd_cached_credentials
        has_pwd = bool(auth_session.pending_password and auth_session.username == username)
        has_cached = has_steamcmd_cached_credentials(username)

        # If user is signed in via QR code and SteamCMD has no credentials on disk,
        # do not invoke SteamCMD blindly
        if auth_method == "qr" and not has_pwd and not has_cached:
            if not api_key:
                error_msg = (
                    "Signed in via Steam Mobile QR Code. Valve's Web API keeps games private by default; "
                    "enter your Steam Web API Key in Settings to sync your games, or sign in with Password & Steam Guard."
                )
            else:
                error_msg = (
                    "Steam Web API returned 0 games. Check that your Steam profile game details are public or your API key is valid."
                )
        else:
            cmd_app_ids = fetch_licenses(username)
            if cmd_app_ids:
                app_ids.update(cmd_app_ids)
            else:
                error_msg = auth_session.last_error or "SteamCMD returned 0 owned game licenses."

    if not app_ids:
        # If refresh returned 0 licenses, preserve existing library cache if available
        if LIBRARY_CACHE_FILE.exists():
            try:
                with open(LIBRARY_CACHE_FILE, "r", encoding="utf-8") as f:
                    cached_games = json.load(f)
                    if cached_games:
                        print(f"[VaporFetch] Refresh found 0 licenses; preserving {len(cached_games)} games from existing cache.")
                        for g in cached_games:
                            status_info = check_backup_status(g["name"], g["appid"])
                            g["backup_status"] = status_info["status"]
                            g["backup_size"] = status_info["size_formatted"]
                            g["backup_size_bytes"] = status_info["size_bytes"]
                        return cached_games, error_msg
            except Exception:
                pass
        return [], error_msg

    games = populate_and_cache_games(app_ids)
    return games, ""


def get_library(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Retrieve user's owned games list (backwards compatible)."""
    games, _ = get_library_with_status(force_refresh=force_refresh)
    return games

