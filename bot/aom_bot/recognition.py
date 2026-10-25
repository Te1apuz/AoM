"""Artifact constellation recognition from an inventory screenshot.

Ported unchanged (algorithm-wise) from the step 1 spike recognize2.py: find
hexagon icons by colour blobs, classify each by glyph shape + frame hue against
the Runes renders, or against in-game reference crops when they are given.
"""
import pickle
import re
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np

LETTER_FILE = dict(A=4, B=1, C=9, D=5, E=3, F=2, G=10, H=11, I=6, J=7, K=12, L=8)
N = 48  # canonical icon size
ICON, GAP, LABEL = 120, 16, 40  # strip_png layout


def icon_parts(bgr, mask):
    """bgr+mask of one icon (any size) -> (glyph mask NxN, frame hue vector, dark glyph mask)."""
    x, y, w, h = cv2.boundingRect(mask)
    bgr, mask = bgr[y:y + h, x:x + w], mask[y:y + h, x:x + w]
    bgr = cv2.resize(bgr, (N, N), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask, (N, N), interpolation=cv2.INTER_NEAREST)
    inner = cv2.erode(mask, np.ones((15, 15), np.uint8))  # drop bevel/edge ring (dim icons have a light rim)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    s, v = hsv[..., 1], hsv[..., 2]
    white = v * (1 - s / 255.0)  # high for white/grey glyph, low for saturated frame
    vals = white[inner > 0].astype(np.uint8).reshape(-1, 1)
    thr, _ = cv2.threshold(vals, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    glyph = ((white > thr) & (inner > 0)).astype(np.uint8)
    # inactive (dim) icons draw a DARK glyph on a lighter frame
    vv = v[inner > 0].astype(np.uint8).reshape(-1, 1)
    vthr, _ = cv2.threshold(vv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = ((v < vthr) & (inner > 0)).astype(np.uint8)
    frame = (inner > 0) & (glyph == 0)
    hue = hsv[..., 0][frame] * np.pi / 90.0  # 0..180 -> 0..2pi
    hv = np.array([np.cos(hue).mean(), np.sin(hue).mean()])
    return glyph, hv / (np.linalg.norm(hv) + 1e-6), dark


def segments(profile, thr, min_w, max_w):
    on = profile > thr
    raw, start = [], None
    for i, o in enumerate(list(on) + [False]):
        if o and start is None:
            start = i
        if not o and start is not None:
            raw.append([start, i])
            start = None
    # dim icons split on their darker glyph: glue pieces across small gaps
    merged = []
    for s in raw:
        if merged and s[0] - merged[-1][1] <= max(3, min_w // 3) and s[1] - merged[-1][0] <= max_w:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [tuple(s) for s in merged if min_w <= s[1] - s[0] <= max_w]


class Recognizer:
    def __init__(self, runes_dir: Path, ingame_refs: Path | None = None):
        self.runes_dir = Path(runes_dir)
        self.hex = None  # hexagon mask, taken from the first reference icon
        self.refs = self._load_refs()
        # letter -> [(glyph, hue)] in-game crops; when present they replace the Runes render
        self.ingame = {}
        if ingame_refs is not None:
            with open(ingame_refs, "rb") as f:
                self.ingame = pickle.load(f)

    def letters(self, image_path: Path) -> tuple[str, str, str, str] | None:
        """The artifact's 4 letters left to right, or None when no icon row is found."""
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        h_img, w_img = img.shape[:2]
        # the brightness-profile path can place a slot past the image edge (tightly cropped screenshots)
        rows = [row for row in self._find_rows(img)
                if all(x >= 0 and y >= 0 and x + w <= w_img and y + h <= h_img for x, y, w, h in row)]
        if not rows:
            return None
        # pick the row whose 4 slots look most like constellation glyphs (tiles/portraits score low)
        best = None
        for row in rows[:40]:
            cand = [self._classify(img, b) for b in row]
            total = sum(c[1] for c in cand)
            if best is None or total > best[0]:
                best = (total, cand)
        letters = "".join(c[0] for c in best[1])
        return tuple(letters) if re.fullmatch(r"[A-L]{4}", letters) else None

    def strip_png(self, letters: Sequence[str]) -> bytes:
        """The 4 constellations as Runes icons, left to right, letter under each."""
        w = len(letters) * ICON + (len(letters) + 1) * GAP
        canvas = np.zeros((ICON + LABEL + 2 * GAP, w, 3), np.uint8)  # black, same as the Runes icon background
        for i, letter in enumerate(letters):
            icon = cv2.imread(str(self.runes_dir / f"Rune{LETTER_FILE[letter]}_200.jpg"))
            x = GAP + i * (ICON + GAP)
            canvas[GAP:GAP + ICON, x:x + ICON] = cv2.resize(icon, (ICON, ICON), interpolation=cv2.INTER_AREA)
            (tw, _), _ = cv2.getTextSize(letter, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
            cv2.putText(canvas, letter, (x + (ICON - tw) // 2, GAP + ICON + LABEL - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (240, 240, 240), 3, cv2.LINE_AA)
        return cv2.imencode(".png", canvas)[1].tobytes()

    def _load_refs(self):
        refs = {}
        for letter, n in LETTER_FILE.items():
            im = cv2.imread(str(self.runes_dir / f"Rune{n}_200.jpg"))
            if im is None:
                raise FileNotFoundError(self.runes_dir / f"Rune{n}_200.jpg")
            g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
            _, m = cv2.threshold(g, 30, 255, cv2.THRESH_BINARY)
            cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
            mask = np.zeros_like(g)
            cv2.fillPoly(mask, [hull], 255)
            # refs have a soft glow; shrink to the hexagon body
            mask = cv2.erode(mask, np.ones((15, 15), np.uint8))
            refs[letter] = icon_parts(im, mask)
            if self.hex is None:
                bx, by, bw, bh = cv2.boundingRect(mask)
                self.hex = mask[by:by + bh, bx:bx + bw]
        return refs

    def _strong_blobs(self, img):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = ((hsv[..., 1] > 70) & (hsv[..., 2] > 90)).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))  # 5x5 glued neighbouring ~22px icons
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if 14 <= w <= 130 and 14 <= h <= 130 and 0.6 <= w / h <= 1.1:
                hull = cv2.convexHull(c)
                # must look like the reference hexagon (rejects square artifact tiles, portraits)
                blob = np.zeros((h, w), np.uint8)
                cv2.fillPoly(blob, [hull - [x, y]], 1)
                hexm = (cv2.resize(self.hex, (w, h), interpolation=cv2.INTER_NEAREST) > 0).astype(np.uint8)
                iou = (blob & hexm).sum() / max((blob | hexm).sum(), 1)
                if iou > 0.75:
                    out.append((x, y, w, h))
        return out

    def _find_rows(self, img):
        """Rows of 4 icons: seed from bright blobs, then split the row band by a column brightness profile."""
        v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32)
        rows = []
        blobs = self._strong_blobs(img)
        # 1) four bright blobs already in an even row: take them as is (profile can't split ~3px gaps)
        for a in blobs:
            line = sorted((b for b in blobs
                           if abs(b[3] - a[3]) <= a[3] * 0.15 and abs(b[1] - a[1]) <= a[3] * 0.2 and b[0] >= a[0]),
                          key=lambda b: b[0])[:4]
            if len(line) == 4:
                gaps = np.diff([b[0] for b in line])
                if gaps.min() > 0 and gaps.max() <= gaps.min() * 1.25 and gaps.max() <= a[2] * 1.9:
                    rows.append(tuple(line))
        # 2) otherwise seed from one bright blob and split the band by brightness profile (finds dim icons)
        for (x, y, w, h) in blobs:
            band = v[y + h // 4: y + 3 * h // 4]  # middle half of the icon height
            prof = band.mean(0)
            lo = np.percentile(prof[max(0, x - 6 * w): x + 7 * w], 10)
            segs = segments(prof, lo + 12, int(w * 0.6), int(w * 1.35))
            segs = [s for s in segs if abs((s[0] + s[1]) / 2 - (x + w / 2)) <= 6 * w]
            for i in range(len(segs) - 3):
                four = segs[i:i + 4]
                if not any(a <= x + w / 2 <= b for a, b in four):
                    continue
                c = [(a + b) / 2 for a, b in four]
                gaps = np.diff(c)
                if gaps.min() > 0 and gaps.max() <= gaps.min() * 1.25 and gaps.max() <= w * 1.8:
                    rows.append(tuple((int(round(cx - w / 2)), y, w, h) for cx in c))
        rows = list(dict.fromkeys(rows))
        return sorted(rows, key=lambda r: -r[0][3])

    def _slot_mask(self, img, box):
        x, y, w, h = box
        m = np.zeros(img.shape[:2], np.uint8)
        m[y:y + h, x:x + w] = cv2.resize(self.hex, (w, h), interpolation=cv2.INTER_NEAREST)
        return m

    def _classify(self, img, box, w_hue=0.35):
        """-> (letter, best score)"""
        glyph, hv, dark = icon_parts(img, self._slot_mask(img, box))
        scores = {}
        for letter, (rg, rh, _) in self.refs.items():
            cands = self.ingame.get(letter) or [(rg, rh)]
            scores[letter] = -9
            for cg, ch in cands:
                best = 0
                for gm in (glyph, dark):  # bright glyph, or dark glyph of an inactive icon
                    for dy in (-2, -1, 0, 1, 2):
                        for dx in (-2, -1, 0, 1, 2):
                            g = np.roll(np.roll(gm, dy, 0), dx, 1)
                            inter = (g & cg).sum()
                            union = (g | cg).sum()
                            best = max(best, inter / max(union, 1))
                s = best + w_hue * float(ch @ hv)  # hue term: 1 same hue, -1 opposite
                scores[letter] = max(scores[letter], s)
        letter, top = max(scores.items(), key=lambda kv: kv[1])
        return letter, top
