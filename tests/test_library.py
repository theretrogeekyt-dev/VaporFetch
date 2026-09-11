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
        # Unknown offline game fallback
        self.assertEqual(resolver.resolve_name(99999999), "Steam App 99999999")

    def test_populate_and_cache_games(self):
        from vaporfetch.library import populate_and_cache_games
        games = populate_and_cache_games({730, 400})
        self.assertEqual(len(games), 2)
        appids = [g["appid"] for g in games]
        self.assertIn(730, appids)
        self.assertIn(400, appids)
        names = [g["name"] for g in games]
        self.assertIn("Counter-Strike 2", names)
        self.assertIn("Portal", names)

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

if __name__ == "__main__":
    unittest.main()
