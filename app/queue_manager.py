import re
import os
import time
import json
import uuid
import shutil
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field

from app.config import (
    DOWNLOAD_DIR,
    DATA_DIR,
    STEAM_HOME_DIR,
    STEAMCMD_BIN,
    load_settings,
    save_settings,
    sync_steam_credentials,
    has_steam_credentials,
    configure_steam_autologin
)
from app.auth import auth_manager

QUEUE_FILE = DATA_DIR / "queue.json"

# Regex for SteamCMD download progress:
# e.g.: "Update state (0x5) downloading, progress: 42.15 (1234567890 / 2928374610)"
PROGRESS_REGEX = re.compile(
    r"Update state \((0x[0-9a-fA-F]+)\)\s+([a-zA-Z\s]+),\s+progress:\s+([0-9.]+)\s+\((\d+)\s*\/\s*(\d+)\)"
)

def sanitize_filename(name: str) -> str:
    """Sanitizes directory names to avoid filesystem collisions or illegal characters."""
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return sanitized or "SteamGame"


async def post_process_game_directory(
    install_path: Path, 
    appid: int = 0, 
    log_tail: Optional[List[str]] = None,
    require_goldberg: bool = False
):
    """
    Cleans up post-download game directory:
    1. Flattens SteamCMD's nested steamapps/common/<Game> structure directly into install_path.
    2. Moves any appmanifest_*.acf into install_path and completely removes the steamapps folder.
    3. Renames any CommonRedist folder (_CommonRedist, CommonRedist, etc.) to 'Redistrutables'.
    4. Optionally applies Goldberg emulator for DRM-free offline play (required if require_goldberg=True).
    """
    def log(msg: str):
        if log_tail is not None:
            log_tail.append(f"[PostProcess] {msg}")

    # Step 1: Look for steamapps folder (steamapps or steam apps, case-insensitive)
    steamapps_dirs = [
        item for item in install_path.iterdir() 
        if item.is_dir() and item.name.lower() in ("steamapps", "steam apps")
    ]

    for s_dir in steamapps_dirs:
        common_dir = None
        for sub in s_dir.iterdir():
            if sub.is_dir() and sub.name.lower() == "common":
                common_dir = sub
            elif sub.is_file() and sub.name.startswith("appmanifest_"):
                # Preserve appmanifest in install_path root
                target_manifest = install_path / sub.name
                if not target_manifest.exists():
                    try:
                        shutil.move(str(sub), str(target_manifest))
                    except Exception:
                        pass

        if common_dir and common_dir.exists():
            common_entries = list(common_dir.iterdir())
            if len(common_entries) == 1 and common_entries[0].is_dir():
                game_subfolder = common_entries[0]
                log(f"Flattening '{game_subfolder.name}' directly into '{install_path.name}'...")
                for game_item in list(game_subfolder.iterdir()):
                    dest = install_path / game_item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest, ignore_errors=True)
                        else:
                            dest.unlink(missing_ok=True)
                    shutil.move(str(game_item), str(dest))
            else:
                for common_item in common_entries:
                    dest = install_path / common_item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest, ignore_errors=True)
                        else:
                            dest.unlink(missing_ok=True)
                    shutil.move(str(common_item), str(dest))

        # Remove the steamapps folder completely
        log(f"Removed '{s_dir.name}' folder.")
        shutil.rmtree(s_dir, ignore_errors=True)

    # Step 2: Rename any commonredist folder to Redistrutables
    for root, dirs, files in os.walk(install_path, topdown=False):
        for d_name in list(dirs):
            clean = d_name.lower().replace("_", "").replace("-", "").strip()
            if clean == "commonredist":
                src_dir = Path(root) / d_name
                dest_dir = Path(root) / "Redistrutables"
                if src_dir != dest_dir:
                    log(f"Renamed '{src_dir.name}' to 'Redistrutables'.")
                    if dest_dir.exists():
                        shutil.rmtree(dest_dir, ignore_errors=True)
                    src_dir.rename(dest_dir)

    # Step 3: Check if Goldberg offline emulator is enabled in settings or required for this batch
    settings = load_settings()
    should_apply_goldberg = require_goldberg or settings.get("enable_goldberg", False)
    if should_apply_goldberg and appid > 0:
        from app.goldberg import goldberg_manager
        await goldberg_manager.ensure_binaries()
        status = goldberg_manager.check_status(install_path)
        if status.get("compatible"):
            account_name = settings.get("steamcmd_username") or "Player"
            res = goldberg_manager.apply(install_path, appid=appid, account_name=account_name)
            req_note = " (Required for batch)" if require_goldberg else ""
            log(f"Applied Goldberg offline wrapper{req_note} ({res['patched_count']} DLLs patched). Original saved to .orig.")
        else:
            if require_goldberg:
                raise RuntimeError(
                    f"Goldberg patch was required for this batch, but '{install_path.name}' does not contain steam_api.dll or steam_api64.dll."
                )
            else:
                log("Game does not use standard steam_api.dll; Goldberg wrapper not applied.")


class QueueItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    appid: int
    name: str
    status: str = "queued"  # queued, running, completed, failed, cancelled
    progress: float = 0.0
    current_bytes: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0
    eta_seconds: int = 0
    step: str = "Queued"
    install_dir: str = ""
    error: Optional[str] = None
    require_goldberg: bool = False
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    log_tail: List[str] = Field(default_factory=list)


class DownloadQueueManager:
    def __init__(self):
        self.items: List[QueueItem] = []
        self.active_process: Optional[asyncio.subprocess.Process] = None
        self.active_item: Optional[QueueItem] = None
        self._subscribers: Set[asyncio.Queue] = set()
        self._worker_task: Optional[asyncio.Task] = None
        self._load_queue()

    def _load_queue(self):
        if QUEUE_FILE.exists():
            try:
                with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item_dict in data:
                        # Reset any previously running items back to queued or failed
                        if item_dict.get("status") == "running":
                            item_dict["status"] = "queued"
                            item_dict["step"] = "Queued (interrupted)"
                        self.items.append(QueueItem(**item_dict))
            except Exception as e:
                print(f"[QueueManager] Failed to load queue file: {e}")

    def _save_queue(self):
        try:
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump([item.model_dump() for item in self.items], f, indent=2)
        except Exception as e:
            print(f"[QueueManager] Failed to save queue: {e}")

    def start_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue_loop())

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q)

    async def broadcast(self, event_type: str, data: Any):
        msg = json.dumps({"event": event_type, "data": data})
        dead_queues = []
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            self._subscribers.discard(dq)

    def add_to_queue(self, games: List[Dict[str, Any]], require_goldberg: bool = False) -> List[QueueItem]:
        """Adds a list of games (appid, name) to the queue."""
        added = []
        for g in games:
            appid = int(g["appid"])
            name = str(g.get("name", f"App {appid}"))
            
            # Avoid duplicate active/queued appids
            existing = next((i for i in self.items if i.appid == appid and i.status in ("queued", "running")), None)
            if existing:
                continue

            item = QueueItem(
                appid=appid,
                name=name,
                status="queued",
                step="Queued in batch",
                require_goldberg=require_goldberg
            )
            self.items.append(item)
            added.append(item)

        self._save_queue()
        self.start_worker()
        return added

    def remove_from_queue(self, item_id: str) -> bool:
        """Removes or cancels a queue item."""
        for idx, item in enumerate(self.items):
            if item.id == item_id:
                if item.status == "running" and self.active_process:
                    try:
                        self.active_process.terminate()
                    except Exception:
                        pass
                    item.status = "cancelled"
                    item.step = "Cancelled by user"
                else:
                    self.items.pop(idx)
                self._save_queue()
                return True
        return False

    def retry_item(self, item_id: str) -> bool:
        """Resets a failed or cancelled item back to queued."""
        for item in self.items:
            if item.id == item_id and item.status in ("failed", "cancelled", "completed"):
                item.status = "queued"
                item.step = "Queued for retry"
                item.progress = 0.0
                item.error = None
                item.log_tail.clear()
                self._save_queue()
                self.start_worker()
                return True
        return False

    def clear_completed(self):
        """Removes completed and cancelled items from the list."""
        self.items = [i for i in self.items if i.status in ("queued", "running")]
        self._save_queue()

    def get_summary(self) -> Dict[str, Any]:
        return {
            "items": [item.model_dump() for item in self.items],
            "active_id": self.active_item.id if self.active_item else None
        }

    async def _process_queue_loop(self):
        while True:
            # Find first queued item
            next_item = next((i for i in self.items if i.status == "queued"), None)
            if not next_item:
                self.active_item = None
                break

            self.active_item = next_item
            await self._run_download(next_item)
            self._save_queue()
            await self.broadcast("queue_update", self.get_summary())
            await asyncio.sleep(1.0)

    async def _run_download(self, item: QueueItem):
        settings = load_settings()
        safe_name = sanitize_filename(item.name)
        install_path = DOWNLOAD_DIR / safe_name
        install_path.mkdir(parents=True, exist_ok=True)

        item.status = "running"
        item.started_at = time.time()
        item.install_dir = str(install_path)
        item.step = "Initializing SteamCMD"
        item.log_tail.append(f"Starting download for {item.name} (AppID: {item.appid})...")
        item.log_tail.append(f"Destination: {install_path}")
        self._save_queue()
        await self.broadcast("item_update", item.model_dump())

        # Construct SteamCMD command
        platform_type = settings.get("force_platform", "windows")
        username = settings.get("steamcmd_username", "").strip()
        validate = settings.get("validate_downloads", True)
        custom_args = settings.get("custom_steamcmd_args", "").strip()

        # Fallback to session account name if not explicitly set in settings
        session = auth_manager.get_session()
        if not username and session:
            username = session.get("account_name", "").strip()
        steamid = session.get("steamid", "") if session else ""

        cmd = ["/bin/bash", STEAMCMD_BIN]
        cmd.extend(["+force_install_dir", str(install_path)])

        if platform_type in ("windows", "linux", "macos"):
            cmd.extend([f"+@sSteamCmdForcePlatformType", platform_type])

        # Prepare Steam credentials and configure autologin
        if username:
            configure_steam_autologin(username, steamid)
        sync_steam_credentials()

        # Routine downloads MUST NEVER pass the password on the command line!
        # Passing raw password forces Steam to trigger a 2FA mobile approval request every time.
        # Instead, SteamCMD authenticates silently using the machine session stored in config.vdf.
        if username:
            cmd.extend(["+login", username])
            item.log_tail.append(f"Logging in as '{username}' using saved machine session (no mobile prompt)...")
        else:
            cmd.extend(["+login", "anonymous"])

        # App update command
        app_update_cmd = f"+app_update {item.appid}"
        if validate:
            app_update_cmd += " validate"
        cmd.append(app_update_cmd)

        if custom_args:
            cmd.extend(custom_args.split())

        cmd.append("+quit")

        item.log_tail.append(f"Executing: {' '.join(cmd)}")
        await self.broadcast("item_update", item.model_dump())

        last_bytes = 0
        last_time = time.time()

        proc_env = os.environ.copy()
        proc_env["HOME"] = "/home/steam"

        try:
            # Execute SteamCMD subprocess with explicit HOME and working dir
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=proc_env,
                cwd="/home/steam" if Path("/home/steam").exists() else None
            )
            self.active_process = process

            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue

                # Add to recent log tail (keep last 80 lines)
                item.log_tail.append(line)
                if len(item.log_tail) > 80:
                    item.log_tail.pop(0)

                # Parse progress
                match = PROGRESS_REGEX.search(line)
                if match:
                    state_code, state_name, pct_str, cur_b_str, tot_b_str = match.groups()
                    pct = float(pct_str)
                    cur_b = int(cur_b_str)
                    tot_b = int(tot_b_str)

                    now = time.time()
                    dt = now - last_time
                    if dt >= 0.8:
                        if cur_b >= last_bytes and dt > 0:
                            item.speed_bps = (cur_b - last_bytes) / dt
                        if item.speed_bps > 0 and tot_b > cur_b:
                            item.eta_seconds = int((tot_b - cur_b) / item.speed_bps)
                        else:
                            item.eta_seconds = 0
                        last_bytes = cur_b
                        last_time = now

                    item.progress = pct
                    item.current_bytes = cur_b
                    item.total_bytes = tot_b
                    item.step = state_name.capitalize()
                elif "Success! App" in line:
                    item.step = "Success"
                    item.progress = 100.0
                elif "ERROR!" in line or "Failed to install" in line:
                    item.error = line
                elif "No subscription" in line:
                    item.error = "Steam account does not own this game (No subscription)."
                elif (
                    "Enter password for user" in line 
                    or "password:" in line 
                    or "FAILED (Account Logon Denied)" in line
                    or "FAILED (Invalid Password)" in line
                    or "FAILED (Rate Limit Exceeded)" in line
                ):
                    item.error = "Steam authorization required. Please authorize this device once in Settings."
                    save_settings({"steamcmd_authorized": False})

                await self.broadcast("item_log", {
                    "id": item.id,
                    "line": line,
                    "progress": item.progress,
                    "step": item.step,
                    "speed_bps": item.speed_bps,
                    "eta_seconds": item.eta_seconds,
                    "current_bytes": item.current_bytes,
                    "total_bytes": item.total_bytes,
                })

            returncode = await process.wait()

            # Always synchronize any new Steam Guard sentry files or config.vdf and mark device authorized if exit code was 0
            sync_steam_credentials()
            if returncode == 0 and username and not settings.get("steamcmd_authorized"):
                save_settings({"steamcmd_authorized": True})

            if returncode == 0 and not item.error:
                item.step = "Cleaning structure"
                try:
                    await post_process_game_directory(
                        install_path, 
                        appid=item.appid, 
                        log_tail=item.log_tail, 
                        require_goldberg=item.require_goldberg
                    )
                    item.status = "completed"
                    item.progress = 100.0
                    item.step = "Completed"
                    item.completed_at = time.time()
                    item.log_tail.append(f"App {item.appid} ({item.name}) downloaded and structured successfully in {install_path}.")
                except Exception as ppe:
                    item.status = "failed"
                    item.error = str(ppe)
                    item.step = "Failed (Goldberg Required)" if item.require_goldberg and "Goldberg" in str(ppe) else "Failed (Post-process)"
                    item.log_tail.append(f"Post-processing failed: {ppe}")
            elif item.status == "cancelled":
                item.log_tail.append("Process cancelled.")
            else:
                item.status = "failed"
                # If error wasn't caught by specific pattern, find the last meaningful log message
                if not item.error:
                    candidate_lines = [
                        l for l in item.log_tail 
                        if not l.startswith("Executing:") and not l.startswith("Starting download") and not l.startswith("Destination:")
                    ]
                    last_msg = candidate_lines[-1] if candidate_lines else f"exit code {returncode}"
                    item.error = f"SteamCMD failed ({last_msg})"

                item.step = "Failed"
                item.log_tail.append(f"Download failed: {item.error}")

        except asyncio.CancelledError:
            item.status = "cancelled"
            item.step = "Cancelled"
            if self.active_process:
                try:
                    self.active_process.kill()
                except Exception:
                    pass
        except Exception as ex:
            item.status = "failed"
            item.error = str(ex)
            item.step = "Failed"
            item.log_tail.append(f"Unexpected error: {ex}")
        finally:
            self.active_process = None
            self._save_queue()
            await self.broadcast("item_update", item.model_dump())


queue_manager = DownloadQueueManager()

