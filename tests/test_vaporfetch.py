import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

# Import the application against an isolated data directory.
test_home = tempfile.TemporaryDirectory()
with patch.dict(os.environ, {
    "DATA_DIR": str(Path(test_home.name) / "data"),
    "DOWNLOAD_DIR": str(Path(test_home.name) / "downloads"),
}):
    from app import main
    from app.goldberg import GoldbergManager
    from app.queue_manager import DownloadQueueManager, QueueItem, safe_install_path
    from app.steam_session import SteamCmdSessionWorker
    from app.storage import write_json


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://vaporfetch"
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_dashboard_routes(self):
        for path in ("/desktop", "/mobile"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("appIdForm", response.text)
        self.assertIn("mobile-tab-view", (await self.client.get("/", headers={"user-agent": "Android"})).text)
        self.assertEqual((await self.client.get("/healthz")).json(), {"status": "ok"})

    async def test_validation_is_all_or_nothing(self):
        with patch.object(main.queue_manager, "add_to_queue") as add:
            response = await self.client.post("/api/queue", json={"games": [{"appid": 740}, {"name": "Invalid"}]})
            self.assertEqual(response.status_code, 422)
            add.assert_not_called()

    async def test_administrator_and_origin_checks(self):
        with patch.multiple(main, ADMIN_USER="admin", ADMIN_PASSWORD="test-password"):
            self.assertEqual((await self.client.get("/api/queue")).status_code, 401)
            self.assertEqual((await self.client.get("/healthz")).status_code, 200)
            auth = ("admin", "test-password")
            self.assertEqual((await self.client.get("/api/queue", auth=auth)).status_code, 200)
            result = await self.client.post("/api/auth/logout", auth=auth, headers={"Origin": "https://other.test"})
            self.assertEqual(result.status_code, 403)

    async def test_session_response_keeps_tokens_private(self):
        session = {"steamid": "76561198000000000", "personaname": "Example", "access_token": "secret"}
        with patch.object(main.auth_manager, "get_session", return_value=session):
            response = await self.client.get("/api/auth/session")
            self.assertEqual(response.json()["session"]["personaname"], "Example")
            self.assertNotIn("access_token", response.json()["session"])
            self.assertEqual(response.headers["cache-control"], "no-store")


class QueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.downloads = Path(directory.name) / "downloads"
        self.downloads.mkdir()
        self.queue_file = Path(directory.name) / "queue.json"
        override = patch.multiple("app.queue_manager", QUEUE_FILE=self.queue_file, DOWNLOAD_DIR=self.downloads)
        override.start()
        self.addCleanup(override.stop)

    async def test_failed_directory_does_not_stop_next_download(self):
        manager = DownloadQueueManager()
        (self.downloads / "Samename [1]").touch()
        runner = AsyncMock()
        with patch("app.queue_manager.steam_session.run_download_job", runner):
            first, second = manager.add_to_queue([
                {"appid": 1, "name": "Same/name"}, {"appid": 2, "name": "Same name"},
            ])
            await asyncio.wait_for(manager._worker_task, 2)
        self.assertEqual((first.status, second.status), ("failed", "completed"))
        self.assertEqual(Path(second.install_dir).name, "Same name [2]")
        self.assertEqual(runner.await_count, 1)
        self.assertEqual(DownloadQueueManager().items[1].status, "completed")

    async def test_cancel_finishes_cleanup_before_next_job(self):
        manager = DownloadQueueManager()
        first_started = asyncio.Event()
        first_stopped = asyncio.Event()

        async def run(**kwargs):
            if kwargs["appid"] == 1:
                try:
                    first_started.set()
                    await asyncio.Future()
                finally:
                    await asyncio.sleep(0)
                    first_stopped.set()
            else:
                self.assertTrue(first_stopped.is_set())

        with patch("app.queue_manager.steam_session.run_download_job", run):
            first, second = manager.add_to_queue([{"appid": 1}, {"appid": 2}])
            await asyncio.wait_for(first_started.wait(), 2)
            self.assertTrue(manager.remove_from_queue(first.id))
            self.assertEqual(first.status, "cancelling")
            await asyncio.wait_for(manager._worker_task, 2)
        self.assertEqual((first.status, second.status), ("cancelled", "completed"))
        self.assertIsNone(manager.active_item)

    async def test_interrupted_queue_and_legacy_install(self):
        legacy = self.downloads / "Old game"
        legacy.mkdir()
        (legacy / "appmanifest_123.acf").touch()
        write_json(self.queue_file, [
            {"invalid": True},
            QueueItem(appid=123, name="New title", status="running", progress=40).model_dump(),
        ])
        manager = DownloadQueueManager()
        item, = manager.items
        self.assertEqual((item.status, item.progress), ("queued", 0))
        self.assertEqual(manager._install_path(item), legacy)
        self.assertFalse(safe_install_path(self.downloads / ".."))

    async def test_atomic_save_failure_does_not_add_jobs(self):
        manager = DownloadQueueManager()
        with patch.object(manager, "_save_queue", side_effect=OSError("volume is read-only")):
            with self.assertRaises(OSError):
                manager.add_to_queue([{"appid": 1}])
        self.assertEqual(manager.items, [])


FAKE_STEAMCMD = """
import sys

sys.stdout.write("Steam>")
sys.stdout.flush()
target_set = False
for command in sys.stdin:
    if command.startswith("force_install_dir "):
        target_set = True
    elif command.startswith("login "):
        if not target_set:
            print("ERROR! Please set the install directory before login.", flush=True)
            break
        print("Logged in OK", flush=True)
    elif command.startswith("app_update "):
        print("Success! App '999' fully installed.", flush=True)
        sys.stdout.write("Update state (0x5) downloading, progress: 50.00 (10 / 20)\\r")
        print("Success! App '740' fully installed.", flush=True)
    elif command.strip() == "quit":
        break
"""


class SteamCmdTests(unittest.IsolatedAsyncioTestCase):
    async def start_fake_login(self, script, **kwargs):
        spawn = asyncio.create_subprocess_exec

        async def spawn_fake(*args, **options):
            return await spawn(sys.executable, "-u", "-c", script, **options)

        worker = SteamCmdSessionWorker()
        self.addAsyncCleanup(worker.terminate_session)
        patches = patch.multiple(
            "app.steam_session", configure_steam_autologin=lambda user: None,
            sync_steam_credentials=lambda: None, save_settings=lambda settings: None,
        )
        patches.start()
        self.addCleanup(patches.stop)
        launch = patch("app.steam_session.asyncio.create_subprocess_exec", spawn_fake)
        launch.start()
        self.addCleanup(launch.stop)
        task = asyncio.create_task(worker.ensure_session("test_user", "test_password", **kwargs))

        async def stop():
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        self.addAsyncCleanup(stop)
        return worker, task

    async def test_login_progress_waits_for_actual_guard_prompt(self):
        worker, task = await self.start_fake_login("""
import sys
print("Steam>", end="", flush=True)
sys.stdin.readline()
print("Logging in user 'test_user' to Steam Public...", flush=True)
sys.stdin.readline()
print("Enter code:", end="", flush=True)
code = sys.stdin.readline().strip()
print(f"Submitted {code}", flush=True)
print("Waiting for user info...OK", flush=True)
sys.stdin.readline()
""")
        async with asyncio.timeout(5):
            while not any("Logging in user" in line for line in worker.log_history):
                await asyncio.sleep(0.01)
            self.assertEqual(worker.state, "signing_in")
            worker.process.stdin.write(b"\n")
            await worker.process.stdin.drain()
            while worker.state != "waiting_code":
                await asyncio.sleep(0.01)
            await worker.submit_steam_guard_code("abc23")
            self.assertTrue(await task)
        self.assertNotIn("ABC23", "\n".join(worker.log_history))

    async def test_code_retry_sets_guard_code_before_login_and_redacts_it(self):
        worker, task = await self.start_fake_login("""
import sys
print("Steam>", end="", flush=True)
command = sys.stdin.readline().strip()
assert command == "set_steam_guard_code ABC23"
print(command, flush=True)
assert sys.stdin.readline().strip() == "login test_user test_password"
print("Waiting for user info...OK", flush=True)
sys.stdin.readline()
""", guard_code="ABC23")
        self.assertTrue(await asyncio.wait_for(task, 5))
        self.assertIn("set_steam_guard_code [redacted]", worker.log_history)

    async def test_install_path_precedes_login_and_success_matches_appid(self):
        spawn = asyncio.create_subprocess_exec

        async def spawn_fake(*args, **kwargs):
            return await spawn(sys.executable, "-u", "-c", FAKE_STEAMCMD, **kwargs)

        worker = SteamCmdSessionWorker()
        self.addAsyncCleanup(worker.terminate_session)
        progress = []
        with patch("app.steam_session.asyncio.create_subprocess_exec", spawn_fake), patch(
            "app.steam_session.sync_steam_credentials"
        ):
            ok = await asyncio.wait_for(worker.run_download_job(
                appid=740, install_path=Path(test_home.name), username="anonymous",
                progress_callback=lambda *args: progress.append(args),
            ), 5)
        self.assertTrue(ok)
        self.assertEqual(progress, [(50.0, 10, 20, "Downloading")])
        self.assertEqual(worker.state, "authenticated")


class GoldbergTests(unittest.TestCase):
    def test_revert_preserves_existing_and_edited_game_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder)
            dll = game / "steam_api.dll"
            dll.write_bytes(b"authentic DLL")
            (game / "steam_appid.txt").write_text("owned by the game")
            settings = game / "steam_settings"
            settings.mkdir()
            (settings / "game-setting.txt").write_text("keep")
            wrapper = GoldbergManager()
            wrapper.apply(game, 740)
            (settings / "force_account_name.txt").write_text("operator edit")
            wrapper.revert(game)
            self.assertEqual(dll.read_bytes(), b"authentic DLL")
            self.assertEqual((game / "steam_appid.txt").read_text(), "owned by the game")
            self.assertEqual((settings / "game-setting.txt").read_text(), "keep")
            self.assertEqual((settings / "force_account_name.txt").read_text(), "operator edit")
            self.assertFalse((settings / "steam_appid.txt").exists())


if __name__ == "__main__":
    unittest.main()
