import unittest
from datetime import datetime

from aom_bot.heroes import Hero
from aom_bot.picker import ArtType, PickResult
from aom_bot.render import chunk_lines, format_pick, format_tier_full, format_type_prompt, hero_line, keyboard


def hero(name, letters):
    return Hero(name, "f", tuple(letters), ("mass", None, None, None), 0, False, False, False, False)


RESULT = PickResult(
    ("L", "G", "E", "B"), ArtType.MASS,
    tiers={
        4: [],
        3: [hero("Теон", "BEDG"), hero("Тан'Арг", "BGLL")],
        2: [hero("Артус", "GFEA"), hero("Люциус", "EEBA"), hero("Врея", "DBBE")]
           + [hero(f"X{i}", "GEAA") for i in range(1, 48)],
    },
    reforge=[],
)


class RenderTest(unittest.TestCase):
    def test_hero_line(self):
        self.assertEqual(hero_line(hero("Древерад", "BGEL")), "Древерад (B G E L)")

    def test_type_prompt(self):
        self.assertEqual(format_type_prompt("LGEB"),
                         "Артефакт: L G E B\nВыбери тип артефакта по его главному свойству:")

    def test_format_pick_exact(self):
        self.assertEqual(format_pick(RESULT), (
            "Артефакт: L G E B · тип: Массовая\n"
            "\n"
            "По созвездиям\n"
            "4/4 — —\n"
            "3/4 — Теон (B E D G), Тан'Арг (B G L L)\n"
            "2/4 — Артус (G F E A), Люциус (E E B A), Врея (D B B E)\n"
            "\n"
            "Под перековку\n"
            "подходящих нет"))

    def test_format_pick_with_reforge(self):
        r = PickResult(RESULT.letters, RESULT.art_type, RESULT.tiers, [hero("Герда", "BBBB"), hero("Рок", "BJBB")])
        self.assertTrue(format_pick(r).endswith("Под перековку\nГерда (B B B B), Рок (B J B B)"))

    def test_stale_note(self):
        text = format_pick(RESULT, stale_since=datetime(2026, 10, 25, 14, 5))
        self.assertTrue(text.endswith("\n\n⚠️ Данные от 25.10.2026 14:05, обновить не удалось."))

    def test_keyboard(self):
        kb = keyboard(RESULT)["inline_keyboard"]
        self.assertEqual([b["callback_data"] for row in kb[:2] for b in row],
                         ["t:mass", "t:single", "t:multi", "t:counter", "t:assist"])
        self.assertEqual([b["text"] for row in kb[:2] for b in row],
                         ["Массовая", "Одиночная", "Мульти", "Контратака", "Вспомогательная"])
        self.assertEqual([(b["text"], b["callback_data"]) for b in kb[2]],
                         [("Все 3/4 (2)", "all:3"), ("Все 2/4 (50)", "all:2")])  # пустая 4/4 — без кнопки
        self.assertEqual(len(keyboard(None)["inline_keyboard"]), 2)  # до выбора типа — только типы

    def test_tier_full_and_chunks(self):
        msgs = format_tier_full(RESULT, 2)
        self.assertTrue(msgs[0].startswith("2/4 · Массовая · все 50\n1. Артус (G F E A)"))
        self.assertIn("50. X47 (G E A A)", msgs[-1])
        self.assertEqual(chunk_lines(["aaaa", "bbbb", "cc"], limit=9), ["aaaa\nbbbb", "cc"])


if __name__ == "__main__":
    unittest.main()
