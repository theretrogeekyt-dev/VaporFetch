import os
import base64
import binascii
import hmac
import json
import time
import shutil
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Literal, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    DOWNLOAD_DIR,
    DATA_DIR,
    STEAMCMD_BIN,
    APP_VERSION,
    APP_COMMIT_SHA,
    load_settings,
    save_settings
)
from app.auth import auth_manager
from app.steam_api import steam_api_client
from app.queue_manager import queue_manager
from app.queue_manager import find_existing_install, safe_install_path
from app.steamcmd_auth import steamcmd_auth_manager
from app.steam_session import steam_session

ADMIN_USER = os.getenv("VAPORFETCH_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("VAPORFETCH_ADMIN_PASSWORD", "")

@asynccontextmanager
async def lifespan(app: FastAPI):
    queue_manager.start_worker()
    try:
        yield
    finally:
        await queue_manager.stop_worker()
        await steamcmd_auth_manager.cancel()
        await steam_session.terminate_session()

app = FastAPI(title="VaporFetch", version=APP_VERSION, lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.middleware("http")
async def protect_dashboard(request: Request, call_next):
    if request.url.path == "/healthz":
        return await call_next(request)

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        try:
            foreign_origin = origin is not None and urlsplit(origin).netloc.lower() != host.lower()
        except ValueError:
            foreign_origin = True
        if foreign_origin or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-origin requests are blocked."}, status_code=403)

    if ADMIN_PASSWORD:
        scheme, _, encoded = request.headers.get("authorization", "").partition(" ")
        expected = f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()
        try:
            valid = scheme.lower() == "basic" and hmac.compare_digest(
                base64.b64decode(encoded, validate=True), expected
            )
        except (ValueError, binascii.Error):
            valid = False
        if not valid:
            return JSONResponse(
                {"detail": "VaporFetch administrator sign-in required."},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="VaporFetch", charset="UTF-8"'},
            )

    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz", include_in_schema=False)
async def health():
    return {"status": "ok"}


# Pydantic Request Models
class PollRequest(BaseModel):
    client_id: str
    request_id: str

class QueueGame(BaseModel):
    appid: int = Field(gt=0, le=4294967295)
    name: Optional[str] = Field(default=None, max_length=512)


class QueueAddRequest(BaseModel):
    games: List[QueueGame] = Field(max_length=5000)
    require_goldberg: Optional[bool] = False

class SteamCmdAuthRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    guard_code: Optional[str] = None

class SteamCmdCodeRequest(BaseModel):
    code: str

class SettingsUpdateRequest(BaseModel):
    steam_api_key: Optional[str] = None
    force_platform: Optional[Literal["windows", "linux", "macos"]] = None
    validate_downloads: Optional[bool] = None
    enable_goldberg: Optional[bool] = None
    steamcmd_username: Optional[str] = None
    steamcmd_password: Optional[str] = None
    steamcmd_authorized: Optional[bool] = None
    custom_steamcmd_args: Optional[str] = None


def is_mobile_user_agent(user_agent: str) -> bool:
    if not user_agent:
        return False
    ua = user_agent.lower()
    return any(keyword in ua for keyword in [
        "android", "mobile", "iphone", "ipad", "ipod", "webos", "blackberry", "iemobile", "opera mini"
    ])


def _render_html(filename: str, set_cookie: Optional[str] = None) -> Response:
    filepath = STATIC_DIR / filename
    if filepath.exists():
        content = filepath.read_text(encoding="utf-8")
        resp = HTMLResponse(content=content)
        if set_cookie:
            resp.set_cookie(key="vf_view_mode", value=set_cookie, max_age=60*60*24*365, httponly=False)
        return resp
    # Fallback to index.html if mobile.html is temporarily absent
    fallback = STATIC_DIR / "index.html"
    if fallback.exists():
        return HTMLResponse(content=fallback.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>VaporFetch is initializing...</h1>")


@app.get("/")
async def serve_index(request: Request, view: Optional[str] = None):
    # 1. Query parameter override: ?view=mobile or ?view=desktop
    if view == "mobile":
        return _render_html("mobile.html", set_cookie="mobile")
    elif view == "desktop":
        return _render_html("index.html", set_cookie="desktop")

    # 2. Saved user preference in cookie
    cookie_pref = request.cookies.get("vf_view_mode")
    if cookie_pref == "mobile":
        return _render_html("mobile.html")
    elif cookie_pref == "desktop":
        return _render_html("index.html")

    # 3. Automatic detection from User-Agent (Android / mobile devices)
    user_agent = request.headers.get("user-agent", "")
    if is_mobile_user_agent(user_agent):
        return _render_html("mobile.html")
    return _render_html("index.html")


@app.get("/mobile", response_class=HTMLResponse)
async def serve_mobile(request: Request):
    return _render_html("mobile.html", set_cookie="mobile")


@app.get("/desktop", response_class=HTMLResponse)
async def serve_desktop(request: Request):
    return _render_html("index.html", set_cookie="desktop")


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
        if result.get("session"):
            result = {**result, "session": auth_manager.public_session(result["session"])}
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
        # Check if steamcmd is authorized and we have a username
        if steamcmd_authorized and settings.get("steamcmd_username"):
            from app.config import extract_account_info_from_loginusers
            acc_info = extract_account_info_from_loginusers(settings.get("steamcmd_username"))
            if acc_info and acc_info.get("steamid"):
                session = {
                    "authenticated": True,
                    "account_name": settings.get("steamcmd_username"),
                    "steamid": acc_info["steamid"],
                    "personaname": acc_info.get("personaname", settings.get("steamcmd_username")),
                    "login_time": int(time.time()),
                }
                auth_manager._current_session = session
                auth_manager._save_persisted_session()

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
        "session": auth_manager.public_session(session),
        "has_password": has_password,
        "steamcmd_authorized": steamcmd_authorized,
        "setup_complete": bool(session.get("authenticated") and (has_password or steamcmd_authorized))
    }


@app.post("/api/auth/logout")
async def logout():
    if queue_manager.active_item:
        raise HTTPException(status_code=409, detail="Cancel or finish the active download before signing out.")
    await steamcmd_auth_manager.cancel()
    await steam_session.terminate_session()
    save_settings({"steamcmd_username": "", "steamcmd_password": "", "steamcmd_authorized": False})
    auth_manager.logout()
    return {"success": True}


# SteamCMD One-and-Done Device Authorization Endpoints
@app.get("/api/auth/steamcmd/status")
async def get_steamcmd_auth_status():
    return steamcmd_auth_manager.get_status()


@app.post("/api/auth/steamcmd/authorize")
async def start_steamcmd_auth(req: SteamCmdAuthRequest):
    if queue_manager.active_item:
        raise HTTPException(status_code=409, detail="Cancel or finish the active download before authorizing SteamCMD.")
    try:
        if req.api_key and req.api_key.strip():
            save_settings({"steam_api_key": req.api_key.strip()})
        status = await steamcmd_auth_manager.start_authorization(
            username=req.username, password=req.password, guard_code=req.guard_code
        )
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
    await steamcmd_auth_manager.cancel()
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
        cached = steam_api_client.get_cached_games(steamid)
        if cached is not None:
            return {"count": len(cached), "games": cached, "cached": True}

        raise HTTPException(
            status_code=403, 
            detail="Steam Web API request unauthorized. Please configure a valid Steam Web API Key in Settings or make profile game details public."
        )
    except Exception:
        cached = steam_api_client.get_cached_games(steamid)
        if cached is not None:
            return {"count": len(cached), "games": cached, "cached": True}
        raise HTTPException(status_code=502, detail="Steam did not return the game library. Please try again.")


# ---------------- Queue & Downloader Endpoints ---------------- #

@app.get("/api/queue")
async def get_queue():
    return queue_manager.get_summary()


@app.post("/api/queue")
async def add_to_queue(req: QueueAddRequest):
    if not req.games:
        raise HTTPException(status_code=400, detail="No games specified.")
    added = queue_manager.add_to_queue(
        [game.model_dump(exclude_none=True) for game in req.games], require_goldberg=bool(req.require_goldberg)
    )
    queue_manager.broadcast("queue_update", queue_manager.get_summary())
    return {"added_count": len(added), "added": [i.model_dump() for i in added]}


@app.delete("/api/queue/{item_id}")
async def delete_queue_item(item_id: str):
    removed = queue_manager.remove_from_queue(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item not found in queue.")
    queue_manager.broadcast("queue_update", queue_manager.get_summary())
    return {"success": True}


@app.post("/api/queue/{item_id}/retry")
async def retry_queue_item(item_id: str):
    retried = queue_manager.retry_item(item_id)
    if not retried:
        raise HTTPException(status_code=404, detail="Item not found or cannot be retried.")
    queue_manager.broadcast("queue_update", queue_manager.get_summary())
    return {"success": True}


@app.post("/api/queue/clear-completed")
async def clear_completed_queue():
    queue_manager.clear_completed()
    queue_manager.broadcast("queue_update", queue_manager.get_summary())
    return {"success": True}


@app.get("/api/queue/stream")
async def stream_queue(request: Request):
    """Server-Sent Events (SSE) endpoint providing live download progress and console logs."""
    async def event_generator():
        sub_queue = await queue_manager.subscribe()
        try:
            # First send current queue summary
            init_msg = {"event": "queue_update", "data": queue_manager.get_summary()}
            yield f"data: {json.dumps(init_msg)}\n\n"

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
    return public_settings(load_settings())


def public_settings(settings: dict) -> dict:
    return {
        key: "******" if key in ("steamcmd_password", "steam_api_key") and value else value
        for key, value in settings.items()
    }


@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest):
    updates = {}
    if req.steam_api_key is not None and req.steam_api_key != "******":
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

    return public_settings(save_settings(updates))


# ---------------- Goldberg Offline Wrapper Endpoints ---------------- #

from app.goldberg import goldberg_manager

def _find_game_dir(appid: int) -> Optional[Path]:
    if any(item.appid == appid and item.status in ("running", "cancelling") for item in queue_manager.items):
        raise HTTPException(status_code=409, detail="Wait for this download to finish before managing its files.")
    for item in reversed(queue_manager.items):
        if item.appid == appid and item.status == "completed" and item.install_dir:
            path = Path(item.install_dir)
            if safe_install_path(path) and path.is_dir():
                return path
    return find_existing_install(appid)

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
    target_dir = _find_game_dir(appid)
    if target_dir is None:
        raise HTTPException(status_code=404, detail="Downloaded game folder not found in /downloads.")

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

@app.get("/api/system/version")
async def get_system_version():
    return {
        "version": APP_VERSION,
        "commit": APP_COMMIT_SHA,
        "short_commit": APP_COMMIT_SHA[:7] if APP_COMMIT_SHA != "dev" else "dev",
        "is_dev": APP_COMMIT_SHA.lower() in ("dev", "", "unknown"),
        "docker_socket_available": bool(ADMIN_PASSWORD) and container_updater.is_docker_socket_available(),
    }

@app.get("/api/system/update/check")
async def check_container_update(force: bool = False):
    update = await container_updater.check_for_updates(force=force)
    return {**update, "can_auto_update": bool(ADMIN_PASSWORD) and update["can_auto_update"]}

@app.post("/api/system/update/apply")
async def apply_container_update():
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Set VAPORFETCH_ADMIN_PASSWORD to enable in-app container updates.")
    try:
        return await container_updater.apply_update()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


