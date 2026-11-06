"""Helpers for writing application state without truncating the previous copy."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def write_json(path: Path, data) -> None:
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
        suffix=".tmp", delete=False,
    ) as temp:
        temp_path = Path(temp.name)
        try:
            json.dump(data, temp, indent=2)
            temp.flush()
            os.fsync(temp.fileno())
            temp.close()
            temp_path.replace(path)
        finally:
            temp.close()
            temp_path.unlink(missing_ok=True)
