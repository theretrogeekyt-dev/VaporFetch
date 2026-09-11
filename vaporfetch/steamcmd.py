import os
import re
import pty
import select
import subprocess
import threading
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Callable

from vaporfetch.config import find_steamcmd_path, DATA_DIR, SESSION_FILE

logger = logging.getLogger("vaporfetch.steamcmd")

# Regular expressions for SteamCMD parsing
RE_PROGRESS = re.compile(
    r"Update state \((0x[0-9a-fA-F]+)\) ([a-zA-Z]+), progress: ([0-9.]+) \(([0-9]+) / ([0-9]+)\)"
)
RE_APP_SUCCESS = re.compile(r"Success! App '([0-9]+)' fully installed\.", re.IGNORECASE)
RE_APP_ERROR = re.compile(r"ERROR! Failed to install app '([0-9]+)' \((.*?)\)", re.IGNORECASE)
RE_LICENSES_APP = re.compile(r"(?:Apps?|AppIDs?)\s*:\s*([0-9, ]+)", re.IGNORECASE)
RE_APPID_EXPLICIT = re.compile(r"\b(?:AppID|App)\s*[:\s]\s*(\d+)\b", re.IGNORECASE)
RE_LICENSES_PKG = re.compile(r"License packageID\s+([0-9]+):", re.IGNORECASE)

# 2FA prompts and result codes in SteamCMD
RE_STEAM_GUARD = re.compile(
    r"(Steam Guard code:|Steam Guard Mobile Authenticator|Two-factor code:|Account Logon Denied|Need Two Factor|result code 65|result code 85)",
    re.IGNORECASE
)
RE_LOGIN_SUCCESS = re.compile(r"(Logged in OK|Waiting for user info\.\.\.OK|Success\.)", re.IGNORECASE)
RE_LOGIN_FAIL = re.compile(
    r"FAILED\s*\((.*?)\)|FAILED with result code\s+([0-9]+)|FAILED\s*:\s*(.*)",
    re.IGNORECASE
)

def check_login_output(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse SteamCMD login output text to determine current state based on
    the latest event in the output stream: logged_in, awaiting_2fa, or failed.
    """
    events = []

    # 1. Success check
    for m in RE_LOGIN_SUCCESS.finditer(text):
        events.append((m.end(), "logged_in", {"status": "logged_in"}))

    # 2. 2FA check
    for m in RE_STEAM_GUARD.finditer(text):
        is_mobile = bool(re.search(r"(Mobile Authenticator|Need Two Factor|result code 85)", text, re.IGNORECASE))
        events.append((m.end(), "awaiting_2fa", {
            "status": "awaiting_2fa",
            "prompt": "Enter the current code from your Steam Mobile Authenticator" if is_mobile else "Enter Steam Guard code sent to your email",
            "two_factor_type": "mobile" if is_mobile else "email",
        }))

    # 3. Specific failures
    for m in RE_LOGIN_FAIL.finditer(text):
        reason = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        reason_lower = reason.lower()

        if "need two factor" in reason_lower or reason == "85":
            events.append((m.end(), "awaiting_2fa", {
                "status": "awaiting_2fa",
                "prompt": "Enter code from your Steam Mobile Authenticator",
                "two_factor_type": "mobile",
            }))
        elif "account logon denied" in reason_lower or reason == "65":
            events.append((m.end(), "awaiting_2fa", {
                "status": "awaiting_2fa",
                "prompt": "Steam Guard code sent to your email. Check your inbox and enter code:",
                "two_factor_type": "email",
            }))
        elif "invalid password" in reason_lower or reason == "5":
            events.append((m.end(), "failed", {"status": "failed", "error": "Invalid Steam password. Please verify your credentials."}))
        elif "rate limit" in reason_lower or reason == "84":
            events.append((m.end(), "failed", {"status": "failed", "error": "Rate limit exceeded. Steam has temporarily throttled login. Please wait a few minutes."}))
        elif "no connection" in reason_lower or reason == "3":
            events.append((m.end(), "failed", {"status": "failed", "error": "No connection to Steam servers. Please check your network connection."}))
        elif reason in ("88", "89") or "mismatch" in reason_lower:
            events.append((m.end(), "failed", {"status": "failed", "error": "Steam Guard 2FA code mismatch. Please check and try again."}))
        else:
            events.append((m.end(), "failed", {"status": "failed", "error": f"Steam login failed: {reason}"}))

    if not events:
        if "Invalid Password" in text:
            return {"status": "failed", "error": "Invalid Steam password."}
        return None

    # Sort by character end position in output stream: the last event wins!
    events.sort(key=lambda x: x[0])
    return events[-1][2]


class SteamCMDAuthSession:
    """Manages an active interactive login session with SteamCMD."""
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.master_fd: Optional[int] = None
        self.username: str = ""
        self.pending_password: Optional[str] = None
        self.pending_code: Optional[str] = None
        self.code_injected_at: int = -1
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
            self.pending_code = None
            self.code_injected_at = -1
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


def save_current_session(username: str, logged_in: bool = True, steam_id: str = "", **extra) -> None:
    """Save session information to disk."""
    data = {
        "username": username,
        "logged_in": logged_in,
        "steam_id": steam_id,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **extra,
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def begin_qr_login() -> Dict[str, Any]:
    """
    Initiate a Steam Mobile QR code login session via Steam's IAuthenticationService.
    Returns client_id, challenge_url, request_id, and interval.
    """
    url = "https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaQR/v1/"
    payload = urllib.parse.urlencode({
        "device_friendly_name": "VaporFetch",
        "platform_type": 1,
        "website_id": "Community"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"User-Agent": "VaporFetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data.get("response", {})
            return {
                "status": "success",
                "client_id": res.get("client_id"),
                "challenge_url": res.get("challenge_url"),
                "request_id": res.get("request_id"),
                "interval": res.get("interval", 3),
            }
    except Exception as e:
        logger.error(f"Failed to begin QR auth session: {e}")
        return {"status": "failed", "error": f"Failed to contact Steam authentication service: {e}"}


def poll_qr_login(client_id: str, request_id: str) -> Dict[str, Any]:
    """
    Poll the status of a pending Steam Mobile QR code login session.
    Returns 'logged_in', 'waiting', or 'expired'/'failed'.
    """
    url = "https://api.steampowered.com/IAuthenticationService/PollAuthSessionStatus/v1/"
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "request_id": request_id
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"User-Agent": "VaporFetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data.get("response", {})

            # If user has confirmed and approved the login on their phone:
            if "refresh_token" in res or "access_token" in res or "account_name" in res:
                account_name = res.get("account_name", "")
                steam_id = res.get("steamid", "")
                access_token = res.get("access_token", "")
                refresh_token = res.get("refresh_token", "")

                auth_session.status = "logged_in"
                auth_session.username = account_name
                save_current_session(
                    username=account_name,
                    logged_in=True,
                    steam_id=steam_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    auth_method="qr",
                )
                return {
                    "status": "logged_in",
                    "username": account_name,
                    "steam_id": steam_id,
                }

            # Still waiting for user interaction:
            had_interaction = res.get("had_remote_interaction", False)
            return {
                "status": "waiting",
                "had_remote_interaction": had_interaction,
            }
    except urllib.error.HTTPError as e:
        if e.code in (400, 404, 410):
            return {"status": "expired", "error": "QR code expired. Please refresh the QR code."}
        return {"status": "failed", "error": f"Steam API error ({e.code})"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def clear_session() -> None:
    """Remove session file to log out."""
    auth_session.reset()
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except Exception:
            pass


def start_login(username: str, password: Optional[str] = None, code: Optional[str] = None) -> Dict[str, Any]:
    """
    Initiate an interactive SteamCMD login session.
    If code is provided upfront, it will be automatically piped to the 2FA prompt in the PTY.
    Returns status: 'logged_in', 'awaiting_2fa', 'authenticating', or 'failed'.
    """
    auth_session.reset()
    auth_session.username = username
    auth_session.pending_password = password
    auth_session.pending_code = code.strip() if code and code.strip() else None
    auth_session.status = "authenticating"

    steamcmd_bin = find_steamcmd_path()

    cmd = [steamcmd_bin]
    if password:
        cmd.extend(["+login", username, password])
    else:
        cmd.extend(["+login", username])
    cmd.extend(["+licenses_print", "+quit"])

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

    # Wait for initial outcome:
    # If code was provided upfront, wait up to 25s for the full login flow and licenses to complete
    # If code was not provided, wait until awaiting_2fa is detected or 15s
    timeout_secs = 25.0 if auth_session.pending_code else 15.0
    start_time = time.time()
    while time.time() - start_time < timeout_secs:
        if auth_session.status in ("logged_in", "failed"):
            break
        if auth_session.status == "awaiting_2fa" and not auth_session.pending_code:
            break
        time.sleep(0.2)

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

    def _finish_login(accum_str: str) -> str:
        # NOTE: Do not set auth_session.status = "logged_in" yet, and do not clear pending_password!
        # Keeping status as "authenticating" prevents the frontend from firing /api/library
        # prematurely while SteamCMD is still outputting licenses.
        try:
            # If SteamCMD did not output licenses yet, send command explicitly
            if "License packageID" not in accum_str:
                logger.info("Sending licenses_print to interactive PTY...")
                try:
                    os.write(master_fd, b"licenses_print\nquit\n")
                except Exception:
                    pass

            read_start = time.time()
            while time.time() - read_start < 25.0:
                if auth_session.process and auth_session.process.poll() is not None:
                    # Drain any remaining bytes from PTY
                    try:
                        r, _, _ = select.select([master_fd], [], [], 0.3)
                        if r:
                            ch = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                            if ch:
                                accum_str += ch
                    except Exception:
                        pass
                    break

                r, _, _ = select.select([master_fd], [], [], 0.5)
                if not r:
                    continue
                ch = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                if not ch:
                    break
                accum_str += ch
        except Exception as e:
            logger.warning(f"Notice while reading licenses on login: {e}")

        owned_app_ids = parse_licenses_output(accum_str)
        print(f"[VaporFetch] licenses_print stream completed. Output {len(accum_str)} bytes, parsed {len(owned_app_ids)} AppIDs.")
        if owned_app_ids:
            try:
                from vaporfetch.library import populate_and_cache_games
                populate_and_cache_games(owned_app_ids)
                logger.info(f"Cached {len(owned_app_ids)} owned games from login session.")
            except Exception as e:
                logger.error(f"Error caching owned games: {e}")
        else:
            logger.warning("No owned AppIDs parsed from login output.")

        try:
            if auth_session.process and auth_session.process.poll() is None:
                auth_session.process.terminate()
                auth_session.process.wait(timeout=2)
        except Exception:
            pass

        try:
            os.close(master_fd)
        except Exception:
            pass
        auth_session.master_fd = None

        save_current_session(auth_session.username, logged_in=True, auth_method="steamcmd")
        auth_session.status = "logged_in"
        return accum_str

    while auth_session.status in ("authenticating", "awaiting_2fa"):
        try:
            r, _, _ = select.select([master_fd], [], [], 0.3)
            if not r:
                # If no data ready and process terminated, drain remaining and exit
                if not auth_session.process or auth_session.process.poll() is not None:
                    break
                continue

            chunk = os.read(master_fd, 4096).decode("utf-8", errors="replace")
            if not chunk:
                break

            accumulated += chunk
            auth_session._output_buffer.append(chunk)

            # If a 2FA code was already injected (upfront or via submit_2fa_code),
            # only inspect output arriving AFTER the injection!
            if auth_session.code_injected_at >= 0:
                post_code_output = accumulated[auth_session.code_injected_at:]
                if not post_code_output.strip():
                    continue
                result = check_login_output(post_code_output)
                if result:
                    if result["status"] == "logged_in":
                        accumulated = _finish_login(accumulated)
                        break
                    elif result["status"] == "awaiting_2fa":
                        # SteamCMD prompted for 2FA again after the code was injected!
                        auth_session.status = "failed"
                        auth_session.error_message = "Steam Guard code was incorrect or expired. Please check your Steam Mobile App and try again."
                        break
                    elif result["status"] == "failed":
                        auth_session.status = "failed"
                        auth_session.error_message = result.get("error", "Login failed")
                        break
                continue

            # Check status on current accumulated output
            result = check_login_output(accumulated)
            if result:
                if result["status"] == "awaiting_2fa":
                    auth_session.prompt_message = result.get("prompt", "Enter Steam Guard code")
                    auth_session.two_factor_type = result.get("two_factor_type", "email")

                    # If upfront code is available and hasn't been sent yet, inject immediately!
                    if auth_session.pending_code:
                        clean_code = auth_session.pending_code
                        auth_session.pending_code = None
                        auth_session.code_injected_at = len(accumulated)
                        try:
                            logger.info("Injecting upfront Steam Guard code into PTY prompt")
                            os.write(master_fd, f"{clean_code}\n".encode("utf-8"))
                        except Exception as e:
                            logger.error(f"Failed to write upfront code to PTY: {e}")
                        auth_session.status = "authenticating"
                        continue
                    else:
                        auth_session.status = "awaiting_2fa"
                        # Keep thread reading so when submit_2fa_code writes to master_fd,
                        # this thread reads the result and updates status!
                        continue

                elif result["status"] == "logged_in":
                    accumulated = _finish_login(accumulated)
                    break
                elif result["status"] == "failed":
                    auth_session.status = "failed"
                    auth_session.error_message = result.get("error", "Login failed")
                    break

        except OSError:
            break

    # If process exited and state still unresolved
    if auth_session.status in ("authenticating", "awaiting_2fa"):
        result = check_login_output(accumulated)
        if result:
            auth_session.status = result["status"]
            if result["status"] == "logged_in":
                accumulated = _finish_login(accumulated)
            elif result["status"] == "failed":
                auth_session.error_message = result.get("error", "Login failed")
        else:
            if auth_session.process and auth_session.process.poll() is not None:
                lines = [l.strip() for l in accumulated.splitlines() if l.strip() and not l.strip().startswith("[")]
                last_line = lines[-1] if lines else "Process terminated without output."
                auth_session.status = "failed"
                auth_session.error_message = f"SteamCMD: {last_line}"


def submit_2fa_code(code: str) -> Dict[str, Any]:
    """
    Send Steam Guard 2FA code to authenticate.
    Handles active PTY streams and direct fallback execution if process exited.
    """
    clean_code = code.strip()
    if not clean_code:
        return {"status": "failed", "error": "Steam Guard code cannot be empty."}

    username = auth_session.username
    password = auth_session.pending_password

    # 1. Active PTY stream (SteamCMD is waiting for 2FA input)
    if auth_session.process and auth_session.process.poll() is None and auth_session.master_fd:
        try:
            auth_session.status = "authenticating"
            auth_session.code_injected_at = len("".join(auth_session._output_buffer))
            os.write(auth_session.master_fd, f"{clean_code}\n".encode("utf-8"))
            start_time = time.time()
            while time.time() - start_time < 25.0:
                if auth_session.status in ("logged_in", "failed"):
                    break
                time.sleep(0.2)
            if auth_session.status == "logged_in":
                return {"status": "logged_in", "username": username}
            elif auth_session.status == "failed":
                return {"status": "failed", "error": auth_session.error_message or "2FA verification failed."}
            else:
                return {"status": "authenticating"}
        except Exception as e:
            logger.error(f"Error sending 2FA to PTY: {e}")

    # 2. Process exited after code 65/85 (fallback execution)
    steamcmd_bin = find_steamcmd_path()
    cmd = [
        steamcmd_bin,
        "+set_steam_guard_code", clean_code,
        "+login", username,
    ]
    if password:
        cmd.append(password)
    cmd.extend(["+licenses_print", "+quit"])

    try:
        res = subprocess.run(
            cmd,
            input=f"{clean_code}\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        out = res.stdout or ""

        result = check_login_output(out)
        if result:
            if result["status"] == "logged_in":
                save_current_session(username, logged_in=True, auth_method="steamcmd")
                owned_app_ids = parse_licenses_output(out)
                if owned_app_ids:
                    try:
                        from vaporfetch.library import populate_and_cache_games
                        populate_and_cache_games(owned_app_ids)
                        logger.info(f"Cached {len(owned_app_ids)} owned games from fallback verification.")
                    except Exception as e:
                        logger.error(f"Error caching owned games: {e}")
                auth_session.status = "logged_in"
                return {"status": "logged_in", "username": username}
            elif result["status"] == "failed":
                return result

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
        else:
            m2 = RE_APPID_EXPLICIT.search(line)
            if m2:
                app_ids.add(int(m2.group(1)))
    return app_ids


def fetch_licenses(username: str) -> Set[int]:
    """Run `licenses_print` in SteamCMD to obtain owned game AppIDs."""
    if auth_session.process and auth_session.process.poll() is None:
        try:
            auth_session.process.terminate()
            auth_session.process.wait(timeout=2)
        except Exception:
            pass
    if auth_session.master_fd:
        try:
            os.close(auth_session.master_fd)
        except Exception:
            pass
        auth_session.master_fd = None

    steamcmd_bin = find_steamcmd_path()
    pwd = auth_session.pending_password if auth_session.username == username else None
    cmd = [steamcmd_bin]
    if pwd:
        cmd.extend(["+login", username, pwd])
    else:
        cmd.extend(["+login", username])
    cmd.extend(["+licenses_print", "+quit"])

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        out = res.stdout or ""
        app_ids = parse_licenses_output(out)
        print(f"[VaporFetch] licenses_print for {username} completed. Output {len(out)} bytes, parsed {len(app_ids)} AppIDs.")
        if not app_ids and out:
            print(f"[VaporFetch] Warning: 0 AppIDs parsed from licenses_print. Output snippet: {out[-500:]}")
        return app_ids
    except Exception as e:
        logger.error(f"Error fetching licenses: {e}")
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
    pwd = auth_session.pending_password if auth_session.username == username else None
    cmd = [
        steamcmd_bin,
        "+force_install_dir", install_dir,
    ]
    if pwd:
        cmd.extend(["+login", username, pwd])
    else:
        cmd.extend(["+login", username])

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

