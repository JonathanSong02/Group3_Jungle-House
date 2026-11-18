"""Explicit, reviewable KB image backfill. Dry-run by default. Never imports app.

python tools/backfill_image_index.py            # counts only, no writes/model
python tools/backfill_image_index.py --apply    # metadata only, then worker may index
python tools/backfill_image_index.py --encode   # encode pending records (requires --apply)
Run only against an explicitly selected isolated/local database until approved.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from db_helper import get_db_connection
from image_index_service import article_images, process_pending, published, sync_article


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--encode", action="store_true")
    args = parser.parse_args()
    if args.encode and not args.apply:
        parser.error("--encode requires --apply")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM wiki_article ORDER BY article_id")
        rows = cursor.fetchall()
        count = sum(len(article_images(row)) for row in rows if published(row))
        print({"published_images": count, "apply": args.apply})
        if args.apply:
            for row in rows:
                sync_article(cursor, row["article_id"])
            conn.commit()
    finally:
        cursor.close()
        conn.close()
    if args.encode:
        while True:
            result = process_pending()
            print(result)
            if result["processed"] < 16 or result["indexed"] == 0:
                break


if __name__ == "__main__":
    main()
