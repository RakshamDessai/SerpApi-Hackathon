"""Hash-keyed disk cache for SerpApi responses (Feature 14).

Three jobs:

* **Credit preservation.** Re-running the same syllabus during development, or a
  judge clicking twice, must not spend a second credit.
* **Offline development.** Once fixtures are recorded, the whole pipeline is
  developed and tested with no network and no key.
* **Demo mode.** With `demo_mode=True` the cache is read-only with no expiry: a
  miss returns `None` rather than falling through to a paid call, so a stage
  demo provably cannot spend credits.

The key deliberately excludes `api_key` so a cache stays valid across keys.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

IGNORED_PARAMS = {"api_key", "output", "no_cache"}


def cache_key(engine: str, params: dict) -> str:
    """Stable hash of an outbound request.

    `sort_keys=True` matters: an unsorted dump produces a different digest for
    the same logical request and silently halves the hit rate.
    """
    payload = {k: v for k, v in params.items() if k not in IGNORED_PARAMS}
    payload["engine"] = engine
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


@dataclass
class ResponseCache:
    directory: Path
    ttl_hours: int = 72
    read_only: bool = False      # demo mode
    ignore_ttl: bool = False     # demo mode: fixtures never expire

    def __post_init__(self) -> None:
        if not self.read_only:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, engine: str, params: dict) -> dict | None:
        path = self._path(cache_key(engine, params))
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("unreadable cache entry %s: %s", path.name, exc)
            return None

        if not self.ignore_ttl:
            age_hours = (time.time() - record.get("fetched_at", 0)) / 3600
            if age_hours > self.ttl_hours:
                return None
        return record.get("response")

    def put(self, engine: str, params: dict, response: dict) -> None:
        if self.read_only:
            return
        path = self._path(cache_key(engine, params))
        record = {
            "fetched_at": time.time(),
            "engine": engine,
            "params": {k: v for k, v in params.items() if k not in IGNORED_PARAMS},
            "response": response,
        }
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
            tmp.replace(path)                 # atomic: never leave a half-written entry
        except OSError as exc:
            log.warning("could not write cache entry %s: %s", path.name, exc)

    def stats(self) -> tuple[int, int]:
        """(entry count, total bytes)."""
        if not self.directory.exists():
            return 0, 0
        files = list(self.directory.glob("*.json"))
        return len(files), sum(f.stat().st_size for f in files)


def build(settings) -> ResponseCache:
    """Construct the right cache for the run.

    Demo mode points at the committed fixture set and refuses to write, so the
    demo is reproducible and provably costs nothing.
    """
    from s2s.config import FIXTURE_DIR

    if settings.demo_mode:
        return ResponseCache(
            directory=FIXTURE_DIR / "serpapi",
            read_only=True,
            ignore_ttl=True,
        )
    return ResponseCache(directory=settings.cache_dir, ttl_hours=settings.cache_ttl_hours)
