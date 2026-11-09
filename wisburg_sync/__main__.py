from __future__ import annotations

import argparse
from pathlib import Path

from wisburg_sync.config import BACKFILL_DAYS
from wisburg_sync.sync import DEFAULT_DB, sync


def main() -> None:
    parser = argparse.ArgumentParser(description="把智堡来源同步到本地 SQLite")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB))
    parser.add_argument("--backfill-days", type=int, default=BACKFILL_DAYS)
    args = parser.parse_args()
    raise SystemExit(sync(db_path=Path(args.db), backfill_days=args.backfill_days))


if __name__ == "__main__":
    main()
