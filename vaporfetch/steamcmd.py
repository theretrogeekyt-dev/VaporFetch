import os
import re
import pty
import select
import subprocess
import threading
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Callable

from vaporfetch.config import find_steamcmd_path, DATA_DIR, SESSION_FILE

# Regular expressions for SteamCMD parsing
RE_PROGRESS = re.compile(
    r"Update state \((0x[0-9a-fA-F]+)\) ([a-zA-Z]+), progress: ([0-9.]+) \(([0-9]+) / ([0-9]+)\)"
)
RE_APP_SUCCESS = re.compile(r"Success! App '([0-9]+)' fully installed\.", re.IGNORECASE)
RE_APP_ERROR = re.compile(r"ERROR! Failed to install app '([0-9]+)' \((.*?)\)", re.IGNORECASE)
RE_LICENSES_APP = re.compile(r"Apps\s*:\s*([0-9, ]+)")
RE_LICENSES_PKG = re.compile(r"License packageID\s+([0-9]+):")

# 2FA prompts in SteamCMD
RE_STEAM_GUARD = re.compile(r"(Steam Guard code:|Steam Guard Mobile Authenticator|Two-factor code:)", re.IGNORECASE)
RE_LOGIN_SUCCESS = re.compile(r"(Logged in OK|Waiting for user info\.\.\.OK)", re.IGNORECASE)
RE_LOGIN_FAIL = re.compile(r"(FAILED with result code|Invalid Password|Rate Limit Exceeded|Login Failure)", re.IGNORECASE)

class SteamCMDAuthSession:
    """Manages an active interactive login session with SteamCMD."""
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.master_fd: Optional[int] = None
        self.username: str = ""
        self.status: str = "idle"  # idle, authenticating, awaiting_2fa, logged_in, failed
        self.error_message: str = ""
        self.prompt_message: str = ""
        self.lock = threading.Lock()
        self._output_buffer: List[str] = []

    def reset(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                except Exception:
                    pass
            if self.master_fd:
                try:
                    os.close(self.master_fd)
                except Exception:
                    pass
            self.process = None
            self.master_fd = None
            self.username = ""
            self.status = "idle"
            self.error_message = ""
            self.prompt_message = ""
            self._output_buffer = []

auth_session = SteamCMDAuthSession()


def get_current_session() -> Dict[str, Any]:
    """Retrieve saved login session information."""
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"logged_in": False, "username": ""}


def save_current_session(username: str, logged_in: bool = True, steam_id: str = "") -> None:
    """Save session information to disk."""
    data = {
        "username": username,
        "logged_in": logged_in,
        "steam_id": steam_id,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def clear_session() -> None:
    """Remove session file to log out."""
    auth_session.reset()
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except Exception:
            pass


def start_login(username: str, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Initiate an interactive SteamCMD login session.
    Returns status: 'logged_in', 'awaiting_2fa', or 'failed'.
    """
    auth_session.reset()
    steamcmd_bin = find_steamcmd_path()

    cmd = [steamcmd_bin]
    if password:
        cmd.extend(["+login", username, password])
    else:
        cmd.extend(["+login", username])

    try:
        master_fd, slave_fd = pty.openpty()
    except Exception as e:
        auth_session.status = "failed"
        auth_session.error_message = f"Failed to allocate PTY: {e}"
        return {"status": "failed", "error": auth_session.error_message}

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            text=False,
        )
        os.close(slave_fd)
    except Exception as e:
        os.close(master_fd)
        auth_session.status = "failed"
        auth_session.error_message = f"Failed to execute steamcmd: {e}"
        return {"status": "failed", "error": auth_session.error_message}

    auth_session.process = proc
    auth_session.master_fd = master_fd
    auth_session.username = username
    auth_session.status = "authenticating"

    # Monitor output in background thread or wait initial window
    thread = threading.Thread(target=_monitor_login_pty, daemon=True)
    thread.start()

    # Wait up to 5 seconds for immediate outcome (success or 2FA request)
    start_time = time.time()
    while time.time() - start_time < 5.0:
        if auth_session.status in ("logged_in", "awaiting_2fa", "failed"):
            break
        time.sleep(0.2)

    return {
        "status": auth_session.status,
        "prompt": auth_session.prompt_message,
        "error": auth_session.error_message,
    }


def _monitor_login_pty():
    """Background reader for the interactive login PTY."""
    master_fd = auth_session.master_fd
    accumulated = ""

    while auth_session.status in ("authenticating", "awaiting_2fa"):
        if not auth_session.process or auth_session.process.poll() is not None:
            break

        try:
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if not r:
                continue

            chunk = os.read(master_fd, 1024).decode("utf-8", errors="replace")
            if not chunk:
                break

            accumulated += chunk
            auth_session._output_buffer.append(chunk)

            # Check for Steam Guard prompt
            if RE_STEAM_GUARD.search(accumulated) and auth_session.status != "awaiting_2fa":
                auth_session.status = "awaiting_2fa"
                if "Mobile Authenticator" in accumulated:
                    auth_session.prompt_message = "Enter Steam Guard Mobile Authenticator code"
                else:
                    auth_session.prompt_message = "Enter Steam Guard code sent to your email"

            # Check for login success
            if RE_LOGIN_SUCCESS.search(accumulated):
                auth_session.status = "logged_in"
                save_current_session(auth_session.username, logged_in=True)
                break

            # Check for login failure
            fail_match = RE_LOGIN_FAIL.search(accumulated)
            if fail_match:
                auth_session.status = "failed"
                auth_session.error_message = f"Login failed: {fail_match.group(0)}"
                break

        except OSError:
            break

    # If process exited and not logged in
    if auth_session.status == "authenticating":
        if RE_LOGIN_SUCCESS.search(accumulated):
            auth_session.status = "logged_in"
            save_current_session(auth_session.username, logged_in=True)
        else:
            auth_session.status = "failed"
            auth_session.error_message = auth_session.error_message or "SteamCMD process closed unexpectedly."


def submit_2fa_code(code: str) -> Dict[str, Any]:
    """Send Steam Guard 2FA code to the running SteamCMD process."""
    if auth_session.status != "awaiting_2fa" or not auth_session.master_fd:
        return {"status": "failed", "error": "No active session waiting for 2FA."}

    clean_code = code.strip() + "\n"
    try:
        os.write(auth_session.master_fd, clean_code.encode("utf-8"))
    except Exception as e:
        auth_session.status = "failed"
        auth_session.error_message = f"Error sending 2FA code: {e}"
        return {"status": "failed", "error": auth_session.error_message}

    # Wait up to 6 seconds for response
    start_time = time.time()
    while time.time() - start_time < 6.0:
        if auth_session.status in ("logged_in", "failed"):
            break
        time.sleep(0.2)

    return {
        "status": auth_session.status,
        "error": auth_session.error_message,
    }


def parse_licenses_output(output: str) -> Set[int]:
    """Parse AppIDs from SteamCMD `licenses_print` stdout."""
    app_ids: Set[int] = set()
    for line in output.splitlines():
        match = RE_LICENSES_APP.search(line)
        if match:
            apps_str = match.group(1)
            for part in apps_str.split(","):
                part = part.strip()
                if part.isdigit():
                    app_ids.add(int(part))
    return app_ids


def fetch_licenses(username: str) -> Set[int]:
    """Run `licenses_print` in SteamCMD to obtain owned game AppIDs."""
    steamcmd_bin = find_steamcmd_path()
    cmd = [
        steamcmd_bin,
        "+login", username,
        "+licenses_print",
        "+quit"
    ]
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            check=False,
        )
        return parse_licenses_output(res.stdout)
    except Exception as e:
        print(f"[VaporFetch] Error fetching licenses: {e}")
        return set()


def parse_progress_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single SteamCMD progress update line."""
    match = RE_PROGRESS.search(line)
    if not match:
        return None

    state_hex, state_name, progress_pct, cur_bytes, total_bytes = match.groups()
    cur_b = int(cur_bytes)
    tot_b = int(total_bytes)
    pct = float(progress_pct)

    return {
        "state_hex": state_hex,
        "state": state_name.lower(),
        "percent": pct,
        "current_bytes": cur_b,
        "total_bytes": tot_b,
    }


def run_app_download(
    appid: int,
    install_dir: str,
    username: str,
    platform: str = "windows",
    validate: bool = True,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """
    Download or backup a Steam game using SteamCMD app_update.
    Streams live progress and log output via callbacks.
    """
    steamcmd_bin = find_steamcmd_path()
    cmd = [
        steamcmd_bin,
        "+force_install_dir", install_dir,
        "+login", username,
    ]

    if platform and platform.lower() in ("windows", "linux", "macos"):
        cmd.extend(["+@sSteamCmdForcePlatformType", platform.lower()])

    if validate:
        cmd.extend(["+app_update", str(appid), "validate"])
    else:
        cmd.extend(["+app_update", str(appid)])

    cmd.append("+quit")

    if log_cb:
        log_cb(f"Starting SteamCMD for AppID {appid} (Platform: {platform})...")
        log_cb(f"Command: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as e:
        err = f"Failed to start SteamCMD: {e}"
        if log_cb:
            log_cb(err)
        return {"success": False, "error": err}

    last_bytes = 0
    last_time = time.time()
    success = False
    error_message = ""

    while True:
        if cancel_event and cancel_event.is_set():
            proc.terminate()
            if log_cb:
                log_cb(f"Download for AppID {appid} cancelled by user.")
            return {"success": False, "error": "Cancelled by user"}

        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break

        line_str = line.strip()
        if not line_str:
            continue

        if log_cb:
            log_cb(line_str)

        # Check success/error
        if RE_APP_SUCCESS.search(line_str):
            success = True

        err_match = RE_APP_ERROR.search(line_str)
        if err_match:
            error_message = err_match.group(2)

        # Check progress
        parsed_prog = parse_progress_line(line_str)
        if parsed_prog and progress_cb:
            now = time.time()
            dt = now - last_time
            if dt > 0.5:
                bytes_diff = parsed_prog["current_bytes"] - last_bytes
                speed = max(0.0, bytes_diff / dt) if last_bytes > 0 else 0.0
                rem_bytes = max(0, parsed_prog["total_bytes"] - parsed_prog["current_bytes"])
                eta = int(rem_bytes / speed) if speed > 0 else 0

                parsed_prog["speed_bps"] = speed
                parsed_prog["eta_seconds"] = eta
                last_bytes = parsed_prog["current_bytes"]
                last_time = now
                progress_cb(parsed_prog)

    retcode = proc.poll()
    if retcode == 0 or success:
        return {"success": True, "error": None}
    else:
        return {
            "success": False,
            "error": error_message or f"SteamCMD process exited with code {retcode}",
        }

