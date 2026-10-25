import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

from aom_bot.source import HeroSource, SourceUnavailable
from tests.xlsx_helper import make_xlsx

SNAPSHOT = (Path(__file__).parent / "data" / "heroes-2026-10-25.xlsx").read_bytes()
T0 = datetime(2026, 10, 25, 12, 0)


class FakeFetch:
    """Returns/raises the queued responses in order; the last one repeats."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self) -> bytes:
        self.calls += 1
        r = self.responses[min(self.calls, len(self.responses)) - 1]
        if isinstance(r, Exception):
            raise r
        return r


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


class HeroSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "heroes.xlsx"
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, fetch):
        return HeroSource(self.cache, fetch=fetch, clock=self.clock)

    def test_fresh_fetch_writes_cache(self):
        snap = self.source(FakeFetch(SNAPSHOT)).get()
        self.assertEqual(len(snap.heroes), 209)
        self.assertFalse(snap.stale)
        self.assertEqual(snap.loaded_at, T0)
        self.assertEqual(self.cache.read_bytes(), SNAPSHOT)

    def test_within_max_age_no_refetch(self):
        fetch = FakeFetch(SNAPSHOT)
        src = self.source(fetch)
        src.get()
        self.clock.now = T0 + timedelta(hours=1)
        src.get()
        self.assertEqual(fetch.calls, 1)

    def test_html_instead_of_xlsx_serves_cache(self):  # Review Focus №4
        src = self.source(FakeFetch(SNAPSHOT, b"<html>Sign in</html>"))
        src.get()
        self.clock.now = T0 + timedelta(hours=7)
        snap = src.get()
        self.assertTrue(snap.stale)
        self.assertEqual(len(snap.heroes), 209)
        self.assertEqual(snap.loaded_at, T0)

    def test_network_error_after_restart_uses_disk_cache(self):
        self.cache.write_bytes(SNAPSHOT)
        os.utime(self.cache, (T0.timestamp(), T0.timestamp()))
        self.clock.now = T0 + timedelta(days=1)
        snap = self.source(FakeFetch(urllib.error.URLError("offline"))).get()
        self.assertTrue(snap.stale)
        self.assertEqual(len(snap.heroes), 209)
        self.assertEqual(snap.loaded_at, T0)

    def test_no_cache_no_network_raises(self):
        with self.assertRaises(SourceUnavailable):
            self.source(FakeFetch(urllib.error.URLError("offline"))).get()

    def test_retry_after_limits_attempts(self):
        fetch = FakeFetch(SNAPSHOT, urllib.error.URLError("offline"))
        src = self.source(fetch)
        src.get()
        self.clock.now = T0 + timedelta(hours=7)
        src.get()  # 2nd call fails
        self.clock.now += timedelta(minutes=5)
        src.get()
        self.assertEqual(fetch.calls, 2)
        self.clock.now += timedelta(minutes=6)
        src.get()
        self.assertEqual(fetch.calls, 3)

    def test_refresh_forces_fetch(self):
        fetch = FakeFetch(SNAPSHOT)
        src = self.source(fetch)
        src.get()
        self.clock.now = T0 + timedelta(minutes=1)
        snap = src.refresh()
        self.assertEqual(fetch.calls, 2)
        self.assertEqual(snap.loaded_at, T0 + timedelta(minutes=1))

    def test_zero_heroes_is_failure(self):
        src = self.source(FakeFetch(SNAPSHOT, make_xlsx({})))
        src.get()
        self.clock.now = T0 + timedelta(hours=7)
        snap = src.get()
        self.assertTrue(snap.stale)
        self.assertEqual(len(snap.heroes), 209)


if __name__ == "__main__":
    unittest.main()
