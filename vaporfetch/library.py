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
    safe_write_json,
)
from vaporfetch.steamcmd import get_current_session, fetch_licenses

# Pre-populated dictionary of common Steam games for instant offline lookup
COMMON_STEAM_APPS: Dict[int, str] = {
    # Valve GoldSrc & Classic games
    10: "Counter-Strike",
    20: "Team Fortress Classic",
    30: "Day of Defeat",
    40: "Deathmatch Classic",
    50: "Half-Life: Opposing Force",
    60: "Ricochet",
    70: "Half-Life",
    80: "Counter-Strike: Condition Zero",
    100: "Counter-Strike: Condition Zero Deleted Scenes",
    130: "Half-Life: Blue Shift",
    # Valve Source games
    220: "Half-Life 2",
    240: "Counter-Strike: Source",
    280: "Half-Life: Source",
    300: "Day of Defeat: Source",
    320: "Half-Life 2: Deathmatch",
    340: "Half-Life 2: Lost Coast",
    360: "Half-Life Deathmatch: Source",
    380: "Half-Life 2: Episode One",
    400: "Portal",
    420: "Half-Life 2: Episode Two",
    440: "Team Fortress 2",
    500: "Left 4 Dead",
    550: "Left 4 Dead 2",
    570: "Dota 2",
    620: "Portal 2",
    630: "Alien Swarm",
    730: "Counter-Strike 2",
    # DOOM & Bethesda classics
    2280: "DOOM + DOOM II",
    2290: "Final DOOM",
    2300: "DOOM II",
    2310: "Quake",
    2320: "Quake II",
    2330: "Quake III Arena",
    2350: "Wolfenstein 3D",
    2360: "Return to Castle Wolfenstein",
    379720: "DOOM (2016)",
    782330: "DOOM Eternal",
    1148590: "DOOM 64",
    # Popular Steam games
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

# Known internal Steam tools, dedicated servers, and engine packages
KNOWN_TOOLS: Dict[int, str] = {
    4: "Source SDK Base",
    5: "Dedicated Server",
    7: "Steam Client",
    8: "winui2",
    9: "Half-Life Beta",
    90: "Half-Life Dedicated Server",
    105: "Half-Life Linux Dedicated Server",
    115: "Source Dedicated Server",
    205: "Source SDK",
    215: "Source SDK Base 2006",
    218: "Source SDK Base 2007",
    225: "Team Fortress 2 Dedicated Server",
    245: "Counter-Strike: Source Dedicated Server",
    255: "Day of Defeat: Source Dedicated Server",
    1007: "Steam Translation Server",
    228980: "Steamworks Common Redistributables",
}

class AppResolver:
    """Resolves Steam AppIDs to game titles using local cache, SteamSpy, and Steam Web API."""
    def __init__(self):
        self.app_map: Dict[int, str] = dict(COMMON_STEAM_APPS)
        self.app_map.update(KNOWN_TOOLS)
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
        safe_write_json(APP_CACHE_FILE, self.app_map)

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
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
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

        return False

    def resolve_name(self, appid: int) -> str:
        """Get the title for an AppID, querying SteamSpy / Steam API if missing."""
        if appid in self.app_map:
            return self.app_map[appid]

        # 1. Try SteamSpy API (reliable, fast, no Akamai 403 block)
        try:
            url = f"https://steamspy.com/api.php?request=appdetails&appid={appid}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                name = (data.get("name") or "").strip()
                if name and not name.lower().startswith("app_"):
                    self.app_map[appid] = name
                    self.save_cache()
                    return name
        except Exception:
            pass

        # 2. Try online store API lookup as fallback
        try:
            url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
    clean = re.sub(r'[\\/*?:"<>|+]', "_", name)
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
    if len(resolver.app_map) <= len(COMMON_STEAM_APPS) + len(KNOWN_TOOLS):
        resolver.update_from_steam_api()

    games = []
    for aid in sorted(app_ids):
        name = resolver.resolve_name(aid)
        is_tool = (
            aid in KNOWN_TOOLS
            or "dedicated server" in name.lower()
            or name.lower().startswith("steam client")
            or name.lower() in ("winui2", "steamworks common redistributables")
        )
        status_info = check_backup_status(name, aid)
        games.append({
            "appid": aid,
            "name": name,
            "image": f"https://steamcdn-a.akamaihd.net/steam/apps/{aid}/header.jpg",
            "backup_status": status_info["status"],
            "backup_size": status_info["size_formatted"],
            "backup_size_bytes": status_info["size_bytes"],
            "is_tool": is_tool,
        })

    # Save to cache
    safe_write_json(LIBRARY_CACHE_FILE, games)

    return games


def resolve_vanity_url(vanity: str, api_key: str) -> Optional[str]:
    """Resolve a Steam custom vanity URL or name into a 64-bit SteamID."""
    if not vanity or not api_key:
        return None
    clean = vanity.strip().rstrip("/")
    if "/" in clean:
        clean = clean.split("/")[-1]
    if clean.isdigit() and len(clean) >= 16:
        return clean
    try:
        url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={api_key}&vanityurl={urllib.parse.quote(clean)}"
        req = urllib.request.Request(url, headers={"User-Agent": "VaporFetch/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data.get("response", {})
            if res.get("success") == 1:
                return str(res.get("steamid"))
    except Exception:
        pass
    return None


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
    steam_id = session.get("steam_id", "")
    access_token = session.get("access_token", "")
    refresh_token = session.get("refresh_token", "")
    settings = load_settings()
    api_key = settings.get("steam_api_key") or settings.get("api_key") or os.environ.get("STEAM_API_KEY", "")
    custom_id = settings.get("custom_steam_id") or settings.get("steam_id", "")

    # Auto-resolve steam_id if not present in session
    if not steam_id:
        from vaporfetch.steamcmd import extract_steam_id_from_token
        steam_id = extract_steam_id_from_token(access_token) or extract_steam_id_from_token(refresh_token)

    # Check custom_steam_id in settings or vanity URL
    if not steam_id and custom_id:
        steam_id = resolve_vanity_url(custom_id, api_key) if api_key else (custom_id if custom_id.isdigit() else "")

    # Fallback to username if vanity name matches
    if not steam_id and username and api_key:
        steam_id = resolve_vanity_url(username, api_key) or ""

    # Persist resolved steam_id to session
    if steam_id and steam_id != session.get("steam_id"):
        session["steam_id"] = steam_id
        save_current_session(username, **session)

    web_api_error = ""
    api_key_valid = False

    if steam_id and (access_token or api_key):
        try:
            query = {
                "steamid": steam_id,
                "include_appinfo": 1,
                "include_played_free_games": 1,
            }
            if api_key:
                query["key"] = api_key
            elif access_token:
                query["access_token"] = access_token

            url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?{urllib.parse.urlencode(query)}"
            headers = {"User-Agent": "VaporFetch/1.0"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                api_key_valid = True
                for game in data.get("response", {}).get("games", []):
                    aid = game.get("appid")
                    name = game.get("name")
                    if aid:
                        app_ids.add(int(aid))
                        if name:
                            resolver.app_map[int(aid)] = name
            if app_ids:
                print(f"[VaporFetch] Retrieved {len(app_ids)} games via Steam Web API for SteamID {steam_id}")
            elif api_key:
                print(f"[VaporFetch] Web API key is valid, but account {steam_id} has private game details.")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                web_api_error = "The configured Steam Web API Key was rejected by Steam (HTTP 401/403). Please verify your key in Settings."
            else:
                web_api_error = f"Steam Web API error: HTTP {e.code}"
            print(f"[VaporFetch] Notice: Web API GetOwnedGames query: {e}")
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
            if web_api_error:
                error_msg = web_api_error
            elif not api_key:
                error_msg = (
                    "Signed in via Steam Mobile QR Code. Valve keeps game libraries private by default. "
                    "Enter your Steam Web API Key in Settings and set Steam Game Details to Public to sync your games, "
                    "or sign in with Password & Steam Guard."
                )
            elif api_key_valid and not app_ids:
                error_msg = (
                    "Your Steam Web API Key is valid, but your Steam account has 'Game Details' set to Private. "
                    "In Steam, go to Profile -> Edit Profile -> Privacy Settings and set 'Game Details' to Public to load your games. "
                    "Alternatively, sign in with Password & Steam Guard."
                )
            else:
                error_msg = (
                    "Signed in via Steam Mobile QR Code, but Steam Web API returned 0 games. "
                    "Check your Steam Privacy Settings to ensure 'Game Details' are set to Public, "
                    "or sign in with Password & Steam Guard."
                )
        else:
            # If active login is currently streaming licenses in the background, wait for it!
            if auth_session.fetching_licenses:
                print(f"[VaporFetch] Login session is actively syncing licenses from SteamCMD. Waiting for completion...")
                auth_session.license_event.wait(timeout=25.0)
                if auth_session.owned_app_ids:
                    app_ids.update(auth_session.owned_app_ids)

            if not app_ids:
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

