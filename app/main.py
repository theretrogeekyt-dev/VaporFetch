import os
import shutil
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional, Literal
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    DOWNLOAD_DIR,
    DATA_DIR,
    STEAMCMD_BIN,
    load_settings,
    save_settings
)
from app.auth import auth_manager
from app.steam_api import steam_api_client
from app.queue_manager import queue_manager
from app.steamcmd_auth import steamcmd_auth_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Resume any pending downloads on startup
    queue_manager.start_worker()
    yield

app = FastAPI(title="VaporFetch", version="1.0.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Pydantic Request Models
class PollRequest(BaseModel):
    client_id: str
    request_id: str

class QueueAddRequest(BaseModel):
    games: List[Dict[str, Any]]
    require_goldberg: Optional[bool] = False

class SteamCmdAuthRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None

class SteamCmdCodeRequest(BaseModel):
    code: str

class SettingsUpdateRequest(BaseModel):
    steam_api_key: Optional[str] = None
    force_platform: Optional[str] = None
    validate_downloads: Optional[bool] = None
    enable_goldberg: Optional[bool] = None
    steamcmd_username: Optional[str] = None
    steamcmd_password: Optional[str] = None
    steamcmd_authorized: Optional[bool] = None
    custom_steamcmd_args: Optional[str] = None


def _load_web_ui_html() -> str:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<h1>VaporFetch is initializing...</h1>"


MOBILE_USER_AGENT_HINTS = (
    "android",
    "iphone",
    "ipad",
    "ipod",
    "mobile",
    "blackberry",
    "windows phone",
)


def _is_mobile_request(request: Request) -> bool:
    user_agent = request.headers.get("user-agent", "").lower()
    if not user_agent:
        return False
    return any(hint in user_agent for hint in MOBILE_USER_AGENT_HINTS)


def _build_mobile_redirect_url(request: Request) -> str:
    params = [(k, v) for k, v in request.query_params.multi_items() if k != "mode"]
    if not params:
        return "/mobile"
    return f"/mobile?{urlencode(params, doseq=True)}"


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request, mode: Optional[Literal["desktop", "mobile"]] = None):
    if mode == "mobile":
        return RedirectResponse(url=_build_mobile_redirect_url(request), status_code=302)
    if mode != "desktop" and _is_mobile_request(request):
        return RedirectResponse(url=_build_mobile_redirect_url(request), status_code=302)
    return HTMLResponse(content=_load_web_ui_html())


@app.get("/mobile", response_class=HTMLResponse)
async def serve_mobile_index():
    return HTMLResponse(content=_load_web_ui_html())


@app.on_event("shutdown")
async def shutdown_event():
    from app.steam_session import steam_session
    await steam_session.terminate_session()


# ---------------- Auth Endpoints ---------------- #

@app.post("/api/auth/qr/begin")
async def begin_qr_auth():
    try:
        data = await auth_manager.begin_qr_auth()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to begin QR auth session: {str(e)}")


@app.post("/api/auth/qr/poll")
async def poll_qr_auth(req: PollRequest):
    try:
        result = await auth_manager.poll_qr_auth(req.client_id, req.request_id)
        if result.get("status") == "confirmed":
            # Fetch profile details (avatar, persona name)
            session = result.get("session", {})
            steamid = session.get("steamid")
            if steamid:
                profile = await steam_api_client.get_player_summary(
                    steamid=steamid,
                    access_token=session.get("access_token")
                )
                if profile:
                    session.update(profile)
                    auth_manager._current_session = session
                    auth_manager._save_persisted_session()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Polling QR auth failed: {str(e)}")


@app.get("/api/auth/session")
async def get_session():
    session = auth_manager.get_session()
    settings = load_settings()
    has_password = bool(settings.get("steamcmd_password"))
    auth_status = steamcmd_auth_manager.get_status()
    steamcmd_authorized = auth_status["authorized"]

    if not session:
        return {
            "authenticated": False,
            "has_password": has_password,
            "steamcmd_authorized": steamcmd_authorized,
            "setup_complete": False
        }
    
    # If persona/avatar not fetched yet, try fetching
    if "personaname" not in session and session.get("steamid"):
        profile = await steam_api_client.get_player_summary(
            steamid=session["steamid"],
            access_token=session.get("access_token")
        )
        if profile:
            session.update(profile)
            auth_manager._current_session = session
            auth_manager._save_persisted_session()

    return {
        "authenticated": True,
        "session": session,
        "has_password": has_password,
        "steamcmd_authorized": steamcmd_authorized,
        "setup_complete": bool(session.get("authenticated") and (has_password or steamcmd_authorized))
    }


@app.post("/api/auth/logout")
async def logout():
    auth_manager.logout()
    return {"success": True}


# SteamCMD One-and-Done Device Authorization Endpoints
@app.get("/api/auth/steamcmd/status")
async def get_steamcmd_auth_status():
    return steamcmd_auth_manager.get_status()


@app.post("/api/auth/steamcmd/authorize")
async def start_steamcmd_auth(req: SteamCmdAuthRequest):
    try:
        status = await steamcmd_auth_manager.start_authorization(username=req.username, password=req.password)
        return status
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start SteamCMD authorization: {e}")


@app.post("/api/auth/steamcmd/code")
async def submit_steamcmd_code(req: SteamCmdCodeRequest):
    try:
        status = await steamcmd_auth_manager.send_code(req.code)
        return status
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send code to SteamCMD: {e}")


@app.post("/api/auth/steamcmd/cancel")
async def cancel_steamcmd_auth():
    steamcmd_auth_manager.cancel()
    return {"success": True}


# ---------------- Game Library Endpoints ---------------- #

@app.get("/api/games")
async def get_owned_games():
    session = auth_manager.get_session()
    if not session or not session.get("steamid"):
        raise HTTPException(status_code=401, detail="User is not authenticated with Steam.")

    steamid = session["steamid"]
    access_token = session.get("access_token")

    try:
        games = await steam_api_client.get_owned_games(
            steamid=steamid,
            access_token=access_token
        )
        return {"count": len(games), "games": games}
    except PermissionError:
        # Attempt automatic token refresh
        new_token = await auth_manager.refresh_access_token()
        if new_token:
            try:
                games = await steam_api_client.get_owned_games(
                    steamid=steamid,
                    access_token=new_token
                )
                return {"count": len(games), "games": games}
            except Exception:
                pass

        # Fallback to local cached games
        cached = steam_api_client.get_cached_games()
        if cached:
            return {"count": len(cached), "games": cached, "cached": True}

        raise HTTPException(
            status_code=403, 
            detail="Steam Web API request unauthorized. Please configure a valid Steam Web API Key in Settings or make profile game details public."
        )
    except Exception as e:
        cached = steam_api_client.get_cached_games()
        if cached:
            return {"count": len(cached), "games": cached, "cached": True}
        raise HTTPException(status_code=500, detail=f"Failed to fetch games library: {str(e)}")


# ---------------- Queue & Downloader Endpoints ---------------- #

@app.get("/api/queue")
async def get_queue():
    return queue_manager.get_summary()


@app.post("/api/queue")
async def add_to_queue(req: QueueAddRequest):
    if not req.games:
        raise HTTPException(status_code=400, detail="No games specified.")
    added = queue_manager.add_to_queue(req.games, require_goldberg=bool(req.require_goldberg))
    return {"added_count": len(added), "added": [i.model_dump() for i in added]}


@app.delete("/api/queue/{item_id}")
async def delete_queue_item(item_id: str):
    removed = queue_manager.remove_from_queue(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item not found in queue.")
    return {"success": True}


@app.post("/api/queue/{item_id}/retry")
async def retry_queue_item(item_id: str):
    retried = queue_manager.retry_item(item_id)
    if not retried:
        raise HTTPException(status_code=404, detail="Item not found or cannot be retried.")
    return {"success": True}


@app.post("/api/queue/clear-completed")
async def clear_completed_queue():
    queue_manager.clear_completed()
    return {"success": True}


@app.get("/api/queue/stream")
async def stream_queue(request: Request):
    """Server-Sent Events (SSE) endpoint providing live download progress and console logs."""
    sub_queue = await queue_manager.subscribe()

    async def event_generator():
        try:
            # First send current queue summary
            init_msg = {"event": "queue_update", "data": queue_manager.get_summary()}
            yield f"data: {json_dumps(init_msg)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(sub_queue.get(), timeout=20.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat comment to keep connection alive
                    yield ": heartbeat\n\n"
        finally:
            queue_manager.unsubscribe(sub_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

import json
def json_dumps(obj):
    return json.dumps(obj)


# ---------------- System & Settings Endpoints ---------------- #

@app.get("/api/system/status")
async def get_system_status():
    total, used, free = 0, 0, 0
    pct = 0.0
    try:
        usage = shutil.disk_usage(DOWNLOAD_DIR)
        total = usage.total
        used = usage.used
        free = usage.free
        if total > 0:
            pct = round((used / total) * 100, 1)
    except Exception:
        pass

    return {
        "download_dir": str(DOWNLOAD_DIR),
        "data_dir": str(DATA_DIR),
        "steamcmd_bin": STEAMCMD_BIN,
        "disk": {
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "used_percent": pct,
        },
        "puid": os.getenv("PUID", "1000"),
        "pgid": os.getenv("PGID", "1000"),
    }


@app.get("/api/settings")
async def get_settings():
    settings = load_settings()
    # Mask password
    masked = settings.copy()
    if masked.get("steamcmd_password"):
        masked["steamcmd_password"] = "******"
    return masked


@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest):
    updates = {}
    if req.steam_api_key is not None:
        updates["steam_api_key"] = req.steam_api_key.strip()
    if req.force_platform is not None:
        updates["force_platform"] = req.force_platform
    if req.validate_downloads is not None:
        updates["validate_downloads"] = req.validate_downloads
    if req.enable_goldberg is not None:
        updates["enable_goldberg"] = req.enable_goldberg
    if req.steamcmd_username is not None:
        updates["steamcmd_username"] = req.steamcmd_username.strip()
    if req.steamcmd_password is not None and req.steamcmd_password != "******":
        updates["steamcmd_password"] = req.steamcmd_password
    if req.steamcmd_authorized is not None:
        updates["steamcmd_authorized"] = req.steamcmd_authorized
    if req.custom_steamcmd_args is not None:
        updates["custom_steamcmd_args"] = req.custom_steamcmd_args.strip()

    updated = save_settings(updates)
    masked = updated.copy()
    if masked.get("steamcmd_password"):
        masked["steamcmd_password"] = "******"
    return masked


# ---------------- Goldberg Offline Wrapper Endpoints ---------------- #

from app.goldberg import goldberg_manager

def _find_game_dir(appid: int) -> Optional[Path]:
    for item in queue_manager.items:
        if item.appid == appid and item.install_dir and Path(item.install_dir).exists():
            return Path(item.install_dir)
    try:
        if DOWNLOAD_DIR.exists():
            for child in DOWNLOAD_DIR.iterdir():
                if not child.is_dir():
                    continue
                if (child / f"appmanifest_{appid}.acf").exists():
                    return child
                appid_file = child / "steam_appid.txt"
                if appid_file.exists():
                    try:
                        if appid_file.read_text(encoding="utf-8", errors="ignore").strip() == str(appid):
                            return child
                    except Exception:
                        pass
    except Exception:
        pass
    return None

@app.get("/api/games/{appid}/goldberg")
async def get_goldberg_status(appid: int):
    target_dir = _find_game_dir(appid)
    if not target_dir or not target_dir.exists():
        raise HTTPException(status_code=404, detail="Downloaded game folder not found in /downloads.")
    status = goldberg_manager.check_status(target_dir)
    status["install_dir"] = str(target_dir)
    return status

@app.post("/api/games/{appid}/goldberg/apply")
async def apply_goldberg(appid: int):
    target_dir = _find_game_dir(appid)
    if not target_dir or not target_dir.exists():
        raise HTTPException(status_code=404, detail="Downloaded game folder not found in /downloads.")
    
    settings = load_settings()
    account_name = settings.get("steamcmd_username") or "Player"
    await goldberg_manager.ensure_binaries()

    if not goldberg_manager.is_available():
        raise HTTPException(
            status_code=500,
            detail="Goldberg emulator binaries (steam_api.dll / steam_api64.dll) could not be downloaded or found. Please place them into your NAS data folder under 'goldberg/' or check container internet connectivity."
        )

    try:
        res = goldberg_manager.apply(target_dir, appid=appid, account_name=account_name)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/games/{appid}/goldberg/revert")
async def revert_goldberg(appid: int):
    target_dir = _find_game_dir(appid)
    if not target_dir or not target_dir.exists():
        raise HTTPException(status_code=404, detail="Downloaded game folder not found in /downloads.")

    try:
        res = goldberg_manager.revert(target_dir)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/goldberg/status")
async def get_goldberg_system_status():
    is_ready = goldberg_manager.is_available()
    return {
        "available": is_ready,
        "dll32_path": str(goldberg_manager.dll32_path) if is_ready else None,
        "dll64_path": str(goldberg_manager.dll64_path) if is_ready else None,
        "data_dir": str(goldberg_manager.dir)
    }

@app.post("/api/goldberg/download")
async def trigger_goldberg_download():
    success = await goldberg_manager.ensure_binaries()
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to download Goldberg binaries from online mirrors. Check your container internet connection or manually place steam_api.dll and steam_api64.dll in your /app/data/goldberg directory."
        )
    return {"success": True, "message": "Goldberg binaries downloaded and ready."}


# ---------------- System Version & Container Updater Endpoints ---------------- #

from app.updater import container_updater
from app.config import APP_VERSION, APP_COMMIT_SHA

@app.get("/api/system/version")
async def get_system_version():
    return {
        "version": APP_VERSION,
        "commit": APP_COMMIT_SHA,
        "short_commit": APP_COMMIT_SHA[:7] if APP_COMMIT_SHA != "dev" else "dev",
        "is_dev": APP_COMMIT_SHA.lower() in ("dev", "", "unknown"),
        "docker_socket_available": container_updater.is_docker_socket_available(),
    }

@app.get("/api/system/update/check")
async def check_container_update(force: bool = False):
    return await container_updater.check_for_updates(force=force)

@app.post("/api/system/update/apply")
async def apply_container_update():
    try:
        return await container_updater.apply_update()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
