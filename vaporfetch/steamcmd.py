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

# 2FA prompts and result codes in SteamCMD
RE_STEAM_GUARD = re.compile(r"(Steam Guard code:|Steam Guard Mobile Authenticator|Two-factor code:)", re.IGNORECASE)
RE_LOGIN_SUCCESS = re.compile(r"(Logged in OK|Waiting for user info\.\.\.OK)", re.IGNORECASE)
RE_LOGIN_FAIL_CODE = re.compile(r"FAILED with result code\s+([0-9]+)", re.IGNORECASE)
RE_LOGIN_FAIL_TEXT = re.compile(r"(Invalid Password|Rate Limit Exceeded|Login Failure|Account Logon Denied)", re.IGNORECASE)

class SteamCMDAuthSession:
    """Manages an active interactive login session with SteamCMD."""
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.master_fd: Optional[int] = None
        self.username: str = ""
        self.pending_password: Optional[str] = None
        self.status: str = "idle"  # idle, authenticating, awaiting_2fa, logged_in, failed
        self.two_factor_type: str = "email"
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
            self.pending_password = None
            self.status = "idle"
            self.two_factor_type = "email"
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
    Returns status: 'logged_in', 'awaiting_2fa', 'authenticating', or 'failed'.
    """
    auth_session.reset()
    auth_session.username = username
    auth_session.pending_password = password
    auth_session.status = "authenticating"

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

    # Monitor output in background thread
    thread = threading.Thread(target=_monitor_login_pty, daemon=True)
    thread.start()

    # Wait up to 10 seconds for initial outcome
    start_time = time.time()
    while time.time() - start_time < 10.0:
        if auth_session.status in ("logged_in", "awaiting_2fa", "failed"):
            break
        time.sleep(0.25)

    return {
        "status": auth_session.status,
        "prompt": auth_session.prompt_message,
        "error": auth_session.error_message,
        "two_factor_type": auth_session.two_factor_type,
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

            # Check for Steam Guard prompt text
            if RE_STEAM_GUARD.search(accumulated) and auth_session.status != "awaiting_2fa":
                auth_session.status = "awaiting_2fa"
                if "Mobile Authenticator" in accumulated:
                    auth_session.prompt_message = "Enter the current code from your Steam Mobile Authenticator"
                    auth_session.two_factor_type = "mobile"
                else:
                    auth_session.prompt_message = "Enter Steam Guard code sent to your email"
                    auth_session.two_factor_type = "email"

            # Check for Steam result codes
            code_match = RE_LOGIN_FAIL_CODE.search(accumulated)
            if code_match:
                result_code = int(code_match.group(1))
                if result_code == 65:  # k_EResultAccountLogonDenied (Email 2FA)
                    auth_session.status = "awaiting_2fa"
                    auth_session.prompt_message = "Steam Guard code sent to your email"
                    auth_session.two_factor_type = "email"
                    break
                elif result_code == 85:  # k_EResultAccountLogonDeniedNeedTwoFactorCode (Mobile 2FA)
                    auth_session.status = "awaiting_2fa"
                    auth_session.prompt_message = "Enter code from your Steam Mobile Authenticator"
                    auth_session.two_factor_type = "mobile"
                    break
                elif result_code == 5:
                    auth_session.status = "failed"
                    auth_session.error_message = "Invalid Steam password. Please verify your credentials."
                    break
                elif result_code == 84:
                    auth_session.status = "failed"
                    auth_session.error_message = "Rate limit exceeded. Steam has temporarily throttled login. Please wait a few minutes."
                    break
                elif result_code in (88, 89):
                    auth_session.status = "failed"
                    auth_session.error_message = "Steam Guard code mismatch. Please request a new code."
                    break
                else:
                    auth_session.status = "failed"
                    auth_session.error_message = f"Steam login failed (Result code {result_code})."
                    break

            # Check for login success
            if RE_LOGIN_SUCCESS.search(accumulated):
                auth_session.status = "logged_in"
                save_current_session(auth_session.username, logged_in=True)
                break

            # Check for other fail texts
            if "Invalid Password" in accumulated:
                auth_session.status = "failed"
                auth_session.error_message = "Invalid Steam password."
                break

        except OSError:
            break

    # If process exited
    if auth_session.status == "authenticating":
        # Check if login success was printed before process exited
        if RE_LOGIN_SUCCESS.search(accumulated):
            auth_session.status = "logged_in"
            save_current_session(auth_session.username, logged_in=True)
        else:
            code_match = RE_LOGIN_FAIL_CODE.search(accumulated)
            if code_match:
                rc = int(code_match.group(1))
                if rc == 65:
                    auth_session.status = "awaiting_2fa"
                    auth_session.prompt_message = "Steam Guard code sent to your email"
                    auth_session.two_factor_type = "email"
                elif rc == 85:
                    auth_session.status = "awaiting_2fa"
                    auth_session.prompt_message = "Enter code from your Steam Mobile Authenticator"
                    auth_session.two_factor_type = "mobile"
                elif rc == 5:
                    auth_session.status = "failed"
                    auth_session.error_message = "Invalid Steam password."
                elif rc == 84:
                    auth_session.status = "failed"
                    auth_session.error_message = "Rate limit exceeded. Please wait a few minutes."
                else:
                    auth_session.status = "failed"
                    auth_session.error_message = f"Steam login failed (Result code {rc})."
            elif RE_STEAM_GUARD.search(accumulated):
                auth_session.status = "awaiting_2fa"
            else:
                auth_session.status = "failed"
                auth_session.error_message = auth_session.error_message or "SteamCMD process closed unexpectedly."


def submit_2fa_code(code: str) -> Dict[str, Any]:
    """
    Send Steam Guard 2FA code to authenticate.
    Handles both active PTY streams and direct execution via set_steam_guard_code.
    """
    clean_code = code.strip()
    if not clean_code:
        return {"status": "failed", "error": "Steam Guard code cannot be empty."}

    username = auth_session.username
    password = auth_session.pending_password

    # 1. Try sending to active PTY if process is alive
    if auth_session.process and auth_session.process.poll() is None and auth_session.master_fd:
        try:
            os.write(auth_session.master_fd, f"{clean_code}\n".encode("utf-8"))
            start_time = time.time()
            while time.time() - start_time < 8.0:
                if auth_session.status in ("logged_in", "failed"):
                    break
                time.sleep(0.2)
            if auth_session.status == "logged_in":
                auth_session.pending_password = None
                return {"status": "logged_in", "username": username}
        except Exception:
            pass

    # 2. Process exited after code 65/85 (standard SteamCMD behavior).
    # Submit via `+set_steam_guard_code`
    steamcmd_bin = find_steamcmd_path()
    cmd = [
        steamcmd_bin,
        "+set_steam_guard_code", clean_code,
        "+login", username,
    ]
    if password:
        cmd.append(password)
    cmd.append("+quit")

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        out = res.stdout or ""

        if RE_LOGIN_SUCCESS.search(out):
            auth_session.status = "logged_in"
            auth_session.pending_password = None
            save_current_session(username, logged_in=True)
            return {"status": "logged_in", "username": username}

        code_match = RE_LOGIN_FAIL_CODE.search(out)
        if code_match:
            rc = int(code_match.group(1))
            if rc in (88, 89):
                return {"status": "failed", "error": "Incorrect Steam Guard code. Please try again."}
            elif rc == 84:
                return {"status": "failed", "error": "Rate limit exceeded. Please wait a few minutes."}
            elif rc == 5:
                return {"status": "failed", "error": "Invalid password."}
            else:
                return {"status": "failed", "error": f"Login failed (Result code {rc})."}

        if "Invalid Password" in out:
            return {"status": "failed", "error": "Invalid password."}

        return {"status": "failed", "error": "Verification failed. Check the code and try again."}
    except Exception as e:
        return {"status": "failed", "error": f"Failed to execute verification: {e}"}


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

