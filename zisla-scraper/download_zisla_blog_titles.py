"""
Scrapes the title + metadata (not body text) of every published blog article
on zisla.com/en/blog.

Deliberately excludes the article body: only title, URL, category, publish
date, and the short (~150-char) SEO meta description are collected. The full
article HTML lives in each item's "component" field and is not touched here -
downloading full article text at scale would mean reproducing Zisla's
copyrighted editorial writing, which is a different thing from collecting
factual/structured data (titles, dates, categories are not creative content).

Usage:
  python download_zisla_blog_titles.py
  python download_zisla_blog_titles.py --out "D:\\other\\path.xlsx"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from zisla_common import fetch_blog_articles, write_new_workbook


def build_rows(articles: list[dict]) -> list[dict]:
    rows = []
    for a in articles:
        en = (a.get("localized") or {}).get("en") or {}
        rows.append(
            {
                "Title": en.get("title"),
                "URL": f"https://www.zisla.com/en/blog{en.get('url')}",
                "Category": a.get("blogType"),
                "Published At": en.get("publishedAt"),
                "Created At": a.get("createdAt"),
                "Updated At": a.get("updatedAt"),
                "Meta Description": en.get("description"),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=r"G:\My Drive\zisla-tracker\zisla-blog-titles.xlsx")
    args = parser.parse_args()

    print("Fetching blog article list from zisla.com ...")
    articles = fetch_blog_articles()
    print(f"Total articles: {len(articles)}")

    rows = build_rows(articles)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing to workbook: {out_path}")
    write_new_workbook(out_path, "Blog Articles", rows)
    print(f"Saved {len(rows)} blog article titles to {out_path}")


if __name__ == "__main__":
    main()
