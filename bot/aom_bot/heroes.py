"""Heroes from RedCat's «Артефакты AoM» xlsx export.

Skill types live only in cell fill colours, so the sheet is read from the raw
xlsx (styles included) with the standard library.
"""
import io
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

MASS_RGB = "FF00FF00"
SINGLE_RGB = "FFFF9900"
FIRST_HERO_ROW = 6
LETTER_COLS = "FHJL"
SKILL_COLS = "NOPQ"
VALID_LETTERS = set("ABCDEFGHIJKL")


class SheetError(ValueError):
    """The bytes are not a readable RedCat xlsx."""


@dataclass(frozen=True)
class Cell:
    text: str
    fill: str | None


@dataclass(frozen=True)
class Hero:
    name: str
    faction: str
    letters: tuple[str, str, str, str]
    skills: tuple[str | None, str | None, str | None, str | None]  # "mass" / "single" / None
    multi: int
    own_counter: bool
    ext_counter: bool
    own_assist: bool
    ext_assist: bool


def read_sheet(xlsx: bytes, sheet_name: str = "Таблица") -> dict[int, dict[str, Cell]]:
    """Row number -> column letter -> cell."""
    try:
        z = zipfile.ZipFile(io.BytesIO(xlsx))
        shared = _shared_strings(z)
        fills = _cell_fills(z)
        sheet = ET.fromstring(z.read(_sheet_path(z, sheet_name)))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise SheetError(f"не удалось прочитать xlsx: {e}") from e

    rows: dict[int, dict[str, Cell]] = {}
    for row in sheet.iter(M + "row"):
        cells = {}
        for c in row.iter(M + "c"):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            style = int(c.get("s", 0))
            cells[col] = Cell(_cell_text(c, shared).strip(), fills[style] if style < len(fills) else None)
        rows[int(row.get("r"))] = cells
    return rows


def parse_heroes(xlsx: bytes) -> tuple[list[Hero], list[str]]:
    """Heroes in sheet order, plus warnings about rows that could not be read fully."""
    rows = read_sheet(xlsx)
    heroes, warnings = [], []
    empty = Cell("", None)
    for r in sorted(n for n in rows if n >= FIRST_HERO_ROW):
        get = lambda col: rows[r].get(col, empty)
        name = get("C").text
        if not name:
            continue
        letters = tuple(get(col).text for col in LETTER_COLS)
        if not all(letter in VALID_LETTERS for letter in letters):
            warnings.append(f"{name} (строка {r}): ожидалось 4 буквы, есть {' '.join(filter(None, letters)) or 'пусто'}")
            continue
        skills = []
        for k, col in enumerate(SKILL_COLS, 1):
            fill = get(col).fill
            if fill == MASS_RGB:
                skills.append("mass")
            elif fill == SINGLE_RGB:
                skills.append("single")
            else:
                if fill is not None:
                    warnings.append(f"{name}: навык {k}, неизвестный цвет {fill}")
                skills.append(None)
        flag = lambda col: bool(get(col).text) or get(col).fill is not None
        heroes.append(Hero(
            name=name,
            faction=get("B").text,
            letters=letters,
            skills=tuple(skills),
            multi=sum("Мульти" in get(col).text for col in SKILL_COLS),
            own_counter=flag("R"),
            ext_counter=flag("S"),
            own_assist=flag("T"),
            ext_assist=flag("U"),
        ))
    return heroes, warnings


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(M + "t")) for si in root.findall(M + "si")]


def _cell_fills(z: zipfile.ZipFile) -> list[str | None]:
    """Fill per cell style index (cellXfs): ARGB, or "theme:N" / "indexed:N" for non-rgb colours."""
    styles = ET.fromstring(z.read("xl/styles.xml"))
    fills = []
    for f in styles.find(M + "fills"):
        pattern = f.find(M + "patternFill")
        fg = pattern.find(M + "fgColor") if pattern is not None else None
        if fg is None or pattern.get("patternType", "none") == "none":
            fills.append(None)
        elif fg.get("rgb"):
            fills.append(fg.get("rgb"))
        else:  # a theme/indexed colour must not pass for "no fill": it gets the unknown-colour warning
            kind = next((k for k in ("theme", "indexed", "auto") if fg.get(k) is not None), "color")
            fills.append(f"{kind}:{fg.get(kind, '?')}")
    return [fills[int(xf.get("fillId", 0))] for xf in styles.find(M + "cellXfs")]


def _sheet_path(z: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rid = next((s.get(R_ID) for s in workbook.iter(M + "sheet") if s.get("name") == sheet_name), None)
    if rid is None:
        raise KeyError(f"нет листа «{sheet_name}»")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(rel.get("Target") for rel in rels.iter(PKG_REL + "Relationship") if rel.get("Id") == rid)
    return target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))


def _cell_text(c: ET.Element, shared: list[str]) -> str:
    kind = c.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in c.iter(M + "t"))
    v = c.find(M + "v")
    if v is None or v.text is None:
        return ""
    return shared[int(v.text)] if kind == "s" else v.text
