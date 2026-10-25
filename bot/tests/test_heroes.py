import unittest
from pathlib import Path

from aom_bot.heroes import Hero, SheetError, parse_heroes
from tests.xlsx_helper import make_xlsx

SNAPSHOT_PATH = Path(__file__).parent / "data" / "heroes-2026-10-25.xlsx"


class ParseHeroesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = SNAPSHOT_PATH.read_bytes()

    def test_counts(self):
        heroes, warnings = parse_heroes(self.snapshot)
        self.assertEqual(len(heroes), 209)
        self.assertEqual(warnings, [])
        self.assertEqual((heroes[0].name, heroes[-1].name), ("Сарпани", "Венди"))
        self.assertEqual(sum("mass" in h.skills for h in heroes), 102)
        self.assertEqual(sum(h.multi > 0 for h in heroes), 66)
        self.assertEqual(sum(h.multi for h in heroes), 90)
        self.assertEqual(sum(h.own_counter for h in heroes), 26)
        self.assertEqual(sum(h.ext_counter for h in heroes), 54)
        self.assertEqual(sum(h.own_assist for h in heroes), 13)  # одна ячейка T — заливка без текста
        self.assertEqual(sum(h.ext_assist for h in heroes), 74)

    def test_known_heroes(self):
        by = {h.name: h for h in parse_heroes(self.snapshot)[0]}
        self.assertEqual(by["Древерад"], Hero("Древерад", "Друиды", ("B", "G", "E", "L"),
                                              ("single", None, "mass", "mass"), 0, False, False, False, True))
        self.assertEqual(by["Рамфорт"].multi, 1)  # «Мульти» в тексте навыка
        self.assertTrue(by["Рамфорт"].own_counter)  # «пассивка с пробудкой» — своя
        self.assertEqual(by["Бенедикт"].skills, ("single", "single", "mass", None))
        self.assertTrue(by["Бенедикт"].ext_counter)  # «2-й навык Артуса»

    def test_not_xlsx(self):
        with self.assertRaises(SheetError):
            parse_heroes(b"<html>Sign in</html>")

    def test_bad_rows_are_warned_not_fatal(self):
        xlsx = make_xlsx({
            6: {"C": ("Хороший", None), "F": ("A", None), "H": ("B", None), "J": ("C", None), "L": ("D", None),
                "N": ("", "FF00FF00"), "O": ("", "FF123456")},
            7: {"C": ("Недописан", None), "F": ("A", None)},
        })
        heroes, warnings = parse_heroes(xlsx)
        self.assertEqual([h.name for h in heroes], ["Хороший"])
        self.assertEqual(heroes[0].skills, ("mass", None, None, None))
        self.assertEqual(len(warnings), 2)
        self.assertIn("Недописан", warnings[1])
        self.assertIn("FF123456", warnings[0])


if __name__ == "__main__":
    unittest.main()
