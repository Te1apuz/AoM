"""python -m aom_bot <token_file> <cache_dir>"""
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
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    admins = frozenset(int(x) for x in os.environ.get("AOM_ADMIN_IDS", "").split(",") if x.strip())
    source = HeroSource(args.cache_dir / "heroes.xlsx")
    try:
        snap = source.get()
        logging.info("heroes: %d, loaded %s%s", len(snap.heroes), snap.loaded_at, " (stale)" if snap.stale else "")
    except SourceUnavailable as e:
        logging.warning("hero sheet unavailable at start: %s", e)

    api = TelegramApi(args.token_file.read_text().strip())
    run(Bot(api, source, admins), api)


if __name__ == "__main__":
    main()
