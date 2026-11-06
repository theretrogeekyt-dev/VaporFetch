import re
import time
import json
import uuid
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field

from app.config import DOWNLOAD_DIR, DATA_DIR, load_settings
from app.auth import auth_manager
from app.steam_session import steam_session
from app.storage import write_json

QUEUE_FILE = DATA_DIR / "queue.json"
SAVED_STEAMAPPS = ".vaporfetch-steamapps"
logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Make a bounded, portable NAS directory name."""
    clean = re.sub(r'[\\/*?:"<>|\x00-\x1f\x7f]', "", name)
    return clean.encode("utf-8")[:180].decode("utf-8", errors="ignore").strip(" .") or "SteamGame"


def safe_install_path(path: Path) -> bool:
    """Game operations may only target real, immediate children of the download root."""
    try:
        return (
            path.parent.resolve() == DOWNLOAD_DIR.resolve()
            and path.resolve().parent == DOWNLOAD_DIR.resolve()
            and path.resolve().name == path.name
            and not path.is_symlink()
        )
    except (OSError, RuntimeError):
        return False


def find_existing_install(appid: int) -> Optional[Path]:
    manifest = f"appmanifest_{appid}.acf"
    for child in DOWNLOAD_DIR.iterdir():
        if child.is_dir() and safe_install_path(child):
            if any((child / directory / manifest).is_file() for directory in ("", "steamapps", SAVED_STEAMAPPS)):
                return child
    return None


def steamapps_is_metadata_only(steamapps: Path, appid: int) -> bool:
    """Check for the game's manifest and empty directories only."""
    if steamapps.is_symlink() or not steamapps.is_dir():
        return False
    for entry in steamapps.iterdir():
        if entry.is_symlink():
            return False
        if entry.name == f"appmanifest_{appid}.acf" and entry.is_file():
            continue
        if entry.is_dir() and not any(entry.iterdir()):
            continue
        return False
    return True


def restore_steamapps(install_path: Path, log_tail: List[str]) -> None:
    saved = install_path / SAVED_STEAMAPPS
    if saved.is_symlink() or not saved.is_dir():
        return
    steamapps = install_path / "steamapps"
    if steamapps.exists() or steamapps.is_symlink():
        log_tail.append("Keeping existing steamapps and its separate saved copy.")
        return
    saved.rename(steamapps)


async def archive_steamapps(install_path: Path, appid: int, log_tail: List[str]) -> None:
    steamapps = install_path / "steamapps"
    saved = install_path / SAVED_STEAMAPPS
    try:
        if saved.exists() or saved.is_symlink() or not steamapps_is_metadata_only(steamapps, appid):
            return
        # Give SteamCMD a chance to flush its install state before moving the directory.
        await steam_session.terminate_session()
        if steamapps_is_metadata_only(steamapps, appid) and not (saved.exists() or saved.is_symlink()):
            steamapps.rename(saved)
            log_tail.append("Moved SteamCMD metadata into a hidden folder for future updates.")
    except OSError as exc:
        log_tail.append(f"Could not tidy SteamCMD's folder: {exc}")


async def post_process_game_directory(
    install_path: Path, appid: int, log_tail: List[str], require_goldberg: bool = False
):
    settings = load_settings()
    if not (require_goldberg or settings.get("enable_goldberg", False)):
        return

    from app.goldberg import goldberg_manager

    try:
        if not goldberg_manager.check_status(install_path).get("compatible"):
            log_tail.append("[PostProcess] Offline wrapper skipped. No compatible Steamworks DLLs found.")
            return
        await goldberg_manager.ensure_binaries()
        result = goldberg_manager.apply(
            install_path, appid=appid, account_name=settings.get("steamcmd_username") or "Player"
        )
        log_tail.append(f"[PostProcess] Offline wrapper applied to {result['patched_count']} DLLs.")
    except Exception as exc:
        if require_goldberg:
            raise RuntimeError(f"Download succeeded, but the offline wrapper failed: {exc}") from exc
        log_tail.append(f"[PostProcess] Offline wrapper could not be applied: {exc}")


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
        self.active_item: Optional[QueueItem] = None
        self._subscribers: Set[asyncio.Queue] = set()
        self._worker_task: Optional[asyncio.Task] = None
        self._download_task: Optional[asyncio.Task] = None
        self._load_queue()

    def _load_queue(self):
        if not QUEUE_FILE.exists():
            return
        try:
            records = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                raise ValueError("Queue data must be an array.")
        except (OSError, ValueError):
            logger.exception("Could not read the download queue")
            return

        for record in records:
            try:
                item = QueueItem.model_validate(record)
            except ValueError:
                logger.warning("Skipping an invalid download queue record")
                continue
            if item.status in ("running", "cancelling"):
                cancelled = item.status == "cancelling"
                self._reset_item(item, "Cancelled by user" if cancelled else "Queued (interrupted)")
                if cancelled:
                    item.status = "cancelled"
            self.items.append(item)

    def _save_queue(self):
        write_json(QUEUE_FILE, [item.model_dump() for item in self.items])

    def _save_worker_state(self):
        try:
            self._save_queue()
        except OSError:
            logger.exception("Could not persist the download queue")

    @staticmethod
    def _reset_item(item: QueueItem, step: str):
        item.status = "queued"
        item.step = step
        item.progress = 0
        item.current_bytes = item.total_bytes = item.eta_seconds = 0
        item.speed_bps = 0
        item.started_at = item.completed_at = item.error = None
        item.log_tail.clear()

    def start_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue_loop())

    async def stop_worker(self):
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)

    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=128)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self._subscribers.discard(queue)

    def broadcast(self, event_type: str, data: Any):
        message = json.dumps({"event": event_type, "data": data})
        for queue in self._subscribers:
            if queue.full():
                # Replace stale telemetry with an authoritative snapshot.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(json.dumps({"event": "queue_update", "data": self.get_summary()}))
            queue.put_nowait(message)

    def add_to_queue(self, games: List[Dict[str, Any]], require_goldberg: bool = False) -> List[QueueItem]:
        """Adds a list of games (appid, name) to the queue."""
        added = []
        for g in games:
            appid = int(g["appid"])
            name = str(g.get("name", f"App {appid}"))
            
            # Avoid duplicate active/queued appids
            existing = next((i for i in self.items if i.appid == appid and i.status in ("queued", "running", "cancelling")), None)
            if existing or any(item.appid == appid for item in added):
                continue

            item = QueueItem(
                appid=appid,
                name=name,
                status="queued",
                step="Queued in batch",
                require_goldberg=require_goldberg
            )
            added.append(item)

        if added:
            previous = self.items
            self.items = [*previous, *added]
            try:
                self._save_queue()
            except OSError:
                self.items = previous
                raise
            self.start_worker()
        return added

    def remove_from_queue(self, item_id: str) -> bool:
        for index, item in enumerate(self.items):
            if item.id != item_id:
                continue
            if item.status == "cancelling":
                return True
            if item is self.active_item and self._download_task and not self._download_task.done():
                previous_status, previous_step = item.status, item.step
                item.status, item.step = "cancelling", "Cancelling"
                try:
                    self._save_queue()
                except OSError:
                    item.status, item.step = previous_status, previous_step
                    raise
                self._download_task.cancel()
            else:
                self.items.pop(index)
                try:
                    self._save_queue()
                except OSError:
                    self.items.insert(index, item)
                    raise
            return True
        return False

    def retry_item(self, item_id: str) -> bool:
        for index, item in enumerate(self.items):
            if item.id != item_id or item.status not in ("failed", "cancelled", "completed"):
                continue
            if any(
                other.appid == item.appid and other.status in ("queued", "running", "cancelling")
                for other in self.items
            ):
                return False
            retry = item.model_copy(deep=True)
            self._reset_item(retry, "Queued for retry")
            self.items[index] = retry
            try:
                self._save_queue()
            except OSError:
                self.items[index] = item
                raise
            self.start_worker()
            return True
        return False

    def clear_completed(self):
        previous = self.items
        self.items = [item for item in previous if item.status in ("queued", "running", "cancelling")]
        try:
            self._save_queue()
        except OSError:
            self.items = previous
            raise

    def _install_path(self, item: QueueItem) -> Path:
        for existing in [item, *reversed(self.items)]:
            if existing.appid == item.appid and existing.install_dir:
                path = Path(existing.install_dir)
                shared = any(
                    other.appid != item.appid and other.install_dir == existing.install_dir
                    for other in self.items
                )
                if not shared and safe_install_path(path) and path.is_dir():
                    return path
        existing = find_existing_install(item.appid)
        if existing is not None:
            return existing
        path = DOWNLOAD_DIR / f"{sanitize_filename(item.name)} [{item.appid}]"
        if not safe_install_path(path):
            raise ValueError("The download destination points outside the download directory.")
        return path

    def get_summary(self) -> Dict[str, Any]:
        return {
            "items": [item.model_dump() for item in self.items],
            "active_id": self.active_item.id if self.active_item else None
        }

    async def _process_queue_loop(self):
        while item := next((i for i in self.items if i.status == "queued"), None):
            self.active_item = item
            item.status = "running"
            item.started_at = time.time()
            item.step = "Preparing download"
            self._save_worker_state()
            self._download_task = asyncio.create_task(self._run_download(item))
            try:
                await self._download_task
            except asyncio.CancelledError:
                if item.status == "cancelling":
                    item.status = "cancelled"
                    item.step = "Cancelled by user"
                    item.completed_at = time.time()
                else:
                    self._reset_item(item, "Queued (interrupted)")
                if asyncio.current_task().cancelling():
                    raise
            except Exception as exc:
                item.status = "failed"
                item.error = str(exc)
                item.step = "Failed"
                item.completed_at = time.time()
                item.log_tail.append(f"Download failed: {exc}")
            finally:
                self._download_task = None
                self.active_item = None
                self._save_worker_state()
                self.broadcast("queue_update", self.get_summary())

    async def _run_download(self, item: QueueItem):
        from app.steamcmd_auth import steamcmd_auth_manager

        await steamcmd_auth_manager.wait_for_authorization()
        settings = load_settings()
        install_path = self._install_path(item)
        install_path.mkdir(parents=True, exist_ok=True)
        item.install_dir = str(install_path)
        item.log_tail.append(f"Starting download for {item.name} (AppID: {item.appid})")
        item.log_tail.append(f"Destination: {install_path}")
        restore_steamapps(install_path, item.log_tail)
        self._save_queue()
        self.broadcast("item_update", item.model_dump())

        platform_type = settings.get("force_platform", "windows")
        username = settings.get("steamcmd_username", "").strip()
        validate = settings.get("validate_downloads", True)
        custom_args = settings.get("custom_steamcmd_args", "").strip()

        # Fallback to session account name if not explicitly set in settings
        session = auth_manager.get_session()
        if not username and session:
            username = session.get("account_name", "").strip()

        last_bytes = 0
        last_time = time.monotonic()

        def on_log(line: str):
            item.log_tail.append(line)
            if len(item.log_tail) > 80:
                item.log_tail.pop(0)
            self.broadcast("item_log", {
                "id": item.id,
                "line": line,
                "progress": item.progress,
                "step": item.step,
                "speed_bps": item.speed_bps,
                "eta_seconds": item.eta_seconds,
                "current_bytes": item.current_bytes,
                "total_bytes": item.total_bytes,
            })

        def on_progress(pct: float, cur_b: int, tot_b: int, step_name: str):
            nonlocal last_bytes, last_time
            now = time.monotonic()
            dt = now - last_time
            if cur_b < last_bytes:
                item.speed_bps = 0
                item.eta_seconds = 0
                last_bytes, last_time = cur_b, now
            elif dt >= 0.8:
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
            item.step = step_name
            self.broadcast("item_update", item.model_dump())

        item.step = "Connecting to SteamCMD"
        self.broadcast("item_update", item.model_dump())
        await steam_session.run_download_job(
            appid=item.appid,
            install_path=install_path,
            platform_type=platform_type,
            validate=validate,
            custom_args=custom_args,
            username=username,
            log_callback=on_log,
            progress_callback=on_progress,
        )

        item.step = "Finalizing download"
        self.broadcast("item_update", item.model_dump())
        await post_process_game_directory(install_path, item.appid, item.log_tail, item.require_goldberg)
        await archive_steamapps(install_path, item.appid, item.log_tail)
        item.status = "completed"
        item.progress = 100.0
        item.speed_bps = item.eta_seconds = 0
        item.step = "Completed"
        item.completed_at = time.time()
        item.log_tail.append(f"App {item.appid} downloaded to {install_path}.")


queue_manager = DownloadQueueManager()

