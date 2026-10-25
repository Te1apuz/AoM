"""Telegram bot: artifact letters -> type buttons -> picked heroes. Long polling, stdlib only."""
import json
import logging
import random
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any

from .picker import ArtType, PickResult, parse_letters, pick
from .render import (HELP, NOT_ADMIN, SESSION_GONE, UNAVAILABLE, format_pick, format_tier_full,
                     format_type_prompt, keyboard)
from .source import HeroSource, SourceUnavailable

log = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    def __init__(self, description: str):
        super().__init__(description)
        self.description = description


class TelegramApi:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method: str, **params) -> Any:
        req = urllib.request.Request(self.base + method, data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
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
                 rng_factory: Callable[[], random.Random] = random.Random, max_sessions: int = 1000):
        self.api = api
        self.source = source
        self.admin_ids = admin_ids
        self.rng_factory = rng_factory
        self.max_sessions = max_sessions
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
        text = msg.get("text", "").strip()
        if text.startswith("/refresh"):
            self._refresh(chat, msg.get("from", {}).get("id"))
            return
        letters = parse_letters(text) if text else None
        if letters:
            self.offer_types(chat, letters, reply_to=msg["message_id"])
        else:
            self.api.call("sendMessage", chat_id=chat, text=HELP)

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
