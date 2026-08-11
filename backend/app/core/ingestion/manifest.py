from __future__ import annotations
import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent.parent.parent.parent / ".ingested_manifest.json"


class Manifest:
    def __init__(self):
        self._path = MANIFEST_PATH
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:
                return {}
        return {}

    def _save(self):
        self._path.write_text(json.dumps(self._data, indent=2))

    def list_ingested(self) -> set[str]:
        return set(self._data.keys())

    def get_meta(self, key: str) -> dict | None:
        return self._data.get(key)

    def mark_ingested(self, key: str, size: int, etag: str):
        self._data[key] = {"size": size, "etag": etag}
        self._save()

    def mark_ingested_batch(self, entries: list[dict]):
        """entries: list of {key, size, etag}"""
        for e in entries:
            self._data[e["key"]] = {"size": e["size"], "etag": e["etag"]}
        self._save()

    def remove(self, key: str):
        self._data.pop(key, None)
        self._save()

    def count(self) -> int:
        return len(self._data)
