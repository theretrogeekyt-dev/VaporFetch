import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.config import (
    STEAMCMD_BIN, 
    STEAM_HOME_DIR, 
    load_settings, 
    save_settings, 
    sync_steam_credentials,
    has_steam_credentials
)

class SteamCmdAuthManager:
    def __init__(self):
        self.active_process: Optional[asyncio.subprocess.Process] = None
        self.state: str = "idle"  # idle, starting, waiting_approval, waiting_code, success, error
        self.status_message: str = ""
        self.log_lines: List[str] = []
        self._auth_task: Optional[asyncio.Task] = None

    def get_status(self) -> Dict[str, Any]:
        settings = load_settings()
        sync_steam_credentials()
        sentry_files = list(STEAM_HOME_DIR.glob("ssfn*"))
        is_authorized = has_steam_credentials()
        
        return {
            "authorized": is_authorized,
            "has_sentry": len(sentry_files) > 0,
            "sentry_count": len(sentry_files),
            "state": self.state,
            "status_message": self.status_message,
            "username": settings.get("steamcmd_username", ""),
            "has_password": bool(settings.get("steamcmd_password")),
            "logs": self.log_lines[-20:],
        }

    async def start_authorization(self, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
        """Starts a managed SteamCMD execution to authorize this device once and for all."""
        settings = load_settings()
        username = (username or settings.get("steamcmd_username", "")).strip()
        password = (password or settings.get("steamcmd_password", "")).strip()

        if not username:
            raise ValueError("Steam username is required for authorization.")
        if not password:
            raise ValueError("Steam password is required for initial device authorization.")

        if self.active_process and self.active_process.returncode is None:
            try:
                self.active_process.terminate()
            except Exception:
                pass

        self.state = "starting"
        self.status_message = "Starting SteamCMD authorization..."
        self.log_lines = []

        # Ensure sentry files are synced beforehand
        sync_steam_sentry_files()

        self._auth_task = asyncio.create_task(self._run_authorization_process(username, password))
        return self.get_status()

    async def _run_authorization_process(self, username: str, password: str):
        proc_env = os.environ.copy()
        proc_env["HOME"] = "/home/steam"

        cmd = [
            "/bin/bash",
            STEAMCMD_BIN,
            "+login",
            username,
            password,
            "+quit"
        ]

        self.log_lines.append(f"Executing: SteamCMD +login {username} ****** +quit")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
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

                self.log_lines.append(line)
                if len(self.log_lines) > 100:
                    self.log_lines.pop(0)

                # State detection
                lower_line = line.lower()
                if "logging in user" in lower_line and "to steam public" in lower_line:
                    self.state = "waiting_approval"
                    self.status_message = "Steam Guard request sent! Please tap 'Approve' on your Steam Mobile app."
                elif "waiting for user info" in lower_line or "logged in ok" in lower_line or "success! app" in lower_line:
                    self.state = "success"
                    self.status_message = "Logged in successfully! Finalizing device authorization..."
                elif "steam guard code" in lower_line or "authenticator code" in lower_line:
                    self.state = "waiting_code"
                    self.status_message = "Steam Guard code required. Enter the 2FA code from your Steam Mobile app."
                elif "invalid password" in lower_line:
                    self.state = "error"
                    self.status_message = "Invalid Steam password. Please check your password in Settings."
                elif "failed with result code" in lower_line:
                    self.state = "error"
                    self.status_message = f"Login failed: {line}"

            returncode = await process.wait()

            if returncode == 0 or self.state == "success":
                self.state = "success"
                self.status_message = "Device authorized successfully! One and done — future downloads will run without prompts."
                # Sync new sentry files and config.vdf to persistent volume
                sync_steam_credentials()
                save_settings({
                    "steamcmd_authorized": True,
                    "steamcmd_username": username,
                    "steamcmd_password": password
                })
            elif self.state != "error":
                self.state = "error"
                if not self.status_message or self.status_message.startswith("Steam Guard request"):
                    self.status_message = f"Authorization process ended with exit code {returncode}."
        except asyncio.CancelledError:
            self.state = "idle"
            self.status_message = "Authorization cancelled."
            if self.active_process:
                try:
                    self.active_process.kill()
                except Exception:
                    pass
        except Exception as e:
            self.state = "error"
            self.status_message = f"Error during authorization: {e}"
        finally:
            self.active_process = None

    async def send_code(self, code: str) -> Dict[str, Any]:
        """Sends a 2FA Steam Guard code to the running SteamCMD process stdin."""
        if not self.active_process or self.active_process.returncode is not None:
            raise ValueError("No active SteamCMD authorization process waiting for code.")
        
        if not self.active_process.stdin:
            raise ValueError("Process stdin is not open.")

        clean_code = code.strip()
        self.log_lines.append(f">> Sending Steam Guard Code: {clean_code[:2]}***")
        self.active_process.stdin.write(f"{clean_code}\n".encode("utf-8"))
        await self.active_process.stdin.drain()
        self.status_message = "Submitted Steam Guard code, verifying..."
        return self.get_status()

    def cancel(self):
        """Cancels any running authorization process."""
        if self._auth_task and not self._auth_task.done():
            self._auth_task.cancel()
        if self.active_process and self.active_process.returncode is None:
            try:
                self.active_process.terminate()
            except Exception:
                pass
        self.state = "idle"
        self.status_message = "Authorization cancelled."


steamcmd_auth_manager = SteamCmdAuthManager()

