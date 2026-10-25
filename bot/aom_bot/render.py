"""Telegram texts and inline keyboards for the hero picker."""
from collections.abc import Sequence
from datetime import datetime

from .heroes import Hero
from .picker import TIERS, ArtType, PickResult

HELP = ("Пришли скриншот карточки артефакта (лучше файлом, без сжатия) — "
        "я распознаю созвездия и подберу героев.\n"
        "Можно и буквами: 4 буквы созвездий, например L G E B.")
UNAVAILABLE = "Таблица героев сейчас недоступна, попробуй позже."
SESSION_GONE = "Это сообщение устарело, пришли скриншот или буквы заново."
NOT_ADMIN = "Эта команда только для админов."
NOT_FOUND = "Не нашёл 4 значка созвездий. Пришли скриншот карточки артефакта, лучше файлом (без сжатия)."
TG_LIMIT = 4096


def hero_line(h: Hero) -> str:
    return f"{h.name} ({' '.join(h.letters)})"


def format_type_prompt(letters: Sequence[str]) -> str:
    return f"Артефакт: {' '.join(letters)}\nВыбери тип артефакта по его главному свойству:"


def format_pick(r: PickResult, stale_since: datetime | None = None) -> str:
    lines = [f"Артефакт: {' '.join(r.letters)} · тип: {r.art_type.label}", "", "По созвездиям"]
    for t in TIERS:
        lines.append(f"{t}/4 — {', '.join(map(hero_line, r.shown(t))) or '—'}")
    lines += ["", "Под перековку", ", ".join(map(hero_line, r.reforge)) or "подходящих нет"]
    if stale_since is not None:
        lines += ["", f"⚠️ Данные от {stale_since:%d.%m.%Y %H:%M}, обновить не удалось."]
    return "\n".join(lines)


def format_tier_full(r: PickResult, tier: int) -> list[str]:
    heroes = r.tiers[tier]
    lines = [f"{tier}/4 · {r.art_type.label} · все {len(heroes)}"]
    lines += [f"{i}. {hero_line(h)}" for i, h in enumerate(heroes, 1)]
    return chunk_lines(lines)


def chunk_lines(lines: list[str], limit: int = TG_LIMIT) -> list[str]:
    chunks, cur = [], ""
    for line in lines:
        candidate = f"{cur}\n{line}" if cur else line
        if cur and len(candidate) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def keyboard(r: PickResult | None) -> dict:
    types = [{"text": t.label, "callback_data": f"t:{t.value}"} for t in ArtType]
    rows = [types[:3], types[3:]]
    if r is not None:
        all_row = [{"text": f"Все {t}/4 ({len(r.tiers[t])})", "callback_data": f"all:{t}"}
                   for t in TIERS if r.tiers[t]]
        if all_row:
            rows.append(all_row)
    return {"inline_keyboard": rows}
