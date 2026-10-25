"""python -m aom_bot <token_file> <cache_dir> [--runes DIR] [--refs FILE] [--save DIR]"""
import argparse
import logging
import os
from pathlib import Path

from .app import Bot, TelegramApi, run
from .source import HeroSource, SourceUnavailable


def main() -> None:
    p = argparse.ArgumentParser(prog="aom_bot", description="AoM artifact bot: recognition + hero picker")
    p.add_argument("token_file", type=Path)
    p.add_argument("cache_dir", type=Path)
    p.add_argument("--runes", type=Path, help="Runes/ icons; enables screenshot recognition (needs OpenCV)")
    p.add_argument("--refs", type=Path, help="in-game reference crops (ingame_refs.pkl)")
    p.add_argument("--save", type=Path, help="keep incoming screenshots and log.jsonl here")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    admins = frozenset(int(x) for x in os.environ.get("AOM_ADMIN_IDS", "").split(",") if x.strip())
    source = HeroSource(args.cache_dir / "heroes.xlsx")
    try:
        snap = source.get()
        logging.info("heroes: %d, loaded %s%s", len(snap.heroes), snap.loaded_at, " (stale)" if snap.stale else "")
    except SourceUnavailable as e:
        logging.warning("hero sheet unavailable at start: %s", e)

    recognizer = None
    if args.runes:
        from .recognition import Recognizer  # OpenCV only when recognition is on
        recognizer = Recognizer(args.runes, args.refs)
    else:
        logging.info("no --runes: screenshots are not recognized, letters as text only")

    api = TelegramApi(args.token_file.read_text().strip())
    run(Bot(api, source, admins, recognizer=recognizer, save_dir=args.save), api)


if __name__ == "__main__":
    main()
