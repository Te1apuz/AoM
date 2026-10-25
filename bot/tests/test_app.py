import random
import unittest
from datetime import datetime
from pathlib import Path

from aom_bot.app import Bot, TelegramError
from aom_bot.heroes import parse_heroes
from aom_bot.render import HELP, NOT_ADMIN, NOT_FOUND, SESSION_GONE, UNAVAILABLE, format_type_prompt, keyboard
from aom_bot.source import Snapshot, SourceUnavailable

HEROES = parse_heroes((Path(__file__).parent / "data" / "heroes-2026-10-25.xlsx").read_bytes())[0]
LOADED = datetime(2026, 10, 25, 12, 0)
ADMIN = 42


class FakeApi:
    def __init__(self):
        self.calls = []
        self.failures = {}
        self.next_id = 1

    def download(self, file_path):
        self.calls.append(("download", {"file_path": file_path}))
        return b"fake image bytes"

    def send_photo(self, chat_id, png, caption, reply_to=None):
        self.calls.append(("sendPhoto", {"chat_id": chat_id, "png": png, "caption": caption,
                                         "reply_to_message_id": reply_to}))

    def fail(self, method, exc):
        self.failures[method] = exc

    def call(self, method, **params):
        self.calls.append((method, params))
        if method in self.failures:
            raise self.failures[method]
        if method == "sendMessage":
            self.next_id += 1
            return {"message_id": self.next_id - 1}
        if method == "getFile":
            return {"file_path": f"photos/{params['file_id']}.jpg"}
        return True

    def sent(self, method):
        return [p for m, p in self.calls if m == method]


class FakeSource:
    def __init__(self, snap=None, exc=None):
        self.snap = snap or Snapshot(HEROES, LOADED, False)
        self.exc = exc

    def get(self):
        if self.exc:
            raise self.exc
        return self.snap

    refresh = get


def msg(text, chat=5, user=ADMIN, message_id=10):
    return {"message": {"message_id": message_id, "chat": {"id": chat}, "from": {"id": user}, "text": text}}


def cb(data, message_id, chat=5, user=ADMIN):
    return {"callback_query": {"id": "q", "data": data, "from": {"id": user},
                               "message": {"message_id": message_id, "chat": {"id": chat}}}}


class BotTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.bot = self.make_bot(FakeSource())

    def make_bot(self, source):
        return Bot(self.api, source, frozenset({ADMIN}), rng_factory=lambda: random.Random(1))

    def test_letters_text_offers_types(self):
        self.bot.handle_update(msg("l g е b"))
        m, p = self.api.calls[-1]
        self.assertEqual((m, p["text"]), ("sendMessage", format_type_prompt("LGEB")))
        self.assertEqual(p["reply_markup"], keyboard(None))

    def test_type_press_edits_message(self):
        self.bot.handle_update(msg("LGEB"))
        self.bot.handle_update(cb("t:mass", message_id=1))
        p = self.api.sent("editMessageText")[-1]
        self.assertEqual((p["chat_id"], p["message_id"]), (5, 1))
        self.assertTrue(p["text"].startswith("Артефакт: L G E B · тип: Массовая"))
        self.assertEqual(p["reply_markup"]["inline_keyboard"][2][-1]["callback_data"], "all:2")
        self.assertIn("answerCallbackQuery", [m for m, _ in self.api.calls])

    def test_show_all_uses_same_order(self):
        self.bot.handle_update(msg("LGEB"))
        self.bot.handle_update(cb("t:mass", message_id=1))
        self.bot.handle_update(cb("all:2", message_id=1))
        edited = self.api.sent("editMessageText")[-1]["text"]
        full = self.api.sent("sendMessage")[-1]["text"]
        top3 = edited.split("2/4 — ")[1].split("\n")[0].split(", ")
        self.assertEqual([line.split(". ", 1)[1] for line in full.split("\n")[1:4]], top3)

    def test_stale_session(self):  # Review Focus №3
        self.bot.handle_update(cb("t:mass", message_id=999))
        self.assertEqual(self.api.calls[-1], ("answerCallbackQuery", {"callback_query_id": "q", "text": SESSION_GONE}))

    def test_message_not_modified_is_ignored(self):  # Review Focus №5
        self.api.fail("editMessageText", TelegramError("Bad Request: message is not modified"))
        self.bot.handle_update(msg("LGEB"))
        self.bot.handle_update(cb("t:mass", message_id=1))  # не бросает
        self.assertEqual(self.api.calls[-1][0], "answerCallbackQuery")

    def test_other_telegram_errors_propagate(self):
        self.api.fail("editMessageText", TelegramError("Bad Request: chat not found"))
        self.bot.handle_update(msg("LGEB"))
        with self.assertRaises(TelegramError):
            self.bot.handle_update(cb("t:mass", message_id=1))

    def test_source_unavailable(self):
        bot = self.make_bot(FakeSource(exc=SourceUnavailable("offline")))
        bot.handle_update(msg("LGEB"))
        bot.handle_update(cb("t:mass", message_id=1))
        self.assertEqual(self.api.sent("sendMessage")[-1]["text"], UNAVAILABLE)
        self.assertEqual(self.api.sent("editMessageText"), [])

    def test_stale_snapshot_adds_note(self):
        bot = self.make_bot(FakeSource(Snapshot(HEROES, LOADED, True)))
        bot.handle_update(msg("LGEB"))
        bot.handle_update(cb("t:mass", message_id=1))
        self.assertTrue(self.api.sent("editMessageText")[-1]["text"].endswith(
            "⚠️ Данные от 25.10.2026 12:00, обновить не удалось."))

    def test_refresh_admin_only(self):
        self.bot.handle_update(msg("/refresh", user=7))
        self.assertEqual(self.api.sent("sendMessage")[-1]["text"], NOT_ADMIN)
        self.bot.handle_update(msg("/refresh", user=ADMIN))
        self.assertEqual(self.api.sent("sendMessage")[-1]["text"], "Загружено 209 героев, данные от 25.10.2026 12:00.")

    def test_offer_types_hook(self):
        self.bot.offer_types(5, "LGEB", reply_to=7)
        p = self.api.sent("sendMessage")[-1]
        self.assertEqual((p["text"], p["reply_to_message_id"]), (format_type_prompt("LGEB"), 7))

    def test_other_text_gets_help(self):
        self.bot.handle_update(msg("привет"))
        self.assertEqual(self.api.sent("sendMessage")[-1]["text"], HELP)

    def test_sessions_are_bounded(self):
        bot = Bot(self.api, FakeSource(), frozenset(), max_sessions=2)
        for _ in range(3):
            bot.handle_update(msg("LGEB"))
        bot.handle_update(cb("t:mass", message_id=1))  # самая старая вытеснена
        self.assertEqual(self.api.calls[-1][1].get("text"), SESSION_GONE)


class FakeRecognizer:
    def __init__(self, result):
        self.result = result
        self.paths = []

    def letters(self, image_path):
        self.paths.append(Path(image_path))
        self.seen_bytes = Path(image_path).read_bytes()
        return self.result

    def strip_png(self, letters):
        return b"\x89PNG strip " + "".join(letters).encode()


def photo_msg(chat=5, user=ADMIN, message_id=10):
    return {"message": {"message_id": message_id, "chat": {"id": chat}, "from": {"id": user, "username": "tester"},
                        "photo": [{"file_id": "small"}, {"file_id": "big"}]}}


def file_msg(mime="image/jpeg", chat=5, message_id=11):
    return {"message": {"message_id": message_id, "chat": {"id": chat}, "from": {"id": ADMIN},
                        "document": {"file_id": "doc", "mime_type": mime}}}


class RecognitionFlowTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()

    def make_bot(self, result, save_dir=None):
        self.rec = FakeRecognizer(result)
        return Bot(self.api, FakeSource(), frozenset(), rng_factory=lambda: random.Random(1),
                   recognizer=self.rec, save_dir=save_dir)

    def test_photo_recognized_then_types_offered(self):
        bot = self.make_bot(("H", "L", "J", "K"))
        bot.handle_update(photo_msg())
        self.assertEqual(self.api.calls[0], ("getFile", {"file_id": "big"}))  # самое крупное фото
        self.assertEqual(self.rec.seen_bytes, b"fake image bytes")
        methods = [m for m, _ in self.api.calls]
        self.assertLess(methods.index("sendPhoto"), methods.index("sendMessage"))  # сначала распознавание
        photo = self.api.sent("sendPhoto")[0]
        self.assertEqual((photo["caption"], photo["png"], photo["reply_to_message_id"]),
                         ("Созвездия артефакта: H L J K", b"\x89PNG strip HLJK", 10))
        prompt = self.api.sent("sendMessage")[-1]
        self.assertEqual((prompt["text"], prompt["reply_markup"]), (format_type_prompt("HLJK"), keyboard(None)))
        bot.handle_update(cb("t:mass", message_id=1))  # кнопки работают и после распознавания
        self.assertTrue(self.api.sent("editMessageText")[-1]["text"].startswith("Артефакт: H L J K"))

    def test_image_document_is_recognized(self):
        bot = self.make_bot(("H", "L", "J", "K"))
        bot.handle_update(file_msg())
        self.assertEqual(self.api.calls[0], ("getFile", {"file_id": "doc"}))

    def test_non_image_document_gets_help(self):
        bot = self.make_bot(("H", "L", "J", "K"))
        bot.handle_update(file_msg(mime="application/pdf"))
        self.assertEqual(self.api.sent("sendMessage")[-1]["text"], HELP)

    def test_not_found(self):
        bot = self.make_bot(None)
        bot.handle_update(photo_msg())
        self.assertEqual(self.api.sent("sendMessage")[-1]["text"], NOT_FOUND)
        self.assertEqual(self.api.sent("sendPhoto"), [])

    def test_save_dir_keeps_screens_and_log(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            bot = self.make_bot(("H", "L", "J", "K"), save_dir=Path(d))
            bot.handle_update(photo_msg())
            entry = json.loads((Path(d) / "log.jsonl").read_text().splitlines()[-1])
            self.assertEqual((entry["user"], entry["kind"], entry["recognized"]), ("tester", "photo", "HLJK"))
            self.assertEqual((Path(d) / entry["file"]).read_bytes(), b"fake image bytes")

    def test_without_recognizer_photo_gets_help(self):
        bot = Bot(self.api, FakeSource(), frozenset())
        bot.handle_update(photo_msg())
        self.assertEqual(self.api.sent("sendMessage")[-1]["text"], HELP)


if __name__ == "__main__":
    unittest.main()
