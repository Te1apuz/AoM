import random
import unittest
from pathlib import Path

from aom_bot.heroes import Hero, parse_heroes, read_sheet
from aom_bot.picker import TIERS, ArtType, overlap, parse_letters, pick, score

SNAPSHOT = (Path(__file__).parent / "data" / "heroes-2026-10-25.xlsx").read_bytes()
HEROES = parse_heroes(SNAPSHOT)[0]


def hero(skills, multi=0, oc=False, ec=False, oa=False, ea=False, name="x", letters="ABCD"):
    return Hero(name, "f", tuple(letters), tuple(skills), multi, oc, ec, oa, ea)


class OverlapTest(unittest.TestCase):
    def test_overlap_multiset(self):
        self.assertEqual(overlap("BBEL", "BEEG"), 2)
        self.assertEqual(overlap("LGEB", "BGEL"), 4)
        self.assertEqual(overlap("AAAA", "ABCD"), 1)

    def test_overlap_matches_redcat_column_m(self):
        rows = read_sheet(SNAPSHOT)
        art = [rows[3][c].text for c in "EGIK"]  # артефакт, вбитый в таблицу: L G E B
        self.assertEqual(art, ["L", "G", "E", "B"])
        expected = {rows[r]["C"].text: int(float(rows[r]["M"].text))
                    for r in rows if r >= 6 and rows[r].get("C") and rows[r]["C"].text}
        self.assertEqual(len(expected), 209)
        self.assertEqual({h.name: overlap(art, h.letters) for h in HEROES}, expected)


class ScoreTest(unittest.TestCase):
    def test_score_table(self):
        self.assertEqual(score(hero(("mass", "mass", "single", None)), ArtType.MASS), 2)
        self.assertEqual(score(hero(("single", None, None, None), multi=2), ArtType.MULTI), 2)
        self.assertEqual(score(hero(("single", "single", "single", None)), ArtType.SINGLE), 3)
        self.assertEqual(score(hero(("single", "single", "mass", None)), ArtType.SINGLE), 0)
        self.assertEqual(score(hero((None,) * 4, oc=True, ec=True), ArtType.COUNTER), 2)
        self.assertEqual(score(hero((None,) * 4, ec=True), ArtType.COUNTER), 1)
        self.assertEqual(score(hero((None,) * 4, ea=True), ArtType.ASSIST), 1)
        self.assertEqual(score(hero((None,) * 4), ArtType.ASSIST), 0)

    def test_labels(self):
        self.assertEqual([t.label for t in ArtType],
                         ["Массовая", "Одиночная", "Мульти", "Контратака", "Вспомогательная"])


class PickTest(unittest.TestCase):
    def test_pick_lgeb_mass(self):
        r = pick(HEROES, "LGEB", ArtType.MASS, random.Random(1))
        self.assertEqual({t: len(r.tiers[t]) for t in TIERS}, {4: 1, 3: 7, 2: 50})
        self.assertEqual([h.name for h in r.shown(4)], ["Древерад"])
        self.assertEqual(len(r.shown(2)), 3)
        for t in TIERS:  # отсортировано по оценке
            s = [score(h, ArtType.MASS) for h in r.tiers[t]]
            self.assertEqual(s, sorted(s, reverse=True))
        shown = {h.name for t in TIERS for h in r.shown(t)}
        self.assertEqual(len(r.reforge), 5)
        self.assertFalse(shown & {h.name for h in r.reforge})
        self.assertTrue(all(score(h, ArtType.MASS) > 0 for h in r.reforge))

    def test_ties_random_but_seeded(self):
        a = pick(HEROES, "LGEB", ArtType.COUNTER, random.Random(1))
        b = pick(HEROES, "LGEB", ArtType.COUNTER, random.Random(1))
        self.assertEqual(a, b)
        orders = {tuple(h.name for h in pick(HEROES, "LGEB", ArtType.COUNTER, random.Random(s)).reforge)
                  for s in range(10)}
        self.assertGreater(len(orders), 1)  # 20 героев делят высшую оценку

    def test_reforge_empty_when_no_positive_score(self):
        heroes = [hero(("mass",) * 4, name=n) for n in "xyz"]
        self.assertEqual(pick(heroes, "EFGH", ArtType.COUNTER, random.Random(0)).reforge, [])

    def test_pick_rejects_bad_letters(self):
        with self.assertRaises(ValueError):
            pick(HEROES, "LGEZ", ArtType.MASS, random.Random(0))


class ParseLettersTest(unittest.TestCase):
    def test_parse_letters(self):  # Review Focus №1
        self.assertEqual(parse_letters("L g е B"), ("L", "G", "E", "B"))  # «е» кириллическая
        self.assertEqual(parse_letters("/pick lgeb"), ("L", "G", "E", "B"))
        self.assertEqual(parse_letters("АВСК"), ("A", "B", "C", "K"))  # всё кириллицей
        self.assertIsNone(parse_letters("LGE"))
        self.assertIsNone(parse_letters("LGEZ"))
        self.assertIsNone(parse_letters("привет"))


if __name__ == "__main__":
    unittest.main()
