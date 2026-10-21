# v1rg0_persistence.py
# Tiny JSON-file persistence for memory, DLQ and proposals.
# Data dir: V1RG0_DATA_DIR (default /workspace/V1rG0_data). Writes are atomic (tmp + rename).
import json
import os
import time

DEFAULT_DATA_DIR = "/workspace/V1rG0_data"


def data_dir() -> str:
    path = os.environ.get("V1RG0_DATA_DIR", DEFAULT_DATA_DIR)
    os.makedirs(path, exist_ok=True)
    return path


class JsonListFile:
    """A JSON array on disk. load() at startup, append()/save() after each change."""

    def __init__(self, name: str, max_items: int = 1000):
        self.path = os.path.join(data_dir(), name)
        self.max_items = max_items
        self.items = self.load()

    def load(self) -> list:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            self._set_aside("unreadable")
            return []
        if not isinstance(data, list):
            self._set_aside("not a JSON list")
            return []
        return data

    def _set_aside(self, reason: str) -> None:
        """Keep a bad file for inspection; timestamped so copies never overwrite each other."""
        stamp = time.strftime("%Y%m%dT%H%M%S") + f"_{time.time_ns() % 1_000_000_000:09d}"
        dest = f"{self.path}.corrupt.{stamp}"
        try:
            os.replace(self.path, dest)
            print(f"[PERSISTENCE] {self.path} {reason}; moved to {dest}")
        except OSError as e:
            raise RuntimeError(f"{self.path} is {reason} and could not be set aside: {e}")

    def append(self, item) -> None:
        self.items.append(item)
        self.items = self.items[-self.max_items:]
        self.save()

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, default=str, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
