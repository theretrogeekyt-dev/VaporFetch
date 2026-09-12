import re
import os
import time
import json
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field

from app.config import (
    DOWNLOAD_DIR,
    DATA_DIR,
    STEAMCMD_BIN,
    load_settings
)

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

    def add_to_queue(self, games: List[Dict[str, Any]]) -> List[QueueItem]:
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
                step="Queued in batch"
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
        password = settings.get("steamcmd_password", "").strip()
        validate = settings.get("validate_downloads", True)
        custom_args = settings.get("custom_steamcmd_args", "").strip()

        cmd = ["/bin/bash", STEAMCMD_BIN]
        cmd.extend(["+force_install_dir", str(install_path)])

        if platform_type in ("windows", "linux", "macos"):
            cmd.extend([f"+@sSteamCmdForcePlatformType", platform_type])

        # Authentication in SteamCMD
        if username and password:
            cmd.extend(["+login", username, password])
        elif username:
            cmd.extend(["+login", username])
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

        item.log_tail.append(f"Executing: {' '.join([c if c != password else '******' for c in cmd])}")
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
                elif "Enter password for user" in line or "password:" in line:
                    item.error = "Steam password required for commercial games. Please enter your password in Settings."

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

            if returncode == 0 and not item.error:
                item.status = "completed"
                item.progress = 100.0
                item.step = "Completed"
                item.completed_at = time.time()
                item.log_tail.append(f"App {item.appid} ({item.name}) downloaded successfully to {install_path}.")
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

