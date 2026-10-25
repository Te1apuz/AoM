# Подбор героя под артефакт — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** По 4 буквам созвездий артефакта и выбранному типу бот отвечает двумя блоками: герои по совпадению букв (4/3/2) и герои под перековку.

**Architecture:** Пакет `bot/aom_bot/` в репо форка. Чистые модули: разбор xlsx (`heroes.py`), подбор (`picker.py`), текст и кнопки (`render.py`). Отдельно источник данных с кэшем (`source.py`) и Telegram-обвязка на long polling (`app.py`). **Один бот** (решение пользователя): распознаватель из спайка шага 1 переносится в `recognition.py` (Task 6). Порядок для игрока такой: скриншот → бот показывает распознанные буквы → кнопки типа → герои. Буквы текстом остаются запасным вводом.

**Tech Stack:** Python 3.15. Ядро (Task 1–5) — только стандартная библиотека (`zipfile`, `xml.etree`, `urllib`, `unittest`). Распознавание (Task 6) — `opencv-python-headless` и `numpy` в `bot/.venv`, как в спайке.

**Spec:** `docs/superpowers/specs/2026-10-25-hero-picker-design.md`

## Global Constraints

- Код — в `bot/` этого репо (ветка `worktree-hero-picker-design`); тесты — `bot/tests/`, запуск из корня репо: `python3 -m unittest discover -s bot/tests -t bot -v`.
- Без сторонних зависимостей в ядре; `cv2`/`numpy` импортирует только `recognition.py`, и его тесты пропускаются (`skipUnless`), если `cv2` не установлен.
- Источник: `https://docs.google.com/spreadsheets/d/18IWMCIs8q2usE4HzB9enjbVJ6C1YLw50/export?format=xlsx`, лист «Таблица», герои с 6-й строки.
- Цвета навыков — точное сравнение ARGB: `FF00FF00` массовая, `FFFF9900` одиночная.
- Совпадение — пересечение мультимножеств букв.
- Блок 1: группы 4/4, 3/4, 2/4, по 3 героя. Блок 2: 5 героев с оценкой > 0, не показанных в блоке 1. Пустая группа — «—», пустой блок 2 — «подходящих нет».
- При равенстве оценок порядок случайный, фиксируется один раз на запрос.
- Протухшие данные: ответ по последней копии + строка «данные от <дата>, обновить не удалось»; без копии — сообщение, что таблица недоступна.
- Обновление по команде — только Telegram id из `AOM_ADMIN_IDS` (через запятую).
- Тестовый снимок — `bot/tests/data/heroes-2026-10-25.xlsx` (копия живой выгрузки 2026-10-25, 209 героев).

## Review Focus

1. Буквы набраны кириллицей или строчными («L g е B» с русской «е») — бот должен понять их как латиницу.
2. В таблице появилась недозаполненная строка (имя есть, букв меньше 4 или чужой цвет навыка) — импорт пропускает/понижает её с предупреждением в лог, остальные герои работают.
3. Нажатие кнопки на сообщении, сделанном до перезапуска бота (сессии нет) — короткий ответ «устарело, пришли скриншот заново», без падения.
4. Google вместо xlsx вернул HTML (страница входа, лимит) — считается неудачной загрузкой, бот отвечает по кэшу с пометкой.
5. Повторное нажатие того же типа даёт тот же текст — Telegram отвечает «message is not modified»; это не ошибка, бот её глотает.

---

### Task 1: Разбор таблицы

**Files:**
- Create: `bot/aom_bot/__init__.py` (пустой), `bot/aom_bot/heroes.py`
- Create: `bot/tests/__init__.py` (пустой), `bot/tests/test_heroes.py`, `bot/tests/data/heroes-2026-10-25.xlsx`

**Interfaces:**
- Produces:
  - `class SheetError(ValueError)` — битый/не-xlsx файл, нет листа «Таблица».
  - `@dataclass(frozen=True) class Cell: text: str; fill: str | None` — `text` уже после `strip()`, `fill` — ARGB `fgColor rgb` или `None`.
  - `read_sheet(xlsx: bytes, sheet_name: str = "Таблица") -> dict[int, dict[str, Cell]]` — номер строки → буква колонки → ячейка.
  - `@dataclass(frozen=True) class Hero: name: str; faction: str; letters: tuple[str, str, str, str]; skills: tuple[str | None, str | None, str | None, str | None]` (`"mass"` / `"single"` / `None`)`; multi: int; own_counter: bool; ext_counter: bool; own_assist: bool; ext_assist: bool`
  - `parse_heroes(xlsx: bytes) -> tuple[list[Hero], list[str]]` — герои в порядке строк и список предупреждений.

- [ ] **Step 1: Положить снимок.** Скачать `EXPORT_URL` в `bot/tests/data/heroes-2026-10-25.xlsx` (`curl -sL -o ...`). Если в живой таблице уже не 209 героев, взять копию `/Users/den/.claude/jobs/016d195d/tmp/live.xlsx` (выгрузка 2026-10-25); если её нет — взять свежую и пересчитать числа в тестах ниже, записав дату в имя файла.

- [ ] **Step 2: Написать падающие тесты** в `bot/tests/test_heroes.py` (`unittest.TestCase`, снимок читается один раз в `setUpClass`):

```python
def test_counts(self):
    heroes, warnings = parse_heroes(SNAPSHOT)
    self.assertEqual(len(heroes), 209)
    self.assertEqual(warnings, [])
    self.assertEqual((heroes[0].name, heroes[-1].name), ("Сарпани", "Венди"))
    self.assertEqual(sum("mass" in h.skills for h in heroes), 102)
    self.assertEqual(sum(h.multi > 0 for h in heroes), 66)
    self.assertEqual(sum(h.multi for h in heroes), 90)
    self.assertEqual(sum(h.own_counter for h in heroes), 26)
    self.assertEqual(sum(h.ext_counter for h in heroes), 54)
    self.assertEqual(sum(h.own_assist for h in heroes), 13)   # одна ячейка T — заливка без текста
    self.assertEqual(sum(h.ext_assist for h in heroes), 74)

def test_known_heroes(self):
    by = {h.name: h for h in parse_heroes(SNAPSHOT)[0]}
    self.assertEqual(by["Древерад"], Hero("Древерад", "Друиды", ("B", "G", "E", "L"),
        ("single", None, "mass", "mass"), 0, False, False, False, True))
    self.assertEqual(by["Рамфорт"].multi, 1)          # «Мульти» в тексте навыка
    self.assertTrue(by["Рамфорт"].own_counter)        # «пассивка с пробудкой» — своя
    self.assertEqual(by["Бенедикт"].skills, ("single", "single", "mass", None))
    self.assertTrue(by["Бенедикт"].ext_counter)       # «2-й навык Артуса»

def test_not_xlsx(self):
    with self.assertRaises(SheetError):
        parse_heroes(b"<html>Sign in</html>")
```

Плюс тест Review Focus №2 на синтетической книге. Собрать минимальный xlsx в памяти: helper `make_xlsx(rows: dict[int, dict[str, tuple[str, str | None]]]) -> bytes` в `bot/tests/xlsx_helper.py` пишет `[Content_Types].xml`, `xl/workbook.xml` с листом «Таблица», `xl/_rels/workbook.xml.rels`, `xl/styles.xml` с заливками и `xl/worksheets/sheet1.xml` с inline-строками.

```python
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
```

- [ ] **Step 3: Запустить** `python3 -m unittest discover -s bot/tests -t bot -v` — ожидается ImportError/FAIL.

- [ ] **Step 4: Реализовать `bot/aom_bot/heroes.py`.**
  - `read_sheet`. Лист ищется по имени: `xl/workbook.xml` → `r:id` → `xl/_rels/workbook.xml.rels` → путь листа.
  - Текст ячейки: `t="s"` — shared string (склеить все `<t>` из runs); `t="inlineStr"` — `<is>`; иначе `<v>`.
  - Заливка: `s` → `cellXfs[s].fillId` → `fills[i].patternFill.fgColor@rgb`.
  - `BadZipFile`, `KeyError` и отсутствие листа превращаются в `SheetError`.
  - `parse_heroes`, строки с 6-й:
    - Пустое имя (C) — строка пропускается молча.
    - Буквы F/H/J/L — если это не 4 буквы из `A`–`L`, строка пропускается с предупреждением `"<имя> (строка N): ожидалось 4 буквы, есть ..."`.
    - Навыки N–Q: `FF00FF00` → `"mass"`, `FFFF9900` → `"single"`, нет заливки → `None`. Любой другой цвет → `None` плюс предупреждение `"<имя>: навык K, неизвестный цвет <rgb>"`.
    - `multi` — число ячеек N–Q, где в тексте есть подстрока `"Мульти"`.
    - R/S/T/U — флаг `bool(text) or fill is not None`.
  - Общая заметка из строки 2 не читается вообще.

- [ ] **Step 5: Запустить тесты** — все PASS.

- [ ] **Step 6: Commit** `git add bot && git commit -m "bot: parse heroes from RedCat xlsx"`

### Task 2: Подбор

**Files:**
- Create: `bot/aom_bot/picker.py`, `bot/tests/test_picker.py`

**Interfaces:**
- Consumes: `Hero`, `parse_heroes`, `read_sheet` (Task 1).
- Produces:
  - `class ArtType(Enum)`: `MASS="mass"`, `SINGLE="single"`, `MULTI="multi"`, `COUNTER="counter"`, `ASSIST="assist"`; свойство `label` → «Массовая», «Одиночная», «Мульти», «Контратака», «Вспомогательная».
  - `TIERS = (4, 3, 2)`, `SHOWN_PER_TIER = 3`, `REFORGE_COUNT = 5`
  - `overlap(a: Sequence[str], b: Sequence[str]) -> int`
  - `score(hero: Hero, t: ArtType) -> int`
  - `parse_letters(text: str) -> tuple[str, str, str, str] | None`
  - `@dataclass(frozen=True) class PickResult: letters: tuple[str, ...]; art_type: ArtType; tiers: dict[int, list[Hero]]; reforge: list[Hero]`; метод `shown(tier: int) -> list[Hero]` = `tiers[tier][:SHOWN_PER_TIER]`.
  - `pick(heroes: Sequence[Hero], letters: Sequence[str], art_type: ArtType, rng: random.Random) -> PickResult` — `ValueError`, если `letters` не 4 буквы A–L.

- [ ] **Step 1: Написать падающие тесты:**

```python
def test_overlap_multiset(self):
    self.assertEqual(overlap("BBEL", "BEEG"), 2)
    self.assertEqual(overlap("LGEB", "BGEL"), 4)
    self.assertEqual(overlap("AAAA", "ABCD"), 1)

def test_overlap_matches_redcat_column_m(self):
    rows = read_sheet(SNAPSHOT)
    art = [rows[3][c].text for c in "EGIK"]              # артефакт, вбитый в таблицу: L G E B
    self.assertEqual(art, ["L", "G", "E", "B"])
    expected = {rows[r]["C"].text: int(float(rows[r]["M"].text)) for r in rows if r >= 6 and rows[r].get("C") and rows[r]["C"].text}
    heroes = parse_heroes(SNAPSHOT)[0]
    self.assertEqual({h.name: overlap(art, h.letters) for h in heroes}, expected)   # 209 из 209

def test_score_table(self):
    h = lambda skills, multi=0, oc=False, ec=False, oa=False, ea=False: Hero("x", "f", tuple("ABCD"), skills, multi, oc, ec, oa, ea)
    self.assertEqual(score(h(("mass", "mass", "single", None)), ArtType.MASS), 2)
    self.assertEqual(score(h(("single", None, None, None), multi=2), ArtType.MULTI), 2)
    self.assertEqual(score(h(("single", "single", "single", None)), ArtType.SINGLE), 3)
    self.assertEqual(score(h(("single", "single", "mass", None)), ArtType.SINGLE), 0)
    self.assertEqual(score(h((None,) * 4, oc=True, ec=True), ArtType.COUNTER), 2)
    self.assertEqual(score(h((None,) * 4, ec=True), ArtType.COUNTER), 1)
    self.assertEqual(score(h((None,) * 4, ea=True), ArtType.ASSIST), 1)
    self.assertEqual(score(h((None,) * 4), ArtType.ASSIST), 0)

def test_pick_lgeb_mass(self):
    r = pick(HEROES, "LGEB", ArtType.MASS, random.Random(1))
    self.assertEqual({t: len(r.tiers[t]) for t in TIERS}, {4: 1, 3: 7, 2: 50})
    self.assertEqual([h.name for h in r.shown(4)], ["Древерад"])
    for t in TIERS:                                       # отсортировано по оценке
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
    orders = {tuple(h.name for h in pick(HEROES, "LGEB", ArtType.COUNTER, random.Random(s)).reforge) for s in range(10)}
    self.assertGreater(len(orders), 1)                    # 20 героев делят высшую оценку

def test_reforge_empty_when_no_positive_score(self):
    heroes = [Hero(n, "f", tuple("ABCD"), ("mass",) * 4, 0, False, False, False, False) for n in "xyz"]
    self.assertEqual(pick(heroes, "EFGH", ArtType.COUNTER, random.Random(0)).reforge, [])

def test_parse_letters(self):                              # Review Focus №1
    self.assertEqual(parse_letters("L g е B"), ("L", "G", "E", "B"))   # «е» кириллическая
    self.assertEqual(parse_letters("/pick lgeb"), ("L", "G", "E", "B"))
    self.assertEqual(parse_letters("АВСК"), ("A", "B", "C", "K"))      # всё кириллицей
    self.assertIsNone(parse_letters("LGE"))
    self.assertIsNone(parse_letters("LGEZ"))
    self.assertIsNone(parse_letters("привет"))

def test_pick_rejects_bad_letters(self):
    with self.assertRaises(ValueError):
        pick(HEROES, "LGEZ", ArtType.MASS, random.Random(0))
```

- [ ] **Step 2: Запустить** — FAIL.

- [ ] **Step 3: Реализовать `bot/aom_bot/picker.py`.**
  - `score` — по таблице из спеки.
  - `pick`: каждому герою один раз за вызов присваивается `rng.random()`. Ключ сортировки `(-score, этот_random)` общий для групп и для блока 2. Группы — герои с `overlap == t`. Блок 2 — герои, не попавшие ни в один `shown(t)`, с `score > 0`, первые `REFORGE_COUNT`.
  - `parse_letters`: срезать префикс `/pick`, убрать пробелы, перевести в верхний регистр. Кириллические двойники отобразить в латиницу: `А→A, В→B, С→C, Е→E, Н→H, К→K`. Принять ровно 4 символа из `A`–`L`.

- [ ] **Step 4: Запустить** — PASS.

- [ ] **Step 5: Commit** `git commit -m "bot: hero picker"`

### Task 3: Текст ответа и кнопки

**Files:**
- Create: `bot/aom_bot/render.py`, `bot/tests/test_render.py`

**Interfaces:**
- Consumes: `PickResult`, `ArtType`, `TIERS`, `Hero` (Task 1–2).
- Produces:
  - `hero_line(h: Hero) -> str` → `"Древерад (B G E L)"`
  - `format_type_prompt(letters: Sequence[str]) -> str`
  - `format_pick(r: PickResult, stale_since: datetime | None = None) -> str`
  - `format_tier_full(r: PickResult, tier: int) -> list[str]` — уже порезано на сообщения.
  - `chunk_lines(lines: list[str], limit: int = 4096) -> list[str]`
  - `keyboard(r: PickResult | None) -> dict` — `{"inline_keyboard": [...]}`; callback_data `"t:<ArtType.value>"` и `"all:<tier>"`.
  - Константы-тексты: `HELP`, `UNAVAILABLE`, `SESSION_GONE`, `NOT_ADMIN`.

- [ ] **Step 1: Написать падающие тесты** на синтетическом `RESULT = PickResult(("L","G","E","B"), ArtType.MASS, tiers={4: [], 3: [Теон (B E D G), Тан'Арг (B G L L)], 2: [Артус (G F E A), Люциус (E E B A), Врея (D B B E)] + 47 героев «X1»…«X47»}, reforge=[])`:

```python
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

def test_stale_note(self):
    text = format_pick(RESULT, stale_since=datetime(2026, 10, 25, 14, 5))
    self.assertTrue(text.endswith("\n\n⚠️ Данные от 25.10.2026 14:05, обновить не удалось."))

def test_keyboard(self):
    kb = keyboard(RESULT)["inline_keyboard"]
    self.assertEqual([b["callback_data"] for row in kb[:2] for b in row],
                     ["t:mass", "t:single", "t:multi", "t:counter", "t:assist"])
    self.assertEqual([(b["text"], b["callback_data"]) for b in kb[2]],
                     [("Все 3/4 (2)", "all:3"), ("Все 2/4 (50)", "all:2")])   # пустая 4/4 — без кнопки
    self.assertEqual(len(keyboard(None)["inline_keyboard"]), 2)               # до выбора типа — только типы

def test_tier_full_and_chunks(self):
    msgs = format_tier_full(RESULT, 2)
    self.assertTrue(msgs[0].startswith("2/4 · Массовая · все 50\n1. Артус (G F E A)"))
    self.assertEqual(chunk_lines(["aaaa", "bbbb", "cc"], limit=9), ["aaaa\nbbbb", "cc"])
```

- [ ] **Step 2: Запустить** — FAIL.

- [ ] **Step 3: Реализовать `bot/aom_bot/render.py`** по формату из тестов.
  - Кнопки типов: две строки, 3 + 2 кнопки, подписи `ArtType.label`.
  - `format_type_prompt` → `"Артефакт: L G E B\nВыбери тип артефакта по его главному свойству:"`.
  - `HELP` объясняет, что прислать: скриншот (когда подключится шаг 1) или 4 буквы, например `L G E B`.
  - `UNAVAILABLE` = `"Таблица героев сейчас недоступна, попробуй позже."`
  - `SESSION_GONE` = `"Это сообщение устарело, пришли скриншот или буквы заново."`

- [ ] **Step 4: Запустить** — PASS.

- [ ] **Step 5: Commit** `git commit -m "bot: render pick result"`

### Task 4: Источник данных с кэшем

**Files:**
- Create: `bot/aom_bot/source.py`, `bot/tests/test_source.py`

**Interfaces:**
- Consumes: `parse_heroes`, `SheetError`, `Hero` (Task 1).
- Produces:
  - `EXPORT_URL` (из Global Constraints)
  - `class SourceUnavailable(Exception)`
  - `@dataclass(frozen=True) class Snapshot: heroes: list[Hero]; loaded_at: datetime; stale: bool`
  - `fetch_export(url: str = EXPORT_URL, timeout: float = 30) -> bytes`
  - `class HeroSource(cache_path: Path, fetch: Callable[[], bytes] = fetch_export, clock: Callable[[], datetime] = datetime.now, max_age: timedelta = timedelta(hours=6), retry_after: timedelta = timedelta(minutes=10))` с методами `get() -> Snapshot` и `refresh() -> Snapshot`.

- [ ] **Step 1: Написать падающие тесты** (fake `fetch` — список ответов/исключений, fake `clock`, `cache_path` во временной папке `tempfile.TemporaryDirectory`):

```python
def test_fresh_fetch_writes_cache(self):        # SNAPSHOT → 209 героев, stale=False, файл кэша создан
def test_within_max_age_no_refetch(self):       # второй get() через 1 ч — fetch вызван 1 раз
def test_html_instead_of_xlsx_serves_cache(self):   # Review Focus №4
    # 1-й fetch SNAPSHOT; через 7 ч fetch возвращает b"<html>..." → get().stale is True, героев 209,
    # loaded_at == время первой загрузки
def test_network_error_after_restart_uses_disk_cache(self):
    # новый HeroSource на тот же cache_path, fetch бросает URLError → stale=True, loaded_at == mtime файла
def test_no_cache_no_network_raises(self):      # SourceUnavailable
def test_retry_after_limits_attempts(self):     # после неудачи следующий get() в пределах 10 мин не зовёт fetch
def test_refresh_forces_fetch(self):            # refresh() через 1 мин после успешной загрузки — fetch вызван снова
def test_zero_heroes_is_failure(self):          # xlsx без героев (make_xlsx({})) → старая копия, stale=True
```

- [ ] **Step 2: Запустить** — FAIL.

- [ ] **Step 3: Реализовать `bot/aom_bot/source.py`.**
  - Неудачей считается: исключение `fetch`, `SheetError` или 0 героев.
  - Предупреждения `parse_heroes` идут в `logging.warning`.
  - Кэш пишется атомарно: временный файл рядом с кэшем, затем `os.replace`.
  - Копия с диска грузится только когда в памяти пусто; её `loaded_at` = mtime файла.
  - `refresh()` игнорирует `max_age` и `retry_after`. При неудаче возвращает протухший снимок или бросает `SourceUnavailable`.

- [ ] **Step 4: Запустить** — PASS.

- [ ] **Step 5: Commit** `git commit -m "bot: hero source with cache"`

### Task 5: Telegram-бот

**Files:**
- Create: `bot/aom_bot/app.py`, `bot/aom_bot/__main__.py`, `bot/tests/test_app.py`, `bot/README.md`

**Interfaces:**
- Consumes: всё из Task 1–4.
- Produces:
  - `class TelegramError(RuntimeError)` с полем `description: str`
  - `class TelegramApi(token: str)` с методом `call(method: str, **params) -> Any` (POST JSON body, `ok=false` → `TelegramError`)
  - `class Bot(api, source: HeroSource, admin_ids: frozenset[int], rng_factory: Callable[[], random.Random] = random.Random, max_sessions: int = 1000)` с методами:
    - `handle_update(upd: dict) -> None`
    - `offer_types(chat_id: int, letters: Sequence[str], reply_to: int | None = None) -> None` — вызывается после распознавания (Task 6) и при вводе букв текстом
  - `run(bot: Bot, api: TelegramApi) -> None` — цикл `getUpdates` как в спайке, ошибки одного апдейта логируются и не роняют цикл.
  - `python3 -m aom_bot <token_file> <cache_dir>` (запуск из `bot/`); админы из `AOM_ADMIN_IDS`.

- [ ] **Step 1: Написать падающие тесты** с `FakeApi` и `FakeSource`. `FakeApi` пишет `(method, params)` в список и на `sendMessage` отдаёт `{"message_id": n}`. Ему можно задать исключение для конкретного метода. `FakeSource` отдаёт `Snapshot` из снимка или бросает `SourceUnavailable`. Нумерация `message_id` в `FakeApi` начинается с 1. Хелперы: `msg(text, chat=5, user=42, message_id=10)` собирает апдейт с `message`, `cb(data, message_id, chat=5, user=42)` — апдейт с `callback_query` и `id="q"`. `Bot` создаётся с `rng_factory=lambda: random.Random(1)`.

```python
def test_letters_text_offers_types(self):
    bot.handle_update(msg("l g е b"))
    m, p = api.calls[-1]
    self.assertEqual((m, p["text"]), ("sendMessage", format_type_prompt("LGEB")))
    self.assertEqual(p["reply_markup"], keyboard(None))

def test_type_press_edits_message(self):
    bot.handle_update(msg("LGEB")); bot.handle_update(cb("t:mass", message_id=1))
    m, p = [c for c in api.calls if c[0] == "editMessageText"][-1]
    self.assertTrue(p["text"].startswith("Артефакт: L G E B · тип: Массовая"))
    self.assertIn("answerCallbackQuery", [c[0] for c in api.calls])

def test_show_all_uses_same_order(self):
    bot.handle_update(msg("LGEB")); bot.handle_update(cb("t:mass", message_id=1)); bot.handle_update(cb("all:2", message_id=1))
    edited = [c for c in api.calls if c[0] == "editMessageText"][-1][1]["text"]
    full = [c for c in api.calls if c[0] == "sendMessage"][-1][1]["text"]
    top3 = edited.split("2/4 — ")[1].split("\n")[0].split(", ")
    self.assertEqual([line.split(". ", 1)[1] for line in full.split("\n")[1:4]], top3)

def test_stale_session(self):                     # Review Focus №3
    bot.handle_update(cb("t:mass", message_id=999))
    self.assertEqual(api.calls[-1], ("answerCallbackQuery", {"callback_query_id": "q", "text": SESSION_GONE}))

def test_message_not_modified_is_ignored(self):   # Review Focus №5
    api.fail("editMessageText", TelegramError("Bad Request: message is not modified"))
    bot.handle_update(msg("LGEB")); bot.handle_update(cb("t:mass", message_id=1))   # не бросает

def test_source_unavailable(self):                # ответ UNAVAILABLE на нажатие типа
def test_stale_snapshot_adds_note(self):          # текст заканчивается строкой «⚠️ Данные от ...»
def test_refresh_admin_only(self):                # /refresh от id не из admin_ids → NOT_ADMIN; от админа → «Загружено 209 героев, данные от …»
def test_offer_types_hook(self):                  # offer_types(5, "LGEB", reply_to=7) шлёт тот же промпт с reply_to_message_id=7
def test_other_text_gets_help(self):              # "привет" → HELP
```

- [ ] **Step 2: Запустить** — FAIL.

- [ ] **Step 3: Реализовать `bot/aom_bot/app.py` и `__main__.py`.**
  - Сессии: `OrderedDict[(chat_id, message_id)] → (letters, PickResult | None)`, LRU на `max_sessions`.
  - Нажатие типа: новый `rng_factory()`, затем `pick(...)`. Результат кладётся в сессию, сообщение правится через `editMessageText` с `format_pick` и `keyboard(result)`.
  - `all:<tier>` шлёт `format_tier_full` новыми сообщениями из сохранённого результата.
  - `answerCallbackQuery` вызывается на каждый callback.
  - `TelegramError`, где в `description` есть `"message is not modified"`, — игнорировать.
  - `reply_markup` передавать как объект в JSON-теле.
  - `bot/README.md`: запуск, переменные, откуда данные, что `offer_types` — вход для шага 1.

- [ ] **Step 4: Запустить** весь набор `python3 -m unittest discover -s bot/tests -t bot -v` — PASS.

- [ ] **Step 5: Commit** `git commit -m "bot: telegram wiring for hero picker"`

### Task 6: Распознавание в том же боте

**Files:**
- Create: `bot/aom_bot/recognition.py`, `bot/aom_bot/data/ingame_refs.pkl`, `bot/requirements.txt`, `bot/tests/test_recognition.py`, `bot/tests/data/screens/` (3 скриншота из `/Users/den/prj/aom/example/artefact/`)
- Modify: `bot/aom_bot/app.py`, `bot/aom_bot/__main__.py`, `bot/tests/test_app.py`, `bot/README.md`

**Interfaces:**
- Consumes: `Bot.offer_types`, `TelegramApi` (Task 5).
- Produces:
  - `class Recognizer(runes_dir: Path, ingame_refs: Path | None)` с методами `letters(image_path: Path) -> tuple[str, str, str, str] | None` (без суффикса `(dim)`, слева направо) и `strip_png(letters: Sequence[str]) -> bytes` (картинка 4 значков из `Runes/` с буквами под ними, как в спайке).
  - `Bot(..., recognizer: Recognizer | None = None, save_dir: Path | None = None)`: фото или картинка-документ в сообщении → скачать → `recognizer.letters`. Если `None` — ответ `NOT_FOUND` («Не нашёл 4 значка созвездий. Пришли скриншот карточки артефакта, лучше файлом (без сжатия).»). Иначе — `sendPhoto` с картинкой значков и подписью `«Созвездия артефакта: L G E B»`, затем `offer_types(chat, letters, reply_to=message_id)`.
  - Если задан `save_dir`, скриншот и строка в `log.jsonl` сохраняются, как в спайке (поля `file`, `user`, `kind`, `recognized`).
  - `python3 -m aom_bot <token_file> <cache_dir> [--runes DIR] [--refs FILE] [--save DIR]`; без `--runes` бот работает только с буквами текстом.

- [ ] **Step 1: Окружение.** `python3 -m venv bot/.venv && bot/.venv/bin/pip install opencv-python-headless numpy`, затем `pip freeze` с `opencv`/`numpy` → `bot/requirements.txt`. В `.gitignore` добавить `bot/.venv/` и `.superpowers/`.
- [ ] **Step 2: Написать падающие тесты.**
  - `test_recognition.py`: `Recognizer(REPO/"Runes", DATA/"ingame_refs.pkl").letters(...)` на трёх скриншотах. Сравнение мультимножеством, как в спайке: `photo_2026-10-25_10-16-41.jpg` → `HLJK`, `photo_2026-10-25_10-16-41 (2).jpg` → `BDDH`, `photo_2026-10-25_10-16-42.jpg` → `KLDB`. `letters(картинка без значков)` → `None`. `strip_png("LGEB")` начинается с PNG-сигнатуры.
  - `test_app.py`: `FakeRecognizer` возвращает `("H","L","J","K")` или `None`; `FakeApi.getFile` и скачивание подменяются.
    - Фото → по порядку `sendPhoto` (подпись `«Созвездия артефакта: H L J K»`), затем `sendMessage` с `format_type_prompt("HLJK")` и `keyboard(None)`.
    - `None` → `NOT_FOUND`.
    - С `save_dir` появляется строка в `log.jsonl`.
- [ ] **Step 3: Запустить** `bot/.venv/bin/python -m unittest discover -s bot/tests -t bot -v` — новые тесты FAIL.
- [ ] **Step 4: Реализовать.**
  - Перенести `recognize2.py` из `/Users/den/.claude/jobs/7ba0ece8/tmp/spike/` в `recognition.py` без изменения алгоритма. Глобальные `HEX`/`INGAME` становятся полями `Recognizer`; отладочный вывод и `__main__` убрать.
  - `ingame_refs.pkl` скопировать в `bot/aom_bot/data/`.
  - `strip_png` — функция `runes_strip` из `collector_bot.py`.
  - Скачивание файла по `getFile` и `sendPhoto` multipart — из `collector_bot.py`, методами `TelegramApi`.
- [ ] **Step 5: Запустить** — PASS (весь набор под `bot/.venv`, а ядро — ещё и системным `python3`, где тесты распознавания пропускаются).
- [ ] **Step 6: Commit** `git commit -m "bot: recognition and picker in one bot"`

### Task 7: Живая проверка

**Files:** нет новых.

- [ ] **Step 1: Остановить спайк-бот шага 1.** Он слушает тот же токен, а два `getUpdates` на одном токене дают 409 Conflict. Объединённый бот заменяет его, включая сохранение скриншотов. **Перед остановкой спросить пользователя:** спайк принадлежит другой сессии.
- [ ] **Step 2: Запустить** из `bot/`: `AOM_ADMIN_IDS=<id> .venv/bin/python -m aom_bot /Users/den/.config/aom-bot/token ~/.cache/aom-bot --runes ../Runes --refs aom_bot/data/ingame_refs.pkl --save /Users/den/prj/aom/example/incoming`. Ожидается лог с именем бота и загрузкой 209+ героев.
- [ ] **Step 3: Прогнать в Telegram.** Скриншот артефакта → картинка значков с буквами → кнопки типа → «Массовая» → «Все 2/4 (N)» → «Контратака» на том же сообщении. Отдельно проверить ввод `L G E B` текстом.
- [ ] **Step 4: Записать результат проверки в README.**
