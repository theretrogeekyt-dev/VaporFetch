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

if __name__ == "__main__":
    unittest.main()

