import os
import json
import queue
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from fastapi import FastAPI, Request, HTTPException, Query
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
    from pydantic import BaseModel
except ImportError:
    # Allows module to be imported even if fastapi is not yet installed in host environment
    FastAPI = None
    BaseModel = object

from vaporfetch.config import (
    load_settings,
    save_settings,
    get_storage_stats,
    DATA_DIR,
    DOWNLOADS_DIR,
)
from vaporfetch.steamcmd import (
    get_current_session,
    start_login,
    submit_2fa_code,
    clear_session,
    auth_session,
    begin_qr_login,
    poll_qr_login,
    has_steamcmd_cached_credentials,
)
from vaporfetch.library import (
    get_library,
    get_library_with_status,
    resolver,
    check_backup_status,
)
from vaporfetch.downloader import manager

STATIC_DIR = Path(__file__).parent / "static"

if FastAPI is not None:
    app = FastAPI(title="VaporFetch", description="Steam Game Downloader & Backup Manager")

    # Request models
    class LoginRequest(BaseModel):
        username: str
        password: Optional[str] = None
        code: Optional[str] = None

    class TwoFactorRequest(BaseModel):
        code: str

    class QRPollRequest(BaseModel):
        client_id: str
        request_id: str

    class QueueAddRequest(BaseModel):
        appid: Optional[int] = None
        name: Optional[str] = None
        platform: Optional[str] = None
        appids: Optional[List[int]] = None
        all_games: Optional[bool] = False

    class QueueRemoveRequest(BaseModel):
        appid: int

    class SettingsUpdateRequest(BaseModel):
        default_platform: Optional[str] = None
        validate_downloads: Optional[bool] = None
        folder_format: Optional[str] = None
        steam_api_key: Optional[str] = None
        custom_steam_id: Optional[str] = None

    @app.middleware("http")
    async def add_cache_control_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Static assets
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse("<h1>VaporFetch</h1><p>Static files missing.</p>")

    @app.get("/api/status")
    async def get_status():
        session = get_current_session()
        settings = load_settings()
        api_key = settings.get("steam_api_key") or settings.get("api_key") or os.environ.get("STEAM_API_KEY", "")
        session["has_api_key"] = bool(api_key)
        session["auth_method"] = session.get("auth_method", "qr")
        username = session.get("username", "")
        session["has_steamcmd_auth"] = bool(session.get("logged_in") and username)
        return {
            "session": session,
            "auth_state": {
                "status": "logged_in" if session.get("logged_in") else "idle",
                "prompt": "",
                "error": "",
            },
            "queue_state": manager.get_queue_state(),
            "storage": get_storage_stats(),
        }

    @app.get("/api/login/status")
    async def login_status_endpoint():
        session = get_current_session()
        return {
            "status": "logged_in" if session.get("logged_in") else auth_session.status,
            "prompt": auth_session.prompt_message,
            "error": auth_session.error_message,
            "two_factor_type": auth_session.two_factor_type,
        }

    @app.post("/api/login")
    async def login_endpoint(payload: LoginRequest):
        return {"status": "qr_required", "message": "Please sign in using Steam Mobile QR Code."}

    @app.post("/api/login/2fa")
    async def two_factor_endpoint(payload: TwoFactorRequest):
        return {"status": "qr_required", "message": "Please sign in using Steam Mobile QR Code."}

    @app.post("/api/login/qr/begin")
    async def qr_begin_endpoint():
        res = begin_qr_login()
        if res.get("status") == "failed":
            raise HTTPException(status_code=500, detail=res.get("error", "Failed to start QR session"))
        return res

    @app.post("/api/login/qr/poll")
    async def qr_poll_endpoint(payload: QRPollRequest):
        if not payload.client_id or not payload.request_id:
            raise HTTPException(status_code=400, detail="client_id and request_id are required")
        res = poll_qr_login(payload.client_id.strip(), payload.request_id.strip())
        return res

    @app.post("/api/logout")
    async def logout_endpoint():
        clear_session()
        return {"status": "ok", "message": "Logged out successfully"}

    @app.get("/api/library")
    async def get_library_endpoint(refresh: bool = False):
        games, error = get_library_with_status(force_refresh=refresh)
        return {
            "count": len(games),
            "games": games,
            "error": error,
        }

    @app.post("/api/library/refresh")
    async def refresh_library_endpoint():
        games, error = get_library_with_status(force_refresh=True)
        return {
            "count": len(games),
            "games": games,
            "error": error,
        }

    @app.get("/api/queue")
    async def get_queue_endpoint():
        return manager.get_queue_state()

    @app.post("/api/queue/add")
    async def add_queue_endpoint(payload: QueueAddRequest):
        if payload.all_games:
            library = get_library(force_refresh=False)
            items = [{"appid": g["appid"], "name": g["name"]} for g in library]
            added = manager.add_batch(items, platform=payload.platform)
            return {"status": "ok", "queued_count": added, "message": f"Queued {added} games from entire library."}

        if payload.appids:
            library_map = {g["appid"]: g["name"] for g in get_library(force_refresh=False)}
            items = [{"appid": aid, "name": library_map.get(aid) or resolver.resolve_name(aid)} for aid in payload.appids]
            added = manager.add_batch(items, platform=payload.platform)
            return {"status": "ok", "queued_count": added, "message": f"Queued {added} selected games."}

        if payload.appid:
            success = manager.add_to_queue(payload.appid, payload.name, payload.platform)
            if success:
                return {"status": "ok", "message": f"App {payload.appid} queued."}
            else:
                return {"status": "exists", "message": f"App {payload.appid} is already in the queue."}

        raise HTTPException(status_code=400, detail="No appid or all_games flag provided")

    @app.post("/api/queue/remove")
    async def remove_queue_endpoint(payload: QueueRemoveRequest):
        removed = manager.remove_from_queue(payload.appid)
        return {"status": "ok", "removed": removed}

    @app.post("/api/queue/cancel")
    async def cancel_queue_endpoint():
        cancelled = manager.cancel_current()
        return {"status": "ok", "cancelled": cancelled}

    @app.post("/api/queue/clear")
    async def clear_queue_endpoint():
        manager.clear_queue()
        return {"status": "ok", "message": "Queue cleared"}

    @app.get("/api/settings")
    async def get_settings_endpoint():
        return load_settings()

    @app.post("/api/settings")
    async def update_settings_endpoint(payload: SettingsUpdateRequest):
        updates = {k: v for k, v in payload.dict().items() if v is not None}
        save_settings(updates)
        return {"status": "ok", "settings": load_settings()}

    @app.get("/api/events")
    async def events_endpoint(request: Request):
        """Server-Sent Events (SSE) stream for live download progress, logs, and queue events."""
        async def event_generator():
            q = manager.subscribe()
            try:
                # Send initial state and recent logs
                initial_data = json.dumps({"type": "queue_update", "data": manager.get_queue_state()})
                yield f"data: {initial_data}\n\n"

                for log_line in list(manager.log_history)[-50:]:
                    yield f"data: {json.dumps({'type': 'log', 'data': log_line})}\n\n"

                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        # Non-blocking pop with short timeout
                        loop = asyncio.get_event_loop()
                        msg = await loop.run_in_executor(None, lambda: q.get(timeout=1.0))
                        yield f"data: {json.dumps(msg)}\n\n"
                    except queue.Empty:
                        yield ": ping\n\n"
            finally:
                manager.unsubscribe(q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
else:
    app = None


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Start the uvicorn web server."""
    import uvicorn
    uvicorn.run("vaporfetch.web.server:app", host=host, port=port, log_level="info")

if __name__ == "__main__":
    run_server()

