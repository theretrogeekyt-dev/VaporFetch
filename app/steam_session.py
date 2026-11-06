import os
import re
import signal
import time
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from app.config import (
    STEAMCMD_BIN,
    STEAM_HOME_DIR,
    load_settings,
    save_settings,
    sync_steam_credentials,
    configure_steam_autologin
)

# Regex for SteamCMD download progress:
PROGRESS_REGEX = re.compile(
    r"Update state \((0x[0-9a-fA-F]+)\)\s+([a-zA-Z\s]+),\s+progress:\s+([0-9.]+)\s+\((\d+)\s*\/\s*(\d+)\)"
)
SUCCESS_REGEX = re.compile(r"Success! App '(\d+)'", re.IGNORECASE)
GUARD_CODE_PROMPT = re.compile(
    r"(?:steam guard|authenticator|two[- ]factor).*code[^:]*:\s*$|\benter (?:the )?code:\s*$",
    re.IGNORECASE,
)
DOWNLOAD_OUTPUT_TIMEOUT = 15 * 60


def normalize_guard_code(code: str) -> str:
    code = code.strip()
    if not re.fullmatch(r"[A-Za-z0-9]{5,8}", code):
        raise ValueError("Enter the Steam Guard code as shown in Steam or your email.")
    return code.upper()


class SteamCmdSessionWorker:
    """
    Manages a long-running, persistent interactive SteamCMD process.
    SteamCMD can reuse an authorized session for the same destination and platform.
    A different destination needs a new console so force_install_dir precedes login.
    """
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.state: str = "disconnected"
        self.status_message: str = ""
        self.current_user: str = ""
        self.is_logged_in: bool = False
        self.log_history: List[str] = []
        self.line_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._process_lock = asyncio.Lock()
        self._target = None
        self._secrets: set[str] = set()

    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def is_ready(self) -> bool:
        return self.is_alive() and self.is_logged_in

    def get_status(self) -> Dict[str, Any]:
        settings = load_settings()
        return {
            "alive": self.is_alive(),
            "logged_in": self.is_logged_in,
            "state": self.state,
            "status_message": self.status_message,
            "username": self.current_user or settings.get("steamcmd_username", ""),
            "has_password": bool(settings.get("steamcmd_password")),
            "logs": self.log_history[-25:],
        }

    async def _stdout_reader(self):
        """Read line updates and interactive prompts that have no trailing newline."""
        try:
            buffer = ""
            while True:
                if not self.process or not self.process.stdout:
                    break
                chunk = await self.process.stdout.read(4096)
                if not chunk:
                    break
                parts = re.split(r"[\r\n]+", buffer + chunk.decode("utf-8", errors="replace"))
                buffer = parts.pop()
                if buffer.rstrip().endswith("Steam>") or GUARD_CODE_PROMPT.search(buffer):
                    parts.append(buffer)
                    buffer = ""
                for line in parts:
                    line = line.strip()
                    if not line:
                        continue
                    for secret in self._secrets:
                        line = line.replace(secret, "[redacted]")
                    self.log_history.append(line)
                    if len(self.log_history) > 150:
                        self.log_history.pop(0)
                    self.line_queue.put_nowait(line)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log_history.append(f"[SessionWorker] Reader error: {e}")
        finally:
            self.is_logged_in = False
            await self.line_queue.put(None)  # Sentinel for EOF

    async def ensure_session(
        self, username: str, password: str = "",
        log_callback: Optional[Callable[[str], None]] = None,
        *, install_path: Optional[Path] = None, platform_type: str = "windows", guard_code: str = "",
    ) -> bool:
        """
        Ensures a persistent SteamCMD process is running and logged in.
        If already logged in as the requested user, returns immediately with 0 prompts.
        """
        async with self._lock:
            settings = load_settings()
            clean_user = (username or settings.get("steamcmd_username", "") or "anonymous").strip()
            clean_pass = password if password is not None else settings.get("steamcmd_password", "")
            if not re.fullmatch(r"[A-Za-z0-9_]+", clean_user):
                raise ValueError("Enter a valid Steam account name.")
            if "\n" in clean_pass or "\r" in clean_pass:
                raise ValueError("The Steam password must be a single line.")
            target = (install_path, platform_type)

            # If already alive, authenticated, and matching user, return immediately!
            if self.is_ready() and self.current_user.lower() == clean_user.lower() and self._target == target:
                if log_callback:
                    log_callback(f"Using active persistent SteamCMD session for '{clean_user}' (no phone prompt).")
                return True

            # If process is running but wrong user or disconnected, terminate first
            if self.process is not None:
                await self.terminate_session()

            self.state = "starting"
            self.status_message = f"Starting SteamCMD persistent session for '{clean_user}'..."
            self.current_user = clean_user
            self.is_logged_in = False
            self.log_history = []
            self._target = target
            self._secrets = {value for value in (clean_pass, guard_code) if value}
            
            # Clear line queue
            while not self.line_queue.empty():
                try:
                    self.line_queue.get_nowait()
                except Exception:
                    break

            if log_callback:
                log_callback(self.status_message)

            # Sync and configure autologin beforehand
            if clean_user != "anonymous":
                configure_steam_autologin(clean_user)
            sync_steam_credentials()

            proc_env = os.environ.copy()
            proc_env["HOME"] = "/home/steam"

            # CRITICAL: Launch SteamCMD strictly in interactive console mode with NO "+" CLI arguments!
            # When SteamCMD receives "+" arguments on the command line, it runs in batch mode and terminates
            # after executing them. Without "+" arguments, it enters interactive mode and stays at Steam> forever.
            cmd = ["/bin/bash", STEAMCMD_BIN]

            try:
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=proc_env,
                    start_new_session=os.name == "posix",
                    cwd="/home/steam" if Path("/home/steam").exists() else None
                )
                self._reader_task = asyncio.create_task(self._stdout_reader())
            except Exception as e:
                self.state = "error"
                self.status_message = f"Failed to launch SteamCMD: {e}"
                if log_callback:
                    log_callback(self.status_message)
                raise RuntimeError(self.status_message)

            # 1. Wait for SteamCMD interactive shell to initialize
            ready = False
            start_init = time.time()
            while time.time() - start_init < 45.0:
                try:
                    line = await asyncio.wait_for(self.line_queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    if not self.is_alive():
                        break
                    continue

                if line is None:
                    break

                if log_callback:
                    log_callback(line)

                lower_line = line.lower()
                if "steamcmd needs to be online" in lower_line:
                    self.status_message = "SteamCMD could not reach Steam to update. Check the container's connection to Steam."
                    await self.terminate_session()
                    raise RuntimeError(self.status_message)
                if "loading steam api... ok" in lower_line or "type 'quit' to exit" in lower_line or "steam>" in lower_line:
                    ready = True
                    break

            if not ready or not self.is_alive() or not self.process or not self.process.stdin:
                self.state = "error"
                self.status_message = "SteamCMD failed to initialize interactive console."
                await self.terminate_session()
                raise RuntimeError(self.status_message)

            # Set the target before login, as required by SteamCMD.
            if install_path is not None:
                path = str(install_path)
                if any(char in path for char in '\r\n"'):
                    await self.terminate_session()
                    raise ValueError("The download destination contains unsupported characters.")
                self.process.stdin.write(f'force_install_dir "{path}"\n'.encode("utf-8"))
                if platform_type in ("windows", "linux", "macos"):
                    self.process.stdin.write(f"@sSteamCmdForcePlatformType {platform_type}\n".encode("utf-8"))

            # 2. Send login command directly to interactive stdin
            if clean_pass:
                if " " in clean_pass and not (clean_pass.startswith('"') and clean_pass.endswith('"')):
                    login_line = f'login {clean_user} "{clean_pass}"\n'
                else:
                    login_line = f"login {clean_user} {clean_pass}\n"
            else:
                login_line = f"login {clean_user}\n"

            if log_callback:
                log_callback(f">> Authenticating '{clean_user}' in persistent session...")

            if guard_code:
                # SteamCMD accepts a code before the login command in its interactive console.
                self.process.stdin.write(f"set_steam_guard_code {guard_code}\n".encode("utf-8"))
            self.state = "verifying_code" if guard_code else "signing_in"
            self.status_message = "SteamCMD is signing in to Steam…"
            self.process.stdin.write(login_line.encode("utf-8"))
            await self.process.stdin.drain()

            # 3. Monitor login output from line queue
            login_timeout = 120.0
            start_login = time.monotonic()

            while time.monotonic() - start_login < login_timeout:
                try:
                    line = await asyncio.wait_for(self.line_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    if not self.is_alive():
                        break
                    continue

                if line is None:
                    break

                if log_callback:
                    log_callback(line)

                lower_line = line.lower()

                if "waiting for confirmation" in lower_line and lower_line.endswith("ok"):
                    self.state = "starting"
                    self.status_message = "Steam Guard approved. Finishing Steam sign-in…"
                elif (
                    "confirm the login in the steam mobile app" in lower_line
                    or ("waiting for confirmation" in lower_line and "failed" not in lower_line)
                ):
                    self.state = "waiting_approval"
                    self.status_message = "Steam is waiting for approval. Open Steam Guard in the Steam Mobile app or use a code below."
                    if log_callback:
                        log_callback(f">> {self.status_message}")

                elif GUARD_CODE_PROMPT.search(line):
                    self.state = "waiting_code"
                    self.status_message = "SteamCMD is asking for a Steam Guard code. Use the current code from the app or your Steam email."
                    if log_callback:
                        log_callback(f">> {self.status_message}")

                # Detect successful authentication
                elif (
                    "logged in ok" in lower_line
                    or ("waiting for user info" in lower_line and lower_line.endswith("ok"))
                ):
                    self.is_logged_in = True
                    self.state = "authenticated"
                    self.status_message = f"Authenticated as '{clean_user}'! Persistent session is ready."
                    if log_callback:
                        log_callback(f">> {self.status_message}")
                    
                    # Persist authorized status to settings
                    if clean_user != "anonymous":
                        save_settings({"steamcmd_authorized": True, "steamcmd_username": clean_user})
                        sync_steam_credentials()
                    return True

                # Detect login failure
                elif "invalid password" in lower_line:
                    self.state = "error"
                    self.status_message = "Invalid Steam password. Please update your password in Settings."
                    await self.terminate_session()
                    raise ValueError(self.status_message)

                elif "failed" in lower_line and (
                    "waiting for confirmation" in lower_line or "account logon denied" in lower_line
                    or "account login denied" in lower_line or "invalid login auth code" in lower_line
                    or "two-factor code mismatch" in lower_line
                ):
                    self.state = "error"
                    self.status_message = "Steam Guard authorization failed. Retry with a fresh code from the Steam Mobile app or your Steam email."
                    await self.terminate_session()
                    raise RuntimeError(self.status_message)
                elif "failed with result code" in lower_line or "failed (" in lower_line:
                    self.state = "error"
                    self.status_message = f"Steam login failed: {line}"
                    await self.terminate_session()
                    raise RuntimeError(self.status_message)

            if self.is_logged_in:
                return True

            if not self.is_alive():
                self.state = "error"
                self.status_message = f"SteamCMD exited unexpectedly (exit code {self.process.returncode if self.process else 'unknown'})."
                await self.terminate_session()
                raise RuntimeError(self.status_message)

            if self.state in ("waiting_approval", "waiting_code", "verifying_code"):
                self.status_message = "Steam Guard timed out. Retry with a fresh code or approve the next sign-in in the Steam Mobile app."
            else:
                self.status_message = "SteamCMD timed out signing in to Steam. Check the container's connection to Steam and retry."
            self.state = "error"
            await self.terminate_session()
            raise TimeoutError(self.status_message)

    async def submit_steam_guard_code(self, code: str) -> bool:
        """Sends a 2FA Steam Guard code to the running SteamCMD process stdin."""
        if self.state != "waiting_code" or not self.is_alive() or not self.process or not self.process.stdin:
            raise ValueError("No active SteamCMD session waiting for code.")

        clean_code = normalize_guard_code(code)
        self._secrets.add(clean_code)
        self.log_history.append(">> Submitting Steam Guard code.")
        self.state = "verifying_code"
        self.status_message = "Submitted Steam Guard code, verifying..."
        self.process.stdin.write(f"{clean_code}\n".encode("utf-8"))
        await self.process.stdin.drain()
        return True

    async def run_download_job(
        self,
        appid: int,
        install_path: Path,
        platform_type: str = "windows",
        validate: bool = True,
        custom_args: str = "",
        username: str = "",
        password: str = "",
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[float, int, int, str], None]] = None
    ) -> bool:
        """
        Executes a game download job through the persistent SteamCMD session.
        Pipes commands directly to stdin without restarting SteamCMD or triggering mobile prompts.
        """
        # Ensure session is authenticated
        try:
            await self.ensure_session(
                username, password, log_callback, install_path=install_path, platform_type=platform_type
            )
            return await self._download(appid, validate, custom_args, log_callback, progress_callback)
        except (asyncio.CancelledError, Exception):
            await self.terminate_session()
            raise

    async def _download(self, appid, validate, custom_args, log_callback, progress_callback) -> bool:

        if not self.is_alive() or not self.process or not self.process.stdin:
            raise RuntimeError("SteamCMD process is not alive.")

        self.state = "downloading"
        self.status_message = f"Downloading AppID {appid}..."

        # Drain any leftover lines in queue before issuing new download
        while not self.line_queue.empty():
            try:
                self.line_queue.get_nowait()
            except Exception:
                break

        # Send download commands to SteamCMD via stdin
        commands = [command.strip() for command in custom_args.split("+") if command.strip()]

        app_update_cmd = f'app_update {appid}'
        if validate:
            app_update_cmd += ' validate'
        commands.append(app_update_cmd)

        if log_callback:
            log_callback(f"Executing in persistent session: {app_update_cmd}")

        for cmd_str in commands:
            self.process.stdin.write(f"{cmd_str}\n".encode("utf-8"))
        await self.process.stdin.drain()

        # Stream output until download completes or fails
        while True:
            try:
                line = await asyncio.wait_for(self.line_queue.get(), timeout=DOWNLOAD_OUTPUT_TIMEOUT)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("SteamCMD stopped reporting download progress.") from exc

            if line is None:  # Process exited
                raise RuntimeError("SteamCMD exited before confirming the download.")

            # Parse progress
            match = PROGRESS_REGEX.search(line)
            if match:
                state_code, state_name, pct_str, cur_b_str, tot_b_str = match.groups()
                pct = float(pct_str)
                cur_b = int(cur_b_str)
                tot_b = int(tot_b_str)
                if progress_callback:
                    progress_callback(pct, cur_b, tot_b, state_name.capitalize())
            if log_callback:
                log_callback(line)

            # Detect success
            success = SUCCESS_REGEX.search(line)
            if success and int(success.group(1)) == appid:
                self.state = "authenticated"
                return True

            # Detect failure conditions
            lower_line = line.lower()
            if "no subscription" in lower_line:
                raise RuntimeError("This app requires a Steam account that owns it (No subscription).")
            if "disk write failure" in lower_line:
                raise RuntimeError("SteamCMD could not write to the download destination.")
            if "enter password for user" in lower_line or "steamcmd has been disconnected" in lower_line:
                raise RuntimeError("SteamCMD disconnected or authorization expired.")
            if "error!" in lower_line or "failed to install" in lower_line or "before logon" in lower_line:
                raise RuntimeError(line)

    async def terminate_session(self):
        """Terminates the running SteamCMD process cleanly."""
        async with self._process_lock:
            self.is_logged_in = False
            self.state = "disconnected"
            process = self.process
            if process and process.returncode is None:
                if process.stdin:
                    try:
                        process.stdin.write(b"quit\n")
                        await process.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    try:
                        if os.name == "posix":
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()
            if self._reader_task:
                self._reader_task.cancel()
                await asyncio.gather(self._reader_task, return_exceptions=True)
            self.process = self._reader_task = None
            self._secrets.clear()


# Singleton instance shared across the application
steam_session = SteamCmdSessionWorker()
