"""Picks heroes for an artifact: by constellation match and for a reforge."""
import random
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .heroes import VALID_LETTERS, Hero

TIERS = (4, 3, 2)
SHOWN_PER_TIER = 3
REFORGE_COUNT = 5

# Cyrillic look-alikes a player may type instead of Latin letters
CYRILLIC_TO_LATIN = str.maketrans("АВСЕНК", "ABCEHK")


class ArtType(Enum):
    MASS = "mass"
    SINGLE = "single"
    MULTI = "multi"
    COUNTER = "counter"
    ASSIST = "assist"

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    ArtType.MASS: "Массовая",
    ArtType.SINGLE: "Одиночная",
    ArtType.MULTI: "Мульти",
    ArtType.COUNTER: "Контратака",
    ArtType.ASSIST: "Вспомогательная",
}


@dataclass(frozen=True)
class PickResult:
    letters: tuple[str, ...]
    art_type: ArtType
    tiers: dict[int, list[Hero]]  # full ranked list per tier
    reforge: list[Hero]

    def shown(self, tier: int) -> list[Hero]:
        return self.tiers[tier][:SHOWN_PER_TIER]


def overlap(a: Sequence[str], b: Sequence[str]) -> int:
    """How many of the artifact's letters the hero has, counting repeats."""
    return sum((Counter(a) & Counter(b)).values())


def score(hero: Hero, t: ArtType) -> int:
    if t is ArtType.MASS:
        return hero.skills.count("mass")
    if t is ArtType.MULTI:
        return hero.multi
    if t is ArtType.SINGLE:
        return 0 if "mass" in hero.skills else hero.skills.count("single")
    if t is ArtType.COUNTER:
        return 2 if hero.own_counter else 1 if hero.ext_counter else 0
    return 2 if hero.own_assist else 1 if hero.ext_assist else 0


def parse_letters(text: str) -> tuple[str, str, str, str] | None:
    text = re.sub(r"^/pick\b", "", text.strip(), flags=re.IGNORECASE)
    letters = re.sub(r"\s+", "", text).upper().translate(CYRILLIC_TO_LATIN)
    if len(letters) != 4 or not set(letters) <= VALID_LETTERS:
        return None
    return tuple(letters)


def pick(heroes: Sequence[Hero], letters: Sequence[str], art_type: ArtType, rng: random.Random) -> PickResult:
    letters = tuple(letters)
    if len(letters) != 4 or not set(letters) <= VALID_LETTERS:
        raise ValueError(f"нужно 4 буквы A–L, получено {letters!r}")
    # one random tie-break per hero per request, shared by both blocks
    tie = {id(h): rng.random() for h in heroes}
    ranked = sorted(heroes, key=lambda h: (-score(h, art_type), tie[id(h)]))
    tiers = {t: [h for h in ranked if overlap(letters, h.letters) == t] for t in TIERS}
    result = PickResult(letters, art_type, tiers, [])
    shown = {id(h) for t in TIERS for h in result.shown(t)}
    reforge = [h for h in ranked if id(h) not in shown and score(h, art_type) > 0][:REFORGE_COUNT]
    return PickResult(letters, art_type, tiers, reforge)
