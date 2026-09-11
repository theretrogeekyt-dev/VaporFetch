import unittest
from vaporfetch.downloader import DownloadTask, DownloadManager

class TestDownloader(unittest.TestCase):
    def test_download_task_to_dict(self):
        task = DownloadTask(appid=730, name="Counter-Strike 2", platform="windows")
        d = task.to_dict()
        self.assertEqual(d["appid"], 730)
        self.assertEqual(d["name"], "Counter-Strike 2")
        self.assertEqual(d["platform"], "windows")
        self.assertEqual(d["status"], "queued")
        self.assertEqual(d["percent"], 0.0)

    def test_queue_operations(self):
        mgr = DownloadManager()
        # Ensure clean state
        mgr.clear_queue()

        # Add single
        added = mgr.add_to_queue(400, "Portal", "linux")
        self.assertTrue(added)

        # Duplicate should be rejected
        added_dup = mgr.add_to_queue(400, "Portal", "linux")
        self.assertFalse(added_dup)

        # Add batch
        batch = [
            {"appid": 440, "name": "Team Fortress 2"},
            {"appid": 550, "name": "Left 4 Dead 2"},
            {"appid": 400, "name": "Portal"}, # Should be skipped since already queued
        ]
        count = mgr.add_batch(batch, platform="windows")
        self.assertEqual(count, 2)

        # Check queue length
        state = mgr.get_queue_state()
        self.assertEqual(len(state["queue"]), 3)

        # Remove item
        removed = mgr.remove_from_queue(440)
        self.assertTrue(removed)
        state = mgr.get_queue_state()
        self.assertEqual(len(state["queue"]), 2)

        # Clear queue
        mgr.clear_queue()
        state = mgr.get_queue_state()
        self.assertEqual(len(state["queue"]), 0)

    def test_run_app_download_without_credentials(self):
        from unittest.mock import patch
        from vaporfetch.steamcmd import run_app_download, auth_session
        auth_session.reset()
        with patch("vaporfetch.steamcmd.has_steamcmd_cached_credentials", return_value=False):
            res = run_app_download(
                appid=2280,
                install_dir="/downloads/DOOM + DOOM II",
                username="reaper360vr",
            )
            self.assertFalse(res["success"])
            self.assertIn("Steam authentication not found", res["error"])

    def test_run_app_download_with_qr_session_fails_fast_without_steamcmd_credentials(self):
        from unittest.mock import patch
        from vaporfetch.steamcmd import run_app_download, auth_session
        auth_session.reset()
        qr_session = {"username": "reaper360vr", "logged_in": True, "auth_method": "qr"}
        with patch("vaporfetch.steamcmd.has_steamcmd_cached_credentials", return_value=False), \
             patch("vaporfetch.steamcmd.get_current_session", return_value=qr_session):
            res = run_app_download(
                appid=2280,
                install_dir="/downloads/DOOM + DOOM II",
                username="reaper360vr",
            )
            self.assertFalse(res["success"])
            self.assertIn("Steam Mobile QR Code only authorizes library sync", res["error"])

    def test_run_app_download_sanitizes_plus_in_cmd(self):
        from unittest.mock import patch, MagicMock
        from vaporfetch.steamcmd import run_app_download, auth_session
        auth_session.reset()
        auth_session.pending_password = "dummy"
        auth_session.username = "testuser"

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = ""
        mock_proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
             patch("os.makedirs"):
            run_app_download(
                appid=2280,
                install_dir="/downloads/DOOM + DOOM II",
                username="testuser",
            )
            mock_popen.assert_called_once()
            called_cmd = mock_popen.call_args[0][0]
            # Ensure install_dir argument had '+' replaced with '_' and is quoted for spaces
            self.assertIn('"/downloads/DOOM _ DOOM II"', called_cmd)
            self.assertNotIn("/downloads/DOOM + DOOM II", called_cmd)
            # Ensure password was NOT placed in CLI arguments
            self.assertNotIn("dummy", called_cmd)
            # Ensure +quit is omitted so SteamCMD runs in interactive PTY mode
            self.assertNotIn("+quit", called_cmd)
            # Ensure @sSteamCmdForcePlatformType precedes +login per Valve specification
            self.assertIn("+@sSteamCmdForcePlatformType", called_cmd)
            self.assertLess(called_cmd.index("+@sSteamCmdForcePlatformType"), called_cmd.index("+login"))

    def test_run_app_download_success_flow(self):
        from unittest.mock import patch, MagicMock
        from vaporfetch.steamcmd import run_app_download, auth_session
        auth_session.reset()
        auth_session.pending_password = "dummy"
        auth_session.username = "testuser"

        logs = []
        progresses = []

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc), \
             patch("select.select", return_value=([999], [], [])), \
             patch("os.read", side_effect=[
                 b"Update state (0x61) downloading, progress: 50.00 (500 / 1000)\nSuccess! App '1148590' fully installed.\n",
                 b""
             ]), \
             patch("os.makedirs"), \
             patch("os.close"):
            res = run_app_download(
                appid=1148590,
                install_dir="/downloads/DOOM 64",
                username="testuser",
                log_cb=lambda l: logs.append(l),
                progress_cb=lambda p: progresses.append(p),
            )
            self.assertTrue(res["success"])
            self.assertTrue(any("fully installed" in l for l in logs))

    def test_run_app_download_filters_breakpad_stderr(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from vaporfetch.steamcmd import run_app_download, auth_session
        auth_session.reset()
        auth_session.pending_password = "dummy"
        auth_session.username = "testuser"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 254

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_stderr = Path(tmpdir) / ".steam" / "steam" / "logs" / "stderr.txt"
            fake_stderr.parent.mkdir(parents=True, exist_ok=True)
            fake_stderr.write_text(
                "flock /sys/devices/virtual/dmi/id/sys_vendor LOCK_SH failed. errno = 13\n"
                "09/11 23:06:52 Init: Installing breakpad exception handler for appid(steam)/version(1788292693)/tid(91)\n"
                "UpdateUI: skip show logo\n",
                encoding="utf-8"
            )

            with patch("subprocess.Popen", return_value=mock_proc), \
                 patch("select.select", return_value=([], [], [])), \
                 patch("os.environ", {"HOME": tmpdir}), \
                 patch("os.makedirs"), \
                 patch("os.close"):
                res = run_app_download(
                    appid=1148590,
                    install_dir="/downloads/DOOM 64",
                    username="testuser",
                )
                self.assertFalse(res["success"])
                # Breakpad banner and hardware locks should be filtered out
                self.assertNotIn("Installing breakpad exception handler", res["error"])
                self.assertNotIn("flock /sys/devices", res["error"])
                self.assertIn("SteamCMD process exited with code 254", res["error"])


    def test_save_current_session_preserves_metadata(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from vaporfetch.steamcmd import save_current_session, get_current_session

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_session = Path(tmpdir) / "session.json"
            with patch("vaporfetch.steamcmd.SESSION_FILE", temp_session):
                # Step 1: Save QR session with steam_id and access_token
                save_current_session("reaper360vr", logged_in=True, steam_id="76561199132013751", access_token="token123", auth_method="qr")
                s1 = get_current_session()
                self.assertEqual(s1["steam_id"], "76561199132013751")
                self.assertEqual(s1["access_token"], "token123")

                # Step 2: Authenticate SteamCMD (steam_id passed as empty)
                save_current_session("reaper360vr", logged_in=True, steam_id="", auth_method="steamcmd")
                s2 = get_current_session()
                # steam_id and access_token should still be preserved
                self.assertEqual(s2["steam_id"], "76561199132013751")
                self.assertEqual(s2["access_token"], "token123")
                self.assertEqual(s2["auth_method"], "steamcmd")

    def test_safe_write_json_normal(self):
        import json
        import tempfile
        from pathlib import Path
        from vaporfetch.config import safe_write_json

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test.json"
            safe_write_json(target, {"hello": "world"})
            self.assertTrue(target.exists())
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data, {"hello": "world"})

    def test_safe_write_json_permission_error_fallback(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from vaporfetch.config import safe_write_json

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "test_perm.json"
            target.write_text("{}", encoding="utf-8")

            original_open = open
            attempt = 0

            def mock_open_func(file, mode="r", *args, **kwargs):
                nonlocal attempt
                if Path(file) == target and "w" in mode:
                    attempt += 1
                    if attempt == 1:
                        raise PermissionError("Simulated permission error")
                return original_open(file, mode, *args, **kwargs)

            with patch("builtins.open", side_effect=mock_open_func):
                safe_write_json(target, {"recovered": True})

            self.assertEqual(attempt, 2)
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data, {"recovered": True})

if __name__ == "__main__":
    unittest.main()


