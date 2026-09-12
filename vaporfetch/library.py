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

# Allowed retail games that might otherwise trigger keywords (e.g. "Mod")
ALLOWED_GAMES: Set[int] = {
    4000,   # Garry's Mod
    362890, # Black Mesa
}

# Known internal Steam tools, runtimes, software, mods, and dedicated servers
KNOWN_NON_GAMES: Dict[int, str] = {
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
    97: "Steam Translation Server",
    228980: "Steamworks Common Redistributables",
    513: "Left 4 Dead Authoring Tools",
    563: "Left 4 Dead 2 Authoring Tools",
    564: "Left 4 Dead 2 Add-on Support",
    575: "Dota 2 - English Depot",
    576: "Dota 2 - Content Depot",
    629: "Portal 2 Authoring Tools - Beta",
    644: "Portal 2 Publishing Tool",
    746: "Counter-Strike: Global Offensive Authoring Tools",
    243750: "Source SDK Base 2013 Multiplayer",
    244630: "Source SDK Base 2013 Singleplayer",
    250820: "SteamVR",
    323910: "SteamVR Performance Test",
    356530: "SteamVR Workshop Tools",
    858210: "Steam Linux Runtime",
    1070560: "Steam Linux Runtime",
    1391110: "Steam Linux Runtime - Soldier",
    1628350: "Steam Linux Runtime - Sniper",
    1807930: "Steam Linux Runtime - Medic",
    896660: "Proton 3.7",
    961940: "Proton 3.16",
    1054830: "Proton 4.2",
    1113280: "Proton 4.11",
    1245040: "Proton 5.0",
    1420170: "Proton 5.13",
    1493710: "Proton Experimental",
    1580130: "Proton 6.3",
    1887720: "Proton 7.0",
    2180100: "Proton Hotfix",
    2230260: "Proton Next",
    2348520: "Proton 8.0",
    2805730: "Proton 9.0",
    # Known Software & Applications
    1840: "Source Filmmaker",
    365670: "Blender",
    431960: "Wallpaper Engine",
    431730: "Aseprite",
    223850: "3DMark",
    524390: "PCMark 10",
    484580: "GameMaker Studio 2",
    217370: "GameMaker: Studio",
    363890: "RPG Maker MV",
    1096900: "RPG Maker MZ",
    220700: "RPG Maker VX Ace",
    235900: "RPG Maker XP",
    362870: "RPG Maker 2003",
    383730: "RPG Maker 2000",
    286010: "VoiceAttack",
    629520: "Soundpad",
    400040: "ShareX",
    1118310: "RetroArch",
    367670: "Controller Companion",
    993090: "Lossless Scaling",
    227260: "DisplayFusion",
    1905180: "OBS Studio",
    404790: "Godot Engine",
    388080: "Borderless Gaming",
    1079260: "EVGA Precision X1",
    1009850: "OVR Advanced Settings",
    1173510: "XSOverlay",
    1494460: "Desktop+",
    1192380: "Stop Sign VR",
    908520: "fpsVR",
    382110: "Virtual Desktop",
    # Known Mods
    17500: "Zombie Panic! Source",
    17510: "Age of Chivalry",
    17520: "Synergy",
    17530: "D.I.P.R.I.P.",
    17550: "Eternal Silence",
    17570: "Pirates, Vikings, and Knights II",
    17730: "Smashball",
    218350: "Gunman Chronicles",
    223710: "Cry of Fear",
    235780: "MINERVA: Metastasis",
    258380: "Rexaura",
    280740: "Aperture Tag: The Paint Gun Testing Initiative",
    286080: "Thinking with Time Machine",
    290930: "Half-Life 2: Update",
    317400: "Portal Stories: Mel",
    365300: "Transmissions: Element 120",
    397460: "Half-Life 2: Year Long Horror",
    587650: "Half-Life 2: DownFall",
    601360: "Portal: Revolution",
    679270: "Half-Life: C.A.G.E.D.",
    714070: "Entropy : Zero",
    976620: "Enderal: Forgotten Stories",
    1014940: "Nehrim: At Fate's Edge",
    1467450: "The Chronicles of Myrtana: Archolos",
    1583720: "Entropy : Zero 2",
}
# Backward compatibility alias
KNOWN_TOOLS = KNOWN_NON_GAMES


def is_tool_or_non_game(appid: int, name: str, app_type: Optional[str] = None) -> bool:
    """
    Determine whether an AppID or title corresponds to a non-game
    (DLC, mod, software, tool, dedicated server, runtime, beta, demo, soundtrack, or unreleased package).
    Returns True if the item is NOT a standard game.
    """
    if appid in ALLOWED_GAMES:
        return False

    if appid in KNOWN_NON_GAMES:
        return True

    # Check explicit app_type parameter or cached type from Steam API / SteamSpy
    detected_type = (app_type or (resolver.app_types.get(appid, "") if "resolver" in globals() else "")).lower()
    if detected_type in (
        "dlc", "mod", "software", "tool", "demo", "music", "video",
        "series", "episode", "hardware", "application"
    ):
        return True

    clean = (name or "").strip()
    if not clean:
        return True

    # 1. Unresolved, placeholder, or unknown items
    if clean.startswith("Steam App ") or clean.startswith("SteamDB Unknown App"):
        return True
    if re.match(r"^App\s*#?\d+$", clean, re.IGNORECASE) or re.match(r"^app_\d+$", clean, re.IGNORECASE):
        return True

    lower = clean.lower()

    # 2. Known internal Valve / Steam keywords
    if (
        lower in ("winui2", "steam client", "steamworks common redistributables", "spacewar")
        or lower.startswith("steam client")
        or lower.startswith("steam linux runtime")
        or lower.startswith("proton ")
        or lower == "proton"
        or lower.startswith("steamworks ")
        or lower.startswith("source sdk")
        or lower.startswith("steamvr")
        or lower.startswith("unreleased ")
        or lower.startswith("valve internal ")
        or lower.startswith("steam test ")
        or lower.startswith("test app ")
    ):
        return True

    # 3. DLC Detection (expansion packs, season passes, cosmetics, item packs, soundtracks, artbooks)
    if re.search(
        r"\b(dlc|expansion pack|expansion pass|season pass|annual pass|battle pass|"
        r"soundtrack|ost|artbook|art book|digital artbook|digital art book|bonus content|bonus pack|"
        r"skin pack|character pack|costume pack|item pack|weapon pack|content pack|"
        r"asset pack|upgrade pack|map pack|voice pack|audio pack|music pack|"
        r"supporter pack|founder pack|founders pack|pre-order bonus|pre-purchase bonus|"
        r"special content|making of|concept art|behind the scenes|digital content|"
        r"exclusive content|cosmetic|cosmetics|bundle)\b",
        lower,
    ):
        return True
    if (
        lower.endswith(" dlc")
        or lower.endswith(" (dlc)")
        or lower.endswith(" - dlc")
        or "dlc: " in lower
        or ": dlc" in lower
        or " dlc -" in lower
    ):
        return True
    if (
        "deluxe upgrade" in lower
        or "founder upgrade" in lower
        or "supporter upgrade" in lower
        or "deluxe edition content" in lower
    ):
        return True
    if (
        "add-on support" in lower
        or "addon support" in lower
        or lower.endswith(" add-on")
        or lower.endswith(" addon")
        or lower.endswith(" (add-on)")
        or lower.endswith(" (addon)")
    ):
        return True

    # 4. Mod Detection (community mods, source mods, workshop mods)
    if (
        lower.endswith(" mod")
        or lower.endswith(" mods")
        or lower.endswith(" (mod)")
        or lower.endswith(" - mod")
        or ": mod" in lower
        or " mod: " in lower
        or " mod - " in lower
        or "- mod - " in lower
    ):
        return True
    if (
        "source mod" in lower
        or "community mod" in lower
        or "workshop mod" in lower
        or "modification" in lower
    ):
        return True

    # 5. Videos, Movies, Music, and Media Content
    if re.search(
        r"\b(video|movie|film|documentary|animation|music video|short film|live action|"
        r"cinematics?|movie pack|video collection|music album|concert|live performance)\b",
        lower,
    ):
        return True

    # 5b. Software & Utility Detection
    if re.search(
        r"\b(software|utility|utilities|benchmark|filmmaker|level editor|map editor|world editor|scenario editor)\b",
        lower,
    ):
        return True
    software_keywords = [
        "wallpaper engine",
        "godot engine",
        "rpg maker",
        "gamemaker",
        "visual novel maker",
        "blender",
        "aseprite",
        "soundpad",
        "voiceattack",
        "sharex",
        "lossless scaling",
        "displayfusion",
        "obs studio",
        "borderless gaming",
        "controller companion",
        "virtual desktop",
        "fpsvr",
        "3dmark",
        "pcmark",
        "vrmark",
        "ovr advanced settings",
        "xsoverlay",
        "desktop+",
        "stop sign vr",
    ]
    for sk in software_keywords:
        if sk in lower:
            return True
    if lower.endswith(" driver") or lower.endswith(" drivers"):
        return True

    # 6. Dedicated Servers & Server Packages
    if (
        "dedicated server" in lower
        or "linux dedicated server" in lower
        or lower.endswith(" server")
        or lower.endswith(" servers")
        or " - server" in lower
        or " server " in lower
        or lower.endswith(" ds")
    ):
        return True

    # 7. Depots, SDKs, authoring/publishing tools
    if (
        "depot" in lower
        or "authoring tool" in lower
        or "authoring tools" in lower
        or "publishing tool" in lower
        or "publishing tools" in lower
        or "creation kit" in lower
        or "devkit" in lower
        or "sdk" in lower
        or "redistributable" in lower
        or "redistributables" in lower
        or "translation server" in lower
        or "content system" in lower
    ):
        return True

    # 8. Betas, Demos, Tests, Alphas, Samples, Teasers, OSTs
    if (
        lower.endswith(" - beta")
        or lower.endswith(" beta")
        or lower.endswith(" (beta)")
        or lower.endswith(" - test")
        or lower.endswith(" test")
        or lower.endswith(" (test)")
        or lower.endswith(" - alpha")
        or lower.endswith(" alpha")
        or lower.endswith(" (alpha)")
        or lower.endswith(" - demo")
        or lower.endswith(" demo")
        or lower.endswith(" (demo)")
        or lower.endswith(" - teaser")
        or lower.endswith(" (teaser)")
        or lower.endswith(" teaser")
        or lower.endswith(" - sample")
        or lower.endswith(" (sample)")
        or lower.endswith(" sample")
        or lower.endswith(" - prototype")
        or lower.endswith(" (prototype)")
        or lower.endswith(" prototype")
        or " public test" in lower
        or " public beta" in lower
        or " closed beta" in lower
        or " open beta" in lower
        or " test server" in lower
        or " test branch" in lower
        or " beta branch" in lower
        or " ost" in lower
        or lower.endswith(" ost")
        or " (ost)" in lower
        or " - ost" in lower
        or "playtest" in lower
        or "trailer" in lower
    ):
        return True

    # 9. Standalone Tools or Editor Packages
    if (
        lower.endswith(" tool")
        or lower.endswith(" tools")
        or lower.endswith(" editor")
        or " tools -" in lower
        or " tool -" in lower
        or " tools (" in lower
        or " tool (" in lower
    ):
        return True

    return False

APP_TYPES_CACHE_FILE = DATA_DIR / "app_types_cache.json"


class AppResolver:
    """Resolves Steam AppIDs to game titles using local cache, SteamSpy, and Steam Web API."""
    def __init__(self):
        self.app_map: Dict[int, str] = dict(COMMON_STEAM_APPS)
        self.app_map.update(KNOWN_TOOLS)
        self.app_types: Dict[int, str] = {}
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
        if APP_TYPES_CACHE_FILE.exists():
            try:
                with open(APP_TYPES_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.app_types[int(k)] = v
            except Exception:
                pass

    def save_cache(self) -> None:
        safe_write_json(APP_CACHE_FILE, self.app_map)
        if self.app_types:
            safe_write_json(APP_TYPES_CACHE_FILE, self.app_types)

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
                genre = (data.get("genre") or "").strip().lower()
                if name and not name.lower().startswith("app_"):
                    self.app_map[appid] = name
                    software_genres = (
                        "utilities", "animation & modeling", "video production",
                        "game development", "design & illustration", "photo editing",
                        "audio production", "education", "software training", "web publishing"
                    )
                    if any(sg in genre for sg in software_genres):
                        self.app_types[appid] = "software"
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
                    app_data = data[str(appid)]["data"]
                    name = app_data.get("name", "").strip()
                    app_type = (app_data.get("type") or "").strip().lower()
                    if app_type:
                        self.app_types[appid] = app_type
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
    Strictly filters out non-game packages (tools, servers, runtimes, betas, depots, etc.).
    """
    if not app_ids:
        return []

    # Attempt updating app cache if needed
    if len(resolver.app_map) <= len(COMMON_STEAM_APPS) + len(KNOWN_TOOLS):
        resolver.update_from_steam_api()

    games = []
    filtered_out = []
    for aid in sorted(app_ids):
        name = resolver.resolve_name(aid)
        if is_tool_or_non_game(aid, name):
            filtered_out.append((aid, name))
            continue
        status_info = check_backup_status(name, aid)
        games.append({
            "appid": aid,
            "name": name,
            "image": f"https://steamcdn-a.akamaihd.net/steam/apps/{aid}/header.jpg",
            "backup_status": status_info["status"],
            "backup_size": status_info["size_formatted"],
            "backup_size_bytes": status_info["size_bytes"],
            "is_tool": False,
        })

    # Log summary of what was filtered
    if filtered_out:
        print(f"[VaporFetch] Filtered out {len(filtered_out)} non-game items: {', '.join(f'{aid}:{name}' for aid, name in filtered_out[:10])}" + ("..." if len(filtered_out) > 10 else ""))

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
                cached_games = json.load(f)
                clean_games = []
                # Purge any non-game tools/depots/servers and update dynamic backup status
                for g in cached_games:
                    if is_tool_or_non_game(g.get("appid", 0), g.get("name", "")):
                        continue
                    status_info = check_backup_status(g["name"], g["appid"])
                    g["backup_status"] = status_info["status"]
                    g["backup_size"] = status_info["size_formatted"]
                    g["backup_size_bytes"] = status_info["size_bytes"]
                    g["is_tool"] = False
                    clean_games.append(g)
                safe_write_json(LIBRARY_CACHE_FILE, clean_games)
                return clean_games, ""
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
    api_key = (settings.get("steam_api_key") or settings.get("api_key") or os.environ.get("STEAM_API_KEY", "")).strip().strip('"').strip("'")
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
                from vaporfetch.steamcmd import log_steamcmd
                log_steamcmd(f"Retrieved {len(app_ids)} games from Steam Web API.")
                print(f"[VaporFetch] Retrieved {len(app_ids)} games via Steam Web API for SteamID {steam_id}")
            elif api_key:
                print(f"[VaporFetch] Web API key is valid, but account {steam_id} has private game details.")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                if api_key:
                    web_api_error = "The configured Steam Web API Key was rejected by Steam (HTTP 401/403). Please verify your 32-character key at https://steamcommunity.com/dev/apikey and update it in Settings."
                else:
                    web_api_error = f"Steam Web API rejected authentication (HTTP {e.code})."
            else:
                web_api_error = f"Steam Web API error: HTTP {e.code}"
            print(f"[VaporFetch] Notice: Web API GetOwnedGames query: {e}")
        except Exception as e:
            print(f"[VaporFetch] Notice: Web API GetOwnedGames query: {e}")

    # 1b. Try Steam Community XML games feed (no API key needed for public libraries or with session cookie)
    if not app_ids and steam_id:
        comm_candidates = [
            f"https://steamcommunity.com/profiles/{steam_id}/games?tab=all&xml=1"
        ]
        if custom_id and not custom_id.isdigit():
            comm_candidates.append(f"https://steamcommunity.com/id/{custom_id}/games?tab=all&xml=1")
        if username and username != custom_id:
            comm_candidates.append(f"https://steamcommunity.com/id/{username}/games?tab=all&xml=1")

        web_cookie = session.get("web_cookie", "")
        for curl in comm_candidates:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                if web_cookie:
                    headers["Cookie"] = web_cookie
                elif access_token:
                    headers["Cookie"] = f"steamLoginSecure={steam_id}%7C%7C{access_token}"
                req = urllib.request.Request(curl, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    xml_content = resp.read().decode("utf-8", errors="replace")
                    if "<games>" in xml_content:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(xml_content)
                        for g in root.findall(".//game"):
                            aid = g.findtext("appID")
                            name = g.findtext("name")
                            if aid and aid.isdigit():
                                app_ids.add(int(aid))
                                if name:
                                    resolver.app_map[int(aid)] = name
                        if app_ids:
                            from vaporfetch.steamcmd import log_steamcmd
                            log_steamcmd(f"Retrieved {len(app_ids)} games from Steam Community profile.")
                            print(f"[VaporFetch] Retrieved {len(app_ids)} games via Steam Community feed for {steam_id}")
                            break
            except Exception as e:
                print(f"[VaporFetch] Notice: Steam Community games feed query: {e}")

    # 2. Try SteamCMD licenses if not populated via Web API or Community XML
    if not app_ids and username:
        auth_method = session.get("auth_method", "steamcmd")
        from vaporfetch.steamcmd import auth_session, has_steamcmd_cached_credentials
        has_pwd = bool(auth_session.pending_password and auth_session.username == username)
        has_cached = has_steamcmd_cached_credentials(username)

        # If user is signed in via QR code and SteamCMD has no credentials on disk,
        # do not invoke SteamCMD blindly
        if auth_method == "qr" and not has_pwd and not has_cached:
            if api_key and web_api_error:
                error_msg = web_api_error
            elif not api_key:
                error_msg = (
                    "Signed in via Steam Mobile QR Code. Valve keeps game libraries private by default. "
                    "In Steam, go to Profile -> Edit Profile -> Privacy Settings and set 'Game Details' to Public to sync your games, "
                    "or click 'Account' and use 'Sign In' (Password & Steam Guard) to sync games directly and enable downloads."
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
            from vaporfetch.steamcmd import log_steamcmd
            log_steamcmd(f"Notice: {error_msg}")
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
                        clean_cached = []
                        for g in cached_games:
                            if is_tool_or_non_game(g.get("appid", 0), g.get("name", "")):
                                continue
                            status_info = check_backup_status(g["name"], g["appid"])
                            g["backup_status"] = status_info["status"]
                            g["backup_size"] = status_info["size_formatted"]
                            g["backup_size_bytes"] = status_info["size_bytes"]
                            g["is_tool"] = False
                            clean_cached.append(g)
                        safe_write_json(LIBRARY_CACHE_FILE, clean_cached)
                        print(f"[VaporFetch] Refresh found 0 licenses; preserving {len(clean_cached)} games from existing cache.")
                        return clean_cached, error_msg
            except Exception:
                pass
        return [], error_msg

    games = populate_and_cache_games(app_ids)
    return games, ""


def get_library(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Retrieve user's owned games list (backwards compatible)."""
    games, _ = get_library_with_status(force_refresh=force_refresh)
    return games

