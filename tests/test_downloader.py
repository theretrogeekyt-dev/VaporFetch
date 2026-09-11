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

    def test_run_app_download_sanitizes_plus_in_cmd(self):
        from unittest.mock import patch, MagicMock
        from vaporfetch.steamcmd import run_app_download, auth_session
        auth_session.reset()
        auth_session.pending_password = "dummy"
        auth_session.username = "testuser"

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = ""
        mock_proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            run_app_download(
                appid=2280,
                install_dir="/downloads/DOOM + DOOM II",
                username="testuser",
            )
            mock_popen.assert_called_once()
            called_cmd = mock_popen.call_args[0][0]
            # Ensure install_dir argument had '+' replaced with '_'
            self.assertIn("/downloads/DOOM _ DOOM II", called_cmd)
            self.assertNotIn("/downloads/DOOM + DOOM II", called_cmd)

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

if __name__ == "__main__":
    unittest.main()

