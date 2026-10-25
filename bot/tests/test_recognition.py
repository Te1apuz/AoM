import tempfile
import unittest
from collections import Counter
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:  # core tests run with the system python, without OpenCV
    cv2 = None

TESTS = Path(__file__).parent
REPO = TESTS.parent.parent
SCREENS = TESTS / "data" / "screens"
REFS = TESTS.parent / "aom_bot" / "data" / "ingame_refs.pkl"

# ground truth from the recognition spike (multiset: icon order is not checked)
TRUTH = {
    "photo_2026-10-25_10-16-41.jpg": "HLJK",
    "photo_2026-10-25_10-16-41 (2).jpg": "BDDH",
    "photo_2026-10-25_10-16-42.jpg": "KLDB",
}


@unittest.skipUnless(cv2, "OpenCV not installed (use bot/.venv)")
class RecognizerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aom_bot.recognition import Recognizer
        cls.rec = Recognizer(REPO / "Runes", REFS)

    def test_known_screens(self):
        for name, want in TRUTH.items():
            with self.subTest(name):
                got = self.rec.letters(SCREENS / name)
                self.assertIsNotNone(got)
                self.assertEqual(len(got), 4)
                self.assertEqual(Counter(got), Counter(want))

    def test_no_icons(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "black.png"
            cv2.imwrite(str(p), np.zeros((600, 1200, 3), np.uint8))
            self.assertIsNone(self.rec.letters(p))

    def test_tight_crop_does_not_crash(self):  # icon boxes may run past the image edge
        img = cv2.imread(str(SCREENS / "photo_2026-10-25_10-16-42.jpg"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tight.png"
            cv2.imwrite(str(p), img[577:626, 418:587])  # exactly the icon row, no padding
            got = self.rec.letters(p)
        self.assertTrue(got is None or Counter(got) == Counter("KLDB"), got)

    def test_strip_png(self):
        self.assertTrue(self.rec.strip_png("LGEB").startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
