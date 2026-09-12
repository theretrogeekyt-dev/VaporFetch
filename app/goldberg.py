import os
import shutil
import zipfile
import io
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.config import DATA_DIR, BASE_DIR

# Directory where Goldberg binaries are stored
GOLDBERG_ASSETS_DIR = Path(os.getenv("GOLDBERG_PATH", str(DATA_DIR / "goldberg")))
GOLDBERG_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Release URL fallback list for Goldberg Steam Emulator
GOLDBERG_RELEASE_URLS = [
    "https://github.com/Detanup01/gbe_fork/releases/latest/download/goldberg_emulator.zip",
    "https://gitlab.com/Mr_Goldberg/goldberg_emulator/-/jobs/artifacts/master/raw/goldberg_emulator.zip?job=build",
]

class GoldbergManager:
    def __init__(self):
        self.dir = GOLDBERG_ASSETS_DIR

    @property
    def dll32_path(self) -> Path:
        return self.dir / "steam_api.dll"

    @property
    def dll64_path(self) -> Path:
        return self.dir / "steam_api64.dll"

    def is_available(self) -> bool:
        """Returns True if the required Goldberg emulator DLLs are ready on disk."""
        return self.dll32_path.exists() and self.dll64_path.exists()

    async def ensure_binaries(self) -> bool:
        """Ensures Goldberg DLLs exist; downloads from mirror if missing."""
        if self.is_available():
            return True

        # Check if they exist in pre-bundled container asset folder /app/assets/goldberg
        bundled = BASE_DIR / "assets" / "goldberg"
        if (bundled / "steam_api.dll").exists() and (bundled / "steam_api64.dll").exists():
            shutil.copy2(bundled / "steam_api.dll", self.dll32_path)
            shutil.copy2(bundled / "steam_api64.dll", self.dll64_path)
            return True

        # Attempt download from mirrors using standard library urllib
        for url in GOLDBERG_RELEASE_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "VaporFetch/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read()
                    with zipfile.ZipFile(io.BytesIO(content)) as zf:
                        for member in zf.namelist():
                            norm = member.lower().replace("\\", "/")
                            if norm.endswith("steam_api.dll") and not norm.endswith("steam_api64.dll"):
                                with zf.open(member) as src, open(self.dll32_path, "wb") as dst:
                                    shutil.copyfileobj(src, dst)
                            elif norm.endswith("steam_api64.dll"):
                                with zf.open(member) as src, open(self.dll64_path, "wb") as dst:
                                    shutil.copyfileobj(src, dst)
                    if self.is_available():
                        return True
            except Exception as e:
                print(f"[Goldberg] Mirror download failed ({url}): {e}")

        return self.is_available()

    def check_status(self, game_path: Path) -> Dict[str, Any]:
        """
        Scans a game directory to see if it has steam_api DLLs and if they are patched with Goldberg.
        """
        if not game_path.exists():
            return {"compatible": False, "patched": False, "dll_count": 0}

        steam_dlls = []
        is_patched = False

        for root, dirs, files in os.walk(game_path):
            for f in files:
                f_lower = f.lower()
                if f_lower in ("steam_api.dll", "steam_api64.dll"):
                    full_path = Path(root) / f
                    orig_path = Path(root) / f"{f}.orig"
                    steam_dlls.append(str(full_path))
                    if orig_path.exists():
                        is_patched = True

        return {
            "compatible": len(steam_dlls) > 0,
            "patched": is_patched,
            "dll_count": len(steam_dlls),
            "dll_paths": steam_dlls,
            "emulator_ready": self.is_available()
        }

    def apply(self, game_path: Path, appid: int, account_name: str = "Player") -> Dict[str, Any]:
        """
        Applies Goldberg emulator to all steam_api DLLs found in the game directory.
        Backs up original DLLs to .orig and writes steam_appid.txt.
        """
        if not self.is_available():
            raise FileNotFoundError("Goldberg emulator DLLs not found. Please ensure they are downloaded.")

        if not game_path.exists():
            raise FileNotFoundError(f"Game directory not found: {game_path}")

        patched_list = []

        for root, dirs, files in os.walk(game_path):
            for f in files:
                f_lower = f.lower()
                if f_lower in ("steam_api.dll", "steam_api64.dll"):
                    target_dll = Path(root) / f
                    orig_dll = Path(root) / f"{f}.orig"

                    # 1. Back up original if not already backed up
                    if not orig_dll.exists():
                        shutil.copy2(target_dll, orig_dll)

                    # 2. Overwrite with matching Goldberg DLL
                    source_emulator = self.dll64_path if f_lower == "steam_api64.dll" else self.dll32_path
                    shutil.copy2(source_emulator, target_dll)
                    patched_list.append(str(target_dll))

                    # 3. Create steam_appid.txt next to the DLL
                    appid_file = Path(root) / "steam_appid.txt"
                    appid_file.write_text(str(appid), encoding="utf-8")

                    # 4. Create steam_settings folder with account name
                    settings_dir = Path(root) / "steam_settings"
                    settings_dir.mkdir(parents=True, exist_ok=True)
                    (settings_dir / "steam_appid.txt").write_text(str(appid), encoding="utf-8")
                    if account_name:
                        (settings_dir / "force_account_name.txt").write_text(account_name, encoding="utf-8")

        return {
            "success": True,
            "patched_count": len(patched_list),
            "patched_files": patched_list,
            "appid": appid
        }

    def revert(self, game_path: Path) -> Dict[str, Any]:
        """
        Reverts any Goldberg-patched DLLs in the game folder back to authentic .orig copies.
        """
        if not game_path.exists():
            raise FileNotFoundError(f"Game directory not found: {game_path}")

        restored_list = []

        for root, dirs, files in os.walk(game_path):
            for f in files:
                f_lower = f.lower()
                if f_lower in ("steam_api.dll.orig", "steam_api64.dll.orig"):
                    orig_file = Path(root) / f
                    target_name = f[:-5]  # strip '.orig'
                    target_file = Path(root) / target_name

                    # Restore original
                    shutil.move(orig_file, target_file)
                    restored_list.append(str(target_file))

                    # Remove generated steam_appid.txt and steam_settings if present
                    appid_file = Path(root) / "steam_appid.txt"
                    if appid_file.exists():
                        appid_file.unlink(missing_ok=True)

                    settings_dir = Path(root) / "steam_settings"
                    if settings_dir.exists():
                        shutil.rmtree(settings_dir, ignore_errors=True)

        return {
            "success": True,
            "restored_count": len(restored_list),
            "restored_files": restored_list
        }


goldberg_manager = GoldbergManager()
