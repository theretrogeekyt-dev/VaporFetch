import time
import threading
import queue
from typing import Dict, List, Any, Optional, Set
from collections import deque

from vaporfetch.config import (
    load_settings,
    get_storage_stats,
)
from vaporfetch.library import (
    resolver,
    get_game_install_dir,
    format_bytes,
)
from vaporfetch.steamcmd import (
    get_current_session,
    run_app_download,
    auth_session,
    has_steamcmd_cached_credentials,
)

class DownloadTask:
    def __init__(self, appid: int, name: str, platform: str = "windows"):
        self.appid: int = appid
        self.name: str = name
        self.platform: str = platform
        self.status: str = "queued"  # queued, downloading, completed, failed, cancelled
        self.percent: float = 0.0
        self.current_bytes: int = 0
        self.total_bytes: int = 0
        self.speed_bps: float = 0.0
        self.eta_seconds: int = 0
        self.error: Optional[str] = None
        self.added_at: float = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appid": self.appid,
            "name": self.name,
            "platform": self.platform,
            "status": self.status,
            "percent": round(self.percent, 1),
            "current_bytes": self.current_bytes,
            "total_bytes": self.total_bytes,
            "current_formatted": format_bytes(self.current_bytes),
            "total_formatted": format_bytes(self.total_bytes),
            "speed_bps": self.speed_bps,
            "speed_formatted": f"{format_bytes(self.speed_bps)}/s" if self.speed_bps > 0 else "--",
            "eta_seconds": self.eta_seconds,
            "error": self.error,
            "added_at": self.added_at,
        }


class DownloadManager:
    """Manages sequential Steam game download queue, worker thread, and live event broadcasting."""
    def __init__(self):
        self.queue: List[DownloadTask] = []
        self.current_task: Optional[DownloadTask] = None
        self.history: deque = deque(maxlen=50)
        self.log_history: deque = deque(maxlen=500)
        self.lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.subscribers: Set[queue.Queue] = set()

        # Background worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def subscribe(self) -> queue.Queue:
        """Register a subscriber queue for SSE / WebSocket real-time events."""
        q: queue.Queue = queue.Queue(maxsize=100)
        with self.lock:
            self.subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a subscriber queue."""
        with self.lock:
            self.subscribers.discard(q)

    def broadcast(self, event_type: str, data: Any) -> None:
        """Broadcast an event payload to all active client streams."""
        payload = {"type": event_type, "data": data, "timestamp": time.time()}
        with self.lock:
            dead = set()
            for q in self.subscribers:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.add(q)
            self.subscribers.difference_update(dead)

    def add_log(self, text: str) -> None:
        """Record a log message and broadcast it."""
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {text}"
        self.log_history.append(formatted)
        self.broadcast("log", formatted)

    def add_to_queue(self, appid: int, name: Optional[str] = None, platform: Optional[str] = None) -> bool:
        """Add a single app to the download queue."""
        with self.lock:
            # Avoid duplicate in active queue
            if self.current_task and self.current_task.appid == appid:
                return False
            if any(t.appid == appid for t in self.queue):
                return False

            if not name:
                name = resolver.resolve_name(appid)

            settings = load_settings()
            target_platform = platform or settings.get("default_platform", "windows")
            task = DownloadTask(appid=appid, name=name, platform=target_platform)
            self.queue.append(task)

        self.add_log(f"Queued '{name}' (AppID: {appid}, Platform: {task.platform})")
        self.broadcast("queue_update", self.get_queue_state())
        return True

    def add_batch(self, items: List[Dict[str, Any]], platform: Optional[str] = None) -> int:
        """Add multiple apps to the queue. Returns count of newly queued games."""
        added = 0
        settings = load_settings()
        target_platform = platform or settings.get("default_platform", "windows")

        with self.lock:
            for item in items:
                aid = item.get("appid")
                if not aid:
                    continue
                aid = int(aid)
                if self.current_task and self.current_task.appid == aid:
                    continue
                if any(t.appid == aid for t in self.queue):
                    continue

                name = item.get("name") or resolver.resolve_name(aid)
                task = DownloadTask(appid=aid, name=name, platform=target_platform)
                self.queue.append(task)
                added += 1

        if added > 0:
            self.add_log(f"Added {added} games to the download queue.")
            self.broadcast("queue_update", self.get_queue_state())

        return added

    def remove_from_queue(self, appid: int) -> bool:
        """Remove a pending game from queue."""
        with self.lock:
            original_len = len(self.queue)
            self.queue = [t for t in self.queue if t.appid != appid]
            removed = len(self.queue) < original_len

        if removed:
            self.add_log(f"Removed AppID {appid} from queue.")
            self.broadcast("queue_update", self.get_queue_state())
        return removed

    def clear_queue(self) -> None:
        """Clear all pending tasks in the queue."""
        with self.lock:
            count = len(self.queue)
            self.queue.clear()

        self.add_log(f"Cleared {count} queued items.")
        self.broadcast("queue_update", self.get_queue_state())

    def cancel_current(self) -> bool:
        """Cancel the currently active download task."""
        if self.current_task and self.current_task.status == "downloading":
            self.add_log(f"Cancelling download for '{self.current_task.name}'...")
            self.cancel_event.set()
            return True
        return False

    def get_queue_state(self) -> Dict[str, Any]:
        """Return the current manager state for API response."""
        with self.lock:
            return {
                "current": self.current_task.to_dict() if self.current_task else None,
                "queue": [t.to_dict() for t in self.queue],
                "history": [t.to_dict() for t in list(self.history)[::-1]],
                "storage": get_storage_stats(),
            }

    def _worker_loop(self):
        """Sequential background processor for queued game downloads."""
        while True:
            task = None
            with self.lock:
                if self.queue:
                    task = self.queue.pop(0)
                    self.current_task = task
                else:
                    self.current_task = None

            if not task:
                time.sleep(1.0)
                continue

            session = get_current_session()
            username = session.get("username")
            if not username:
                task.status = "failed"
                task.error = "Steam account not logged in."
                self.add_log(f"Cannot download '{task.name}': Not logged in.")
                with self.lock:
                    self.history.append(task)
                    self.current_task = None
                self.broadcast("queue_update", self.get_queue_state())
                continue

            session = get_current_session()
            is_authenticated = bool(session.get("logged_in") and (session.get("username") or username))
            if not is_authenticated and not has_steamcmd_cached_credentials(username):
                task.status = "failed"
                task.error = "Steam login required. Please sign in via Account (Steam Mobile QR Code)."
                self.add_log(
                    f"Cannot download '{task.name}': Not logged in to Steam. "
                    "Please click 'Account' and scan the QR code with your Steam Mobile App to authenticate."
                )
                with self.lock:
                    self.history.append(task)
                    self.current_task = None
                self.broadcast("queue_update", self.get_queue_state())
                continue

            task.status = "downloading"
            task.started_at = time.time()
            self.cancel_event.clear()
            self.add_log(f"=== Starting backup of '{task.name}' (AppID: {task.appid}) ===")
            self.broadcast("queue_update", self.get_queue_state())

            settings = load_settings()
            install_dir = str(get_game_install_dir(task.name, task.appid))
            validate = settings.get("validate_downloads", True)

            def progress_callback(info: Dict[str, Any]):
                task.percent = info.get("percent", 0.0)
                task.current_bytes = info.get("current_bytes", 0)
                task.total_bytes = info.get("total_bytes", 0)
                task.speed_bps = info.get("speed_bps", 0.0)
                task.eta_seconds = info.get("eta_seconds", 0)
                self.broadcast("progress", task.to_dict())

            def log_callback(line: str):
                self.add_log(f"[{task.appid}] {line}")

            result = run_app_download(
                appid=task.appid,
                install_dir=install_dir,
                username=username,
                platform=task.platform,
                validate=validate,
                progress_cb=progress_callback,
                log_cb=log_callback,
                cancel_event=self.cancel_event,
            )

            task.finished_at = time.time()
            if result.get("success"):
                task.status = "completed"
                task.percent = 100.0
                self.add_log(f"Successfully backed up '{task.name}' to {install_dir}!")
            elif self.cancel_event.is_set():
                task.status = "cancelled"
                task.error = "Cancelled by user"
                self.add_log(f"Download cancelled for '{task.name}'.")
            else:
                task.status = "failed"
                task.error = result.get("error", "Unknown error")
                self.add_log(f"Failed to backup '{task.name}': {task.error}")

            with self.lock:
                self.history.append(task)
                self.current_task = None

            self.broadcast("queue_update", self.get_queue_state())
            time.sleep(0.5)

manager = DownloadManager()

