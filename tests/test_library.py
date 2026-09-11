import unittest
import tempfile
import os
from pathlib import Path
from vaporfetch.library import (
    sanitize_folder_name,
    format_bytes,
    check_backup_status,
    resolver,
)

class TestLibrary(unittest.TestCase):
    def test_sanitize_folder_name(self):
        self.assertEqual(sanitize_folder_name("Half-Life 2: Episode One"), "Half-Life 2_ Episode One")
        self.assertEqual(sanitize_folder_name("Cyberpunk 2077 // DLC *Special*"), "Cyberpunk 2077 __ DLC _Special_")
        self.assertEqual(sanitize_folder_name("DOOM + DOOM II"), "DOOM _ DOOM II")
        self.assertEqual(sanitize_folder_name("   Spaces   "), "Spaces")
        self.assertEqual(sanitize_folder_name(""), "Unknown_Game")

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(1024), "1 KB")
        self.assertEqual(format_bytes(1048576), "1 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")
        self.assertEqual(format_bytes(5368709120), "5.00 GB")

    def test_app_resolver(self):
        # Known common games in built-in mapping
        self.assertEqual(resolver.resolve_name(730), "Counter-Strike 2")
        self.assertEqual(resolver.resolve_name(400), "Portal")
        self.assertEqual(resolver.resolve_name(105600), "Terraria")
        self.assertEqual(resolver.resolve_name(1148590), "DOOM 64")
        # Known tools / dedicated servers
        self.assertEqual(resolver.resolve_name(5), "Dedicated Server")
        self.assertEqual(resolver.resolve_name(90), "Half-Life Dedicated Server")
        # Unknown offline game fallback
        self.assertEqual(resolver.resolve_name(99999999), "Steam App 99999999")

    def test_populate_and_cache_games(self):
        from vaporfetch.library import populate_and_cache_games
        games = populate_and_cache_games({730, 400, 5, 90})
        self.assertEqual(len(games), 4)
        games_by_id = {g["appid"]: g for g in games}
        self.assertFalse(games_by_id[730]["is_tool"])
        self.assertFalse(games_by_id[400]["is_tool"])
        self.assertTrue(games_by_id[5]["is_tool"])
        self.assertTrue(games_by_id[90]["is_tool"])

    def test_app_resolver_steamspy(self):
        from unittest.mock import patch, MagicMock
        import json
        from vaporfetch.library import AppResolver

        custom_resolver = AppResolver()
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "appid": 888888,
            "name": "Custom Indie Game"
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            name = custom_resolver.resolve_name(888888)
            self.assertEqual(name, "Custom Indie Game")

    def test_get_library_web_api(self):
        from unittest.mock import patch, MagicMock
        import json
        from vaporfetch.library import get_library

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "response": {
                "game_count": 2,
                "games": [
                    {"appid": 730, "name": "Counter-Strike 2"},
                    {"appid": 400, "name": "Portal"}
                ]
            }
        }).encode("utf-8")

        mock_session = {
            "username": "reaper360vr",
            "steam_id": "76561198000000000",
            "auth_method": "qr"
        }
        mock_settings = {
            "steam_api_key": "TEST_KEY_123"
        }

        with patch("vaporfetch.library.get_current_session", return_value=mock_session), \
             patch("vaporfetch.library.load_settings", return_value=mock_settings), \
             patch("urllib.request.urlopen", return_value=mock_resp), \
             patch("vaporfetch.library.LIBRARY_CACHE_FILE", Path("/tmp/fake_library_cache.json")):
            games = get_library(force_refresh=True)
            self.assertEqual(len(games), 2)
            self.assertEqual(games[0]["name"], "Portal")
            self.assertEqual(games[1]["name"], "Counter-Strike 2")

    def test_get_library_with_access_token(self):
        from unittest.mock import patch, MagicMock
        import json
        from vaporfetch.library import get_library

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "response": {
                "game_count": 1,
                "games": [
                    {"appid": 105600, "name": "Terraria"}
                ]
            }
        }).encode("utf-8")

        # QR session has access_token and steam_id, but NO steam_api_key in settings
        mock_session = {
            "username": "reaper360vr",
            "steam_id": "76561198000000000",
            "access_token": "oauth_token_xyz",
            "auth_method": "qr"
        }
        mock_settings = {}

        with patch("vaporfetch.library.get_current_session", return_value=mock_session), \
             patch("vaporfetch.library.load_settings", return_value=mock_settings), \
             patch("urllib.request.urlopen", return_value=mock_resp), \
             patch("vaporfetch.library.LIBRARY_CACHE_FILE", Path("/tmp/fake_library_cache_qr.json")):
            games = get_library(force_refresh=True)
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0]["appid"], 105600)
            self.assertEqual(games[0]["name"], "Terraria")

    def test_get_library_cache_fallback_on_failed_refresh(self):
        from unittest.mock import patch
        import json
        from vaporfetch.library import get_library

        temp_cache = Path(tempfile.gettempdir()) / "test_vaporfetch_cache_fallback.json"
        try:
            initial_games = [
                {
                    "appid": 730,
                    "name": "Counter-Strike 2",
                    "backup_status": "not_downloaded",
                    "backup_size": "0 B",
                    "backup_size_bytes": 0
                }
            ]
            with open(temp_cache, "w", encoding="utf-8") as f:
                json.dump(initial_games, f)

            mock_session = {"username": "testuser"}
            mock_settings = {}

            with patch("vaporfetch.library.get_current_session", return_value=mock_session), \
                 patch("vaporfetch.library.load_settings", return_value=mock_settings), \
                 patch("vaporfetch.library.fetch_licenses", return_value=set()), \
                 patch("vaporfetch.library.LIBRARY_CACHE_FILE", temp_cache):
                games = get_library(force_refresh=True)
                self.assertEqual(len(games), 1)
                self.assertEqual(games[0]["appid"], 730)
                self.assertEqual(games[0]["name"], "Counter-Strike 2")
        finally:
            if temp_cache.exists():
                temp_cache.unlink()

    def test_get_library_with_status_error(self):
        from unittest.mock import patch
        from vaporfetch.library import get_library_with_status
        from vaporfetch.steamcmd import auth_session

        auth_session.last_error = "Steam session expired. Click 'Re-authenticate with Steam' to sign in."
        mock_session = {"username": "testuser"}

        with patch("vaporfetch.library.get_current_session", return_value=mock_session), \
             patch("vaporfetch.library.load_settings", return_value={}), \
             patch("vaporfetch.library.fetch_licenses", return_value=set()), \
             patch("vaporfetch.library.LIBRARY_CACHE_FILE", Path("/tmp/non_existent_cache_file.json")):
            games, error = get_library_with_status(force_refresh=True)
            self.assertEqual(len(games), 0)
            self.assertIn("expired", error.lower())

        auth_session.reset()

    def test_get_library_qr_login_does_not_invoke_steamcmd_without_credentials(self):
        from unittest.mock import patch
        from pathlib import Path
        from vaporfetch.library import get_library_with_status
        from vaporfetch.steamcmd import auth_session

        auth_session.reset()
        qr_session = {
            "username": "reaper360vr",
            "logged_in": True,
            "steam_id": "76561198000000000",
            "access_token": "mock_token",
            "auth_method": "qr",
        }

        with patch("vaporfetch.library.get_current_session", return_value=qr_session), \
             patch("vaporfetch.library.load_settings", return_value={}), \
             patch("urllib.request.urlopen", side_effect=Exception("Private profile")), \
             patch("vaporfetch.steamcmd.has_steamcmd_cached_credentials", return_value=False), \
             patch("vaporfetch.library.fetch_licenses") as mock_fetch_licenses, \
             patch("vaporfetch.library.LIBRARY_CACHE_FILE", Path("/tmp/non_existent_cache_qr.json")):
            games, error = get_library_with_status(force_refresh=True)
            self.assertEqual(len(games), 0)
            mock_fetch_licenses.assert_not_called()
    def test_resolve_vanity_url(self):
        import json
        from unittest.mock import patch, MagicMock
        from vaporfetch.library import resolve_vanity_url

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "response": {"success": 1, "steamid": "76561199132013751"}
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            sid = resolve_vanity_url("TheRetroGeekYT", "mock_key")
            self.assertEqual(sid, "76561199132013751")

        # Full URL input
        with patch("urllib.request.urlopen", return_value=mock_resp):
            sid2 = resolve_vanity_url("https://steamcommunity.com/id/TheRetroGeekYT/", "mock_key")
            self.assertEqual(sid2, "76561199132013751")

    def test_extract_steam_id_from_jwt_token(self):
        import json, base64
        from vaporfetch.steamcmd import extract_steam_id_from_token

        payload = json.dumps({"sub": "76561199132013751", "iss": "steam"}).encode("utf-8")
        b64 = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64}.signature"

        sid = extract_steam_id_from_token(fake_jwt)
        self.assertEqual(sid, "76561199132013751")

    def test_server_login_endpoints(self):
        try:
            from fastapi.testclient import TestClient
            from vaporfetch.web.server import app
        except ImportError:
            self.skipTest("fastapi not installed in host environment")
            return

        client = TestClient(app)

        # Test login status
        with patch("vaporfetch.web.server.get_current_session", return_value={"logged_in": True, "username": "reaper360vr"}):
            resp = client.get("/api/login/status")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "logged_in")
            self.assertEqual(data["username"], "reaper360vr")

        # Test start login endpoint
        with patch("vaporfetch.web.server.start_login", return_value={"status": "awaiting_2fa", "two_factor_type": "mobile_push", "prompt": "Confirm on phone"}):
            resp = client.post("/api/login", json={"username": "reaper360vr", "password": "dummy"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "awaiting_2fa")
            self.assertEqual(data["two_factor_type"], "mobile_push")

        # Test submit 2fa endpoint
        with patch("vaporfetch.web.server.submit_2fa_code", return_value={"status": "logged_in", "username": "reaper360vr"}):
            resp = client.post("/api/login/2fa", json={"code": "K97XP"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "logged_in")

if __name__ == "__main__":
    unittest.main()

