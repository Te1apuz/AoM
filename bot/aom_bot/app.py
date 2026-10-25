"""Telegram bot: screenshot -> recognized letters -> type buttons -> picked heroes. Long polling.

Stdlib only; OpenCV is needed only by the recognizer passed in from __main__.
"""
import json
import logging
import random
import tempfile
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .picker import ArtType, PickResult, parse_letters, pick
from .render import (HELP, NOT_ADMIN, NOT_FOUND, SESSION_GONE, UNAVAILABLE, format_pick, format_recognized,
                     format_tier_full, format_type_prompt, keyboard)
from .source import HeroSource, SourceUnavailable

log = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    def __init__(self, description: str):
        super().__init__(description)
        self.description = description


class TelegramApi:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.file_base = f"https://api.telegram.org/file/bot{token}/"

    def call(self, method: str, **params) -> Any:
        return self._send(urllib.request.Request(self.base + method, data=json.dumps(params).encode(),
                                                 headers={"Content-Type": "application/json"}))

    def download(self, file_path: str) -> bytes:
        with urllib.request.urlopen(self.file_base + file_path, timeout=70) as r:
            return r.read()

    def send_photo(self, chat_id: int, png: bytes, caption: str, reply_to: int | None = None) -> Any:
        """sendPhoto with an in-memory PNG (multipart)."""
        boundary = "----aom" + str(time.time_ns())
        fields = {"chat_id": chat_id, "caption": caption}
        if reply_to is not None:
            fields["reply_to_message_id"] = reply_to
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                 for k, v in fields.items()]
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="runes.png"\r\n'
                     f'Content-Type: image/png\r\n\r\n'.encode() + png + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self._send(urllib.request.Request(
            self.base + "sendPhoto", data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}))

    def _send(self, req: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                res = json.load(r)
        except urllib.error.HTTPError as e:  # Telegram answers 4xx with a JSON description
            res = json.load(e)
        if not res.get("ok"):
            raise TelegramError(res.get("description", "unknown error"))
        return res["result"]


class Bot:
    def __init__(self, api, source: HeroSource, admin_ids: frozenset[int],
                 rng_factory: Callable[[], random.Random] = random.Random, max_sessions: int = 1000,
                 recognizer=None, save_dir: Path | None = None):
        self.api = api
        self.source = source
        self.admin_ids = admin_ids
        self.rng_factory = rng_factory
        self.max_sessions = max_sessions
        self.recognizer = recognizer  # recognition.Recognizer; None -> letters as text only
        self.save_dir = Path(save_dir) if save_dir else None
        # (chat_id, message_id) of the bot's prompt -> (letters, last pick or None)
        self.sessions: OrderedDict[tuple[int, int], tuple[tuple[str, ...], PickResult | None]] = OrderedDict()

    def handle_update(self, upd: dict) -> None:
        if "message" in upd:
            self._on_message(upd["message"])
        elif "callback_query" in upd:
            self._on_callback(upd["callback_query"])

    def offer_types(self, chat_id: int, letters: Sequence[str], reply_to: int | None = None) -> None:
        params = {"chat_id": chat_id, "text": format_type_prompt(letters), "reply_markup": keyboard(None)}
        if reply_to is not None:
            params["reply_to_message_id"] = reply_to
        sent = self.api.call("sendMessage", **params)
        self._remember((chat_id, sent["message_id"]), (tuple(letters), None))

    def _on_message(self, msg: dict) -> None:
        chat = msg["chat"]["id"]
        image = self._image_of(msg)
        if image and self.recognizer:
            self._recognize(msg, *image)
            return
        text = msg.get("text", "").strip()
        if text.startswith("/refresh"):
            self._refresh(chat, msg.get("from", {}).get("id"))
            return
        letters = parse_letters(text) if text else None
        if letters:
            self.offer_types(chat, letters, reply_to=msg["message_id"])
        else:
            self.api.call("sendMessage", chat_id=chat, text=HELP)

    @staticmethod
    def _image_of(msg: dict) -> tuple[str, str] | None:
        """(file_id, kind) of the screenshot in the message, if any."""
        if msg.get("photo"):
            return msg["photo"][-1]["file_id"], "photo"  # largest size Telegram kept
        if msg.get("document", {}).get("mime_type", "").startswith("image/"):
            return msg["document"]["file_id"], "file"  # sent as file: original, uncompressed
        return None

    def _recognize(self, msg: dict, file_id: str, kind: str) -> None:
        chat, message_id = msg["chat"]["id"], msg["message_id"]
        try:
            letters = self._read_letters(msg, file_id, kind)
        except Exception:  # too big for getFile, download error, recognizer crash: the player still gets an answer
            log.exception("recognition failed for message %s", message_id)
            letters = None
        log.info("[%s] recognized %s", kind, letters)
        if not letters:
            self.api.call("sendMessage", chat_id=chat, text=NOT_FOUND, reply_to_message_id=message_id)
            return
        try:
            self.api.send_photo(chat, self.recognizer.strip_png(letters), format_recognized(letters),
                                reply_to=message_id)
        except Exception:  # the type buttons matter more than the picture
            log.exception("sending the constellation strip failed")
        self.offer_types(chat, letters)

    def _read_letters(self, msg: dict, file_id: str, kind: str) -> tuple[str, ...] | None:
        message_id = msg["message_id"]
        file_path = self.api.call("getFile", file_id=file_id)["file_path"]
        data = self.api.download(file_path)
        ext = Path(file_path).suffix or ".jpg"
        if self.save_dir:
            user = msg.get("from", {})
            name = f"{time.strftime('%Y%m%d-%H%M%S')}_{user.get('id')}_{message_id}_{kind}{ext}"
            self.save_dir.mkdir(parents=True, exist_ok=True)
            image_path = self.save_dir / name
            image_path.write_bytes(data)
            letters = self.recognizer.letters(image_path)
            with open(self.save_dir / "log.jsonl", "a") as f:
                f.write(json.dumps({"file": name, "user": user.get("username") or user.get("id"), "kind": kind,
                                    "recognized": "".join(letters) if letters else None}, ensure_ascii=False) + "\n")
        else:
            with tempfile.TemporaryDirectory() as d:
                image_path = Path(d) / f"screen{ext}"
                image_path.write_bytes(data)
                letters = self.recognizer.letters(image_path)
        return letters

    def _refresh(self, chat: int, user_id: int | None) -> None:
        if user_id not in self.admin_ids:
            self.api.call("sendMessage", chat_id=chat, text=NOT_ADMIN)
            return
        try:
            snap = self.source.refresh()
        except SourceUnavailable:
            self.api.call("sendMessage", chat_id=chat, text=UNAVAILABLE)
            return
        text = f"Загружено {len(snap.heroes)} героев, данные от {snap.loaded_at:%d.%m.%Y %H:%M}."
        if snap.stale:
            text += " Обновить не удалось, это старая копия."
        self.api.call("sendMessage", chat_id=chat, text=text)

    def _on_callback(self, q: dict) -> None:
        chat, message_id = q["message"]["chat"]["id"], q["message"]["message_id"]
        session = self.sessions.get((chat, message_id))
        kind, _, arg = q.get("data", "").partition(":")
        if session is None or (kind == "all" and session[1] is None):
            self.api.call("answerCallbackQuery", callback_query_id=q["id"], text=SESSION_GONE)
            return
        self.sessions.move_to_end((chat, message_id))
        letters, result = session
        if kind == "t":
            try:
                snap = self.source.get()
            except SourceUnavailable:
                self.api.call("sendMessage", chat_id=chat, text=UNAVAILABLE)
                self.api.call("answerCallbackQuery", callback_query_id=q["id"])
                return
            result = pick(snap.heroes, letters, ArtType(arg), self.rng_factory())
            self.sessions[(chat, message_id)] = (letters, result)
            try:
                self.api.call("editMessageText", chat_id=chat, message_id=message_id,
                              text=format_pick(result, snap.loaded_at if snap.stale else None),
                              reply_markup=keyboard(result))
            except TelegramError as e:
                if "message is not modified" not in e.description:
                    raise
        elif kind == "all":
            for text in format_tier_full(result, int(arg)):
                self.api.call("sendMessage", chat_id=chat, text=text)
        self.api.call("answerCallbackQuery", callback_query_id=q["id"])

    def _remember(self, key: tuple[int, int], value) -> None:
        self.sessions[key] = value
        self.sessions.move_to_end(key)
        while len(self.sessions) > self.max_sessions:
            self.sessions.popitem(last=False)


def run(bot: Bot, api: TelegramApi) -> None:
    me = api.call("getMe")
    log.info("running as @%s", me["username"])
    offset = 0
    while True:
        try:
            updates = api.call("getUpdates", offset=offset, timeout=50)
        except Exception as e:
            log.warning("poll error: %s", e)
            time.sleep(5)
            continue
        for upd in updates:
            offset = upd["update_id"] + 1
            try:
                bot.handle_update(upd)
            except Exception:
                log.exception("update %s failed", upd.get("update_id"))
