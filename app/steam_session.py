import os
import re
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

class SteamCmdSessionWorker:
    """
    Manages a long-running, persistent SteamCMD process.
    Keeping SteamCMD running in interactive mode avoids repetitive logins,
    which is the root cause of Steam Mobile Authenticator push notifications
    on every individual game download.
    """
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.state: str = "disconnected"  # disconnected, starting, waiting_approval, waiting_code, authenticated, downloading, error
        self.status_message: str = ""
        self.current_user: str = ""
        self.is_logged_in: bool = False
        self.log_history: List[str] = []
        self.line_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

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
        """Reads stdout from the SteamCMD subprocess line by line and queues it."""
        try:
            while self.is_alive():
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue

                self.log_history.append(line)
                if len(self.log_history) > 120:
                    self.log_history.pop(0)

                await self.line_queue.put(line)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log_history.append(f"[SessionWorker] Reader error: {e}")
        finally:
            self.is_logged_in = False
            await self.line_queue.put(None)  # Sentinel for EOF

    async def ensure_session(self, username: str, password: str = "", log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Ensures a persistent SteamCMD process is running and logged in.
        If already logged in as the requested user, returns immediately with 0 prompts.
        """
        async with self._lock:
            settings = load_settings()
            clean_user = (username or settings.get("steamcmd_username", "")).strip()
            clean_pass = password if password is not None else settings.get("steamcmd_password", "")

            if not clean_user:
                raise ValueError("Steam username is required to start SteamCMD session.")

            # If already alive, authenticated, and matching user, return immediately
            if self.is_ready() and self.current_user.lower() == clean_user.lower():
                if log_callback:
                    log_callback(f"Using active persistent SteamCMD session for '{clean_user}' (no phone prompt).")
                return True

            # If process is running but wrong user or disconnected, terminate first
            if self.is_alive():
                await self.terminate_session()

            self.state = "starting"
            self.status_message = f"Starting SteamCMD persistent session for '{clean_user}'..."
            self.current_user = clean_user
            self.is_logged_in = False
            self.log_history = []
            
            # Clear line queue
            while not self.line_queue.empty():
                try:
                    self.line_queue.get_nowait()
                except Exception:
                    break

            if log_callback:
                log_callback(self.status_message)

            # Sync and configure autologin beforehand
            configure_steam_autologin(clean_user)
            sync_steam_credentials()

            proc_env = os.environ.copy()
            proc_env["HOME"] = "/home/steam"

            # Launch SteamCMD in interactive daemon mode with +login
            cmd = ["/bin/bash", STEAMCMD_BIN]
            if clean_pass:
                cmd.extend(["+login", clean_user, clean_pass])
            else:
                cmd.extend(["+login", clean_user])

            try:
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=proc_env,
                    cwd="/home/steam" if Path("/home/steam").exists() else None
                )
                self._reader_task = asyncio.create_task(self._stdout_reader())
            except Exception as e:
                self.state = "error"
                self.status_message = f"Failed to launch SteamCMD: {e}"
                if log_callback:
                    log_callback(self.status_message)
                raise RuntimeError(self.status_message)

            # Monitor startup / login output
            login_timeout = 120.0  # Allow up to 2 minutes for user to tap Approve on mobile
            start_time = time.time()

            while time.time() - start_time < login_timeout:
                try:
                    line = await asyncio.wait_for(self.line_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    if not self.is_alive():
                        break
                    continue

                if line is None:  # Process exited
                    break

                if log_callback:
                    log_callback(line)

                lower_line = line.lower()

                # Detect 2FA mobile authenticator request
                if (
                    "confirm the login in the steam mobile app" in lower_line
                    or "waiting for confirmation" in lower_line
                    or ("logging in user" in lower_line and "to steam public" in lower_line)
                ):
                    self.state = "waiting_approval"
                    self.status_message = "Steam Guard request sent! Please tap 'Approve' on your Steam Mobile app."
                    if log_callback:
                        log_callback(f">> {self.status_message}")

                # Detect 2FA code requirement
                elif "steam guard code" in lower_line or "authenticator code" in lower_line:
                    self.state = "waiting_code"
                    self.status_message = "Steam Guard code required. Enter code in Settings."
                    if log_callback:
                        log_callback(f">> {self.status_message}")

                # Detect successful authentication
                elif (
                    "logged in ok" in lower_line 
                    or "waiting for user info" in lower_line 
                    or "waiting for client config" in lower_line
                    or "waiting for confirmation...ok" in lower_line
                ):
                    self.is_logged_in = True
                    self.state = "authenticated"
                    self.status_message = f"Authenticated as '{clean_user}'! Persistent session is ready."
                    if log_callback:
                        log_callback(f">> {self.status_message}")
                    
                    # Persist authorized status to settings
                    save_settings({"steamcmd_authorized": True, "steamcmd_username": clean_user})
                    sync_steam_credentials()
                    return True

                # Detect login failure
                elif "invalid password" in lower_line:
                    self.state = "error"
                    self.status_message = "Invalid Steam password. Please update your password in Settings."
                    await self.terminate_session()
                    raise ValueError(self.status_message)

                elif "failed with result code" in lower_line or "failed (account logon denied)" in lower_line:
                    self.state = "error"
                    self.status_message = f"Steam login failed: {line}"
                    await self.terminate_session()
                    raise RuntimeError(self.status_message)

            # Check if logged in before timeout
            if self.is_logged_in:
                return True

            if not self.is_alive():
                self.state = "error"
                self.status_message = f"SteamCMD exited unexpectedly (exit code {self.process.returncode if self.process else 'unknown'})."
                await self.terminate_session()
                raise RuntimeError(self.status_message)

            self.state = "error"
            self.status_message = "SteamCMD login timed out waiting for mobile approval."
            await self.terminate_session()
            raise TimeoutError(self.status_message)

    async def submit_steam_guard_code(self, code: str) -> bool:
        """Sends a 2FA Steam Guard code to the running SteamCMD process stdin."""
        if not self.is_alive() or not self.process or not self.process.stdin:
            raise ValueError("No active SteamCMD session waiting for code.")

        clean_code = code.strip()
        self.log_history.append(f">> Submitting Steam Guard code: {clean_code[:2]}***")
        self.process.stdin.write(f"{clean_code}\n".encode("utf-8"))
        await self.process.stdin.drain()
        self.status_message = "Submitted Steam Guard code, verifying..."
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
        await self.ensure_session(username, password, log_callback)

        if not self.is_alive() or not self.process or not self.process.stdin:
            raise RuntimeError("SteamCMD process is not alive.")

        self.state = "downloading"
        self.status_message = f"Downloading AppID {appid} to {install_path}..."

        # Drain any leftover lines in queue before issuing new download
        while not self.line_queue.empty():
            try:
                self.line_queue.get_nowait()
            except Exception:
                break

        # Send download commands to SteamCMD via stdin
        commands = [
            f'force_install_dir "{install_path}"',
        ]
        if platform_type in ("windows", "linux", "macos"):
            commands.append(f'@sSteamCmdForcePlatformType {platform_type}')
        if custom_args:
            for arg in custom_args.split():
                if arg:
                    clean_arg = arg.lstrip('+')
                    commands.append(clean_arg)

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
        download_success = False
        error_message = ""

        while self.is_alive():
            try:
                line = await asyncio.wait_for(self.line_queue.get(), timeout=180.0)
            except asyncio.TimeoutError:
                if not self.is_alive():
                    break
                # Heartbeat check
                if log_callback:
                    log_callback("... waiting for SteamCMD download progress ...")
                continue

            if line is None:  # Process exited
                break

            if log_callback:
                log_callback(line)

            # Parse progress
            match = PROGRESS_REGEX.search(line)
            if match:
                state_code, state_name, pct_str, cur_b_str, tot_b_str = match.groups()
                pct = float(pct_str)
                cur_b = int(cur_b_str)
                tot_b = int(tot_b_str)
                if progress_callback:
                    progress_callback(pct, cur_b, tot_b, state_name.capitalize())

            # Detect success
            if "Success! App" in line:
                download_success = True
                if progress_callback:
                    progress_callback(100.0, 0, 0, "Success")
                break

            # Detect failure conditions
            if "ERROR!" in line or "Failed to install" in line:
                error_message = line
                break
            elif "No subscription" in line:
                error_message = "Steam account does not own this game (No subscription)."
                break
            elif "Disk write failure" in line:
                error_message = "Disk write failure in destination folder."
                break
            elif "Enter password for user" in line or "steamcmd has been disconnected" in line:
                self.is_logged_in = False
                error_message = "SteamCMD session disconnected or authorization expired."
                break

        self.state = "authenticated" if self.is_logged_in else "disconnected"

        if download_success:
            return True
        else:
            raise RuntimeError(error_message or "SteamCMD download failed.")

    async def terminate_session(self):
        """Terminates the running SteamCMD process cleanly."""
        self.is_logged_in = False
        self.state = "disconnected"
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        if self.process and self.process.returncode is None:
            try:
                if self.process.stdin:
                    self.process.stdin.write(b"quit\n")
                    await self.process.stdin.drain()
            except Exception:
                pass

            try:
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        self.process = None


# Singleton instance shared across the application
steam_session = SteamCmdSessionWorker()

