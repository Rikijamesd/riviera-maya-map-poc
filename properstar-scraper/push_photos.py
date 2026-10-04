"""Write the full photo lists from collect_photos.py into resale_listings.pictures.

Only touches rows where the new list is longer than what's stored (the parse.bot rows stuck at
5), and only the pictures column. Small batches with a pause between them, so the Micro
instance's burst credits aren't drained.

    python push_photos.py              # dry run: counts only
    python push_photos.py --apply
"""
from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rightmove-scraper"))
from rightmove import connect  # noqa: E402  (same tlrm database and .env.local)

BATCH = 1000
PAUSE_S = 3


def main() -> None:
    apply = "--apply" in sys.argv
    photos: dict[int, list[str]] = {}
    for f in sorted(glob.glob("photos/*.json")):
        with open(f, encoding="utf-8") as fh:
            for k, v in json.load(fh).items():
                if len(v) > len(photos.get(int(k), [])):
                    photos[int(k)] = v
    print(f"{len(photos)} listings in photos/*.json")

    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("set statement_timeout = '60s'")
    ids = list(photos)
    longer = 0
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        rows = [(lid, json.dumps(photos[lid])) for lid in chunk]
        if apply:
            execute_values(cur, """
                update resale_listings r set pictures = v.pics::jsonb
                from (values %s) as v(id, pics)
                where r.id = v.id
                  and jsonb_array_length(v.pics::jsonb) > coalesce(jsonb_array_length(r.pictures), 0)
            """, rows, page_size=BATCH)
            longer += cur.rowcount
            time.sleep(PAUSE_S)
        else:
            execute_values(cur, """
                select count(*) from resale_listings r
                join (values %s) as v(id, pics) on r.id = v.id
                where jsonb_array_length(v.pics::jsonb) > coalesce(jsonb_array_length(r.pictures), 0)
            """, rows, page_size=BATCH)
            longer += cur.fetchone()[0]
        print(f"  {min(i + BATCH, len(ids))}/{len(ids)}  {'updated' if apply else 'would update'} {longer}", flush=True)
    print(f"\n{'updated' if apply else 'would update'} {longer} listings")


if __name__ == "__main__":
    main()
