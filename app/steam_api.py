import json
import httpx
from typing import List, Dict, Any, Optional
from app.config import load_settings, DATA_DIR

STEAM_API_BASE = "https://api.steampowered.com"

class SteamApiClient:
    def __init__(self):
        pass

    async def get_player_summary(
        self,
        steamid: str,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetches the user's public profile summary (persona name, avatar)."""
        settings = load_settings()
        key = api_key or settings.get("steam_api_key")

        url = f"{STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v2/"
        params = {"steamids": steamid}

        if key:
            params["key"] = key
        elif access_token:
            params["access_token"] = access_token
        else:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    players = res.json().get("response", {}).get("players", [])
                    if players:
                        p = players[0]
                        return {
                            "personaname": p.get("personaname", ""),
                            "avatar": p.get("avatarfull") or p.get("avatarmedium") or p.get("avatar", ""),
                            "profileurl": p.get("profileurl", ""),
                        }
        except Exception:
            pass
        return None

    async def get_owned_games(
        self,
        steamid: str,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches the user's owned games list via GetOwnedGames endpoint.
        Returns a list of standardized game dictionaries with headers and icons.
        """
        settings = load_settings()
        key = api_key or settings.get("steam_api_key")

        url = f"{STEAM_API_BASE}/IPlayerService/GetOwnedGames/v1/"
        params = {
            "steamid": steamid,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json"
        }

        # Try API key first, then access token
        if key:
            params["key"] = key
        elif access_token:
            params["access_token"] = access_token

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, params=params)
            
            if res.status_code == 403 or res.status_code == 401:
                raise PermissionError(
                    "Steam Web API request unauthorized. Please configure a valid Steam Web API Key in Settings or ensure profile game details are public."
                )
            
            res.raise_for_status()
            data = res.json().get("response", {})

        raw_games = data.get("games", [])
        formatted_games = []

        for g in raw_games:
            appid = g.get("appid")
            name = g.get("name") or f"App {appid}"
            icon_hash = g.get("img_icon_url")
            playtime = g.get("playtime_forever", 0)

            icon_url = (
                f"https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{icon_hash}.jpg"
                if icon_hash else ""
            )
            # Steam CDN banners
            header_url = f"https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"

            formatted_games.append({
                "appid": appid,
                "name": name,
                "playtime_forever": playtime,
                "icon_url": icon_url,
                "header_url": header_url,
            })

        # Sort alphabetically by default
        formatted_games.sort(key=lambda x: x["name"].lower())

        # Save to local cache for instant offline/one-time persistence
        try:
            cache_file = DATA_DIR / "games_cache.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(formatted_games, f)
        except Exception:
            pass

        return formatted_games

    def get_cached_games(self) -> List[Dict[str, Any]]:
        cache_file = DATA_DIR / "games_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []


steam_api_client = SteamApiClient()

