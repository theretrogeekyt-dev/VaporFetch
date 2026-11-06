import os
import asyncio
import json
import shutil
import zipfile
import io
import urllib.request
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, Any, List, Optional

from app.config import DATA_DIR, BASE_DIR
from app.storage import write_json

# Directory where Goldberg binaries are stored
GOLDBERG_ASSETS_DIR = Path(os.getenv("GOLDBERG_PATH", str(DATA_DIR / "goldberg")))
GOLDBERG_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Release URL fallback list for Goldberg Steam Emulator
GOLDBERG_RELEASE_URLS = [
    "https://gitlab.com/Mr_Goldberg/goldberg_emulator/-/jobs/4247811310/artifacts/download",
]

CONFIG_MARKER = ".vaporfetch-goldberg.json"
CONFIG_FILES = (
    "steam_appid.txt",
    "steam_settings/steam_appid.txt",
    "steam_settings/force_account_name.txt",
)


def copy_dll(source: Path, target: Path):
    with NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as temp:
        path = Path(temp.name)
    try:
        shutil.copy2(source, path)
        path.replace(target)
    finally:
        path.unlink(missing_ok=True)


def write_emulator_config(directory: Path, appid: int, account_name: str):
    marker = directory / CONFIG_MARKER
    if marker.exists() or marker.is_symlink():
        return
    contents = (str(appid), str(appid), account_name)
    created = {}
    for name, value in zip(CONFIG_FILES, contents):
        path = directory / name
        if value and not path.parent.is_symlink() and not path.exists() and not path.is_symlink():
            created[name] = value
    if created:
        write_json(marker, created)
        for name, value in created.items():
            path = directory / name
            path.parent.mkdir(exist_ok=True)
            with path.open("x", encoding="utf-8") as config:
                config.write(value)


def remove_emulator_config(directory: Path):
    marker = directory / CONFIG_MARKER
    if marker.is_symlink() or not marker.is_file():
        return
    created = json.loads(marker.read_text(encoding="utf-8"))
    for name in CONFIG_FILES:
        path = directory / name
        if name in created and not path.is_symlink() and not path.parent.is_symlink() and path.is_file():
            if path.read_text(encoding="utf-8", errors="replace") == created[name]:
                path.unlink()
    marker.unlink()


class GoldbergManager:
    def __init__(self):
        self.dir = GOLDBERG_ASSETS_DIR
        self.bundled_candidates = [
            BASE_DIR / "app" / "assets" / "goldberg",
            BASE_DIR / "assets" / "goldberg",
            Path("/app/app/assets/goldberg"),
            Path("/app/assets/goldberg"),
        ]

    @property
    def dll32_path(self) -> Path:
        target = self.dir / "steam_api.dll"
        if target.exists():
            return target
        for candidate in self.bundled_candidates:
            c = candidate / "steam_api.dll"
            if c.exists():
                return c
        return target

    @property
    def dll64_path(self) -> Path:
        target = self.dir / "steam_api64.dll"
        if target.exists():
            return target
        for candidate in self.bundled_candidates:
            c = candidate / "steam_api64.dll"
            if c.exists():
                return c
        return target

    def is_available(self) -> bool:
        """Returns True if the required Goldberg emulator DLLs are ready on disk."""
        return self.dll32_path.exists() and self.dll64_path.exists()

    async def ensure_binaries(self) -> bool:
        """Ensures Goldberg DLLs exist; checks bundled paths and downloads from mirror if missing."""
        if self.is_available():
            return True
        return await asyncio.to_thread(self._download_binaries)

    def _download_binaries(self) -> bool:
        # 1. If already available in bundled candidate or self.dir, sync to self.dir for persistence
        if self.is_available():
            try:
                if not (self.dir / "steam_api.dll").exists() and self.dll32_path.exists():
                    shutil.copy2(self.dll32_path, self.dir / "steam_api.dll")
                if not (self.dir / "steam_api64.dll").exists() and self.dll64_path.exists():
                    shutil.copy2(self.dll64_path, self.dir / "steam_api64.dll")
            except Exception as e:
                print(f"[Goldberg] Warning syncing binaries to data directory: {e}")
            return True

        # 2. Check bundled candidates explicitly
        for candidate in self.bundled_candidates:
            c32 = candidate / "steam_api.dll"
            c64 = candidate / "steam_api64.dll"
            if c32.exists() and c64.exists():
                try:
                    shutil.copy2(c32, self.dir / "steam_api.dll")
                    shutil.copy2(c64, self.dir / "steam_api64.dll")
                    return True
                except Exception as e:
                    print(f"[Goldberg] Error copying bundled binaries: {e}")

        # 3. Attempt dynamic URL scrape from GitLab pages
        urls_to_try = list(GOLDBERG_RELEASE_URLS)
        try:
            req = urllib.request.Request("https://mr_goldberg.gitlab.io/goldberg_emulator/", headers={"User-Agent": "VaporFetch/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                page_text = resp.read().decode("utf-8", errors="ignore")
                import re
                match = re.search(r'href="([^"]*artifacts/download)"', page_text)
                if match:
                    dyn_url = match.group(1)
                    if dyn_url not in urls_to_try:
                        urls_to_try.insert(0, dyn_url)
        except Exception as pe:
            print(f"[Goldberg] GitLab Pages scrape warning: {pe}")

        # 4. Attempt download from mirrors
        for url in urls_to_try:
            try:
                print(f"[Goldberg] Downloading emulator binaries from {url}...")
                req = urllib.request.Request(url, headers={"User-Agent": "VaporFetch/1.0"})
                with urllib.request.urlopen(req, timeout=45) as resp:
                    content = resp.read()
                    with zipfile.ZipFile(io.BytesIO(content)) as zf:
                        for member in zf.namelist():
                            norm = member.lower().replace("\\", "/")
                            # Match steam_api.dll (exclude steam_api64.dll)
                            if norm.endswith("steam_api.dll") and not norm.endswith("steam_api64.dll"):
                                with zf.open(member) as src, open(self.dir / "steam_api.dll", "wb") as dst:
                                    shutil.copyfileobj(src, dst)
                            # Match steam_api64.dll
                            elif norm.endswith("steam_api64.dll"):
                                with zf.open(member) as src, open(self.dir / "steam_api64.dll", "wb") as dst:
                                    shutil.copyfileobj(src, dst)
                    if self.is_available():
                        print(f"[Goldberg] Emulator binaries successfully installed into {self.dir}")
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
                    if full_path.is_symlink() or orig_path.is_symlink():
                        continue
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
            raise FileNotFoundError(
                "Goldberg emulator DLLs (steam_api.dll / steam_api64.dll) are missing. "
                "Please place them into your mounted NAS data folder under 'goldberg/' or ensure internet connectivity."
            )

        if not game_path.exists():
            raise FileNotFoundError(f"Game directory not found: {game_path}")

        patched_list = []

        for root, dirs, files in os.walk(game_path):
            for f in files:
                f_lower = f.lower()
                if f_lower in ("steam_api.dll", "steam_api64.dll"):
                    target_dll = Path(root) / f
                    orig_dll = Path(root) / f"{f}.orig"
                    if target_dll.is_symlink() or orig_dll.is_symlink():
                        continue

                    # 1. Back up original if not already backed up
                    if not orig_dll.exists():
                        copy_dll(target_dll, orig_dll)

                    # 2. Overwrite with matching Goldberg DLL
                    source_emulator = self.dll64_path if f_lower == "steam_api64.dll" else self.dll32_path
                    copy_dll(source_emulator, target_dll)
                    patched_list.append(str(target_dll))

                    write_emulator_config(Path(root), appid, account_name)

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
                    if orig_file.is_symlink() or target_file.is_symlink():
                        continue

                    # Restore original
                    orig_file.replace(target_file)
                    restored_list.append(str(target_file))

                    remove_emulator_config(Path(root))

        return {
            "success": True,
            "restored_count": len(restored_list),
            "restored_files": restored_list
        }


goldberg_manager = GoldbergManager()
