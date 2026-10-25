"""The live RedCat sheet, cached in memory and on disk."""
import logging
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from .heroes import Hero, SheetError, parse_heroes

EXPORT_URL = "https://docs.google.com/spreadsheets/d/18IWMCIs8q2usE4HzB9enjbVJ6C1YLw50/export?format=xlsx"

log = logging.getLogger(__name__)


class SourceUnavailable(Exception):
    """No hero data at all: the sheet failed to load and nothing is cached."""


@dataclass(frozen=True)
class Snapshot:
    heroes: list[Hero]
    loaded_at: datetime
    stale: bool


def fetch_export(url: str = EXPORT_URL, timeout: float = 30) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


class HeroSource:
    def __init__(self, cache_path: Path, fetch: Callable[[], bytes] = fetch_export,
                 clock: Callable[[], datetime] = datetime.now,
                 max_age: timedelta = timedelta(hours=6), retry_after: timedelta = timedelta(minutes=10)):
        self.cache_path = Path(cache_path)
        self.fetch = fetch
        self.clock = clock
        self.max_age = max_age
        self.retry_after = retry_after
        self._snap: Snapshot | None = None
        self._next_attempt: datetime | None = None

    def get(self) -> Snapshot:
        now = self.clock()
        if self._snap and not self._snap.stale and now - self._snap.loaded_at < self.max_age:
            return self._snap
        if self._snap and self._next_attempt and now < self._next_attempt:
            return self._snap
        return self._load(now)

    def refresh(self) -> Snapshot:
        return self._load(self.clock())

    def _load(self, now: datetime) -> Snapshot:
        try:
            data = self.fetch()
            heroes, warnings = parse_heroes(data)
            if not heroes:
                raise SheetError("в таблице нет героев")
        except Exception as e:  # network, HTTP, HTML instead of xlsx, broken sheet
            log.warning("не удалось обновить таблицу героев: %s", e)
            self._next_attempt = now + self.retry_after
            if self._snap is None:
                self._snap = self._from_disk()
            if self._snap is None:
                raise SourceUnavailable(str(e)) from e
            self._snap = replace(self._snap, stale=True)
            return self._snap
        for w in warnings:
            log.warning("таблица героев: %s", w)
        self._write_cache(data)
        self._next_attempt = None
        self._snap = Snapshot(heroes, now, False)
        return self._snap

    def _write_cache(self, data: bytes) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_name(self.cache_path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, self.cache_path)

    def _from_disk(self) -> Snapshot | None:
        if not self.cache_path.exists():
            return None
        try:
            heroes, _ = parse_heroes(self.cache_path.read_bytes())
        except SheetError as e:
            log.warning("кэш таблицы героев не читается: %s", e)
            return None
        if not heroes:
            return None
        return Snapshot(heroes, datetime.fromtimestamp(self.cache_path.stat().st_mtime), True)
