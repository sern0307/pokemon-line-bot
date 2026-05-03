"""
毎日の定時情報収集スクリプト
全300件をスクレイピングして SQLite DB に保存する。
LINE通知は行わない。
"""
import os
from datetime import datetime, timezone, timedelta

from scraper import scrape_all
from db import init_db, save_rankings

RULE   = int(os.environ.get("RULE", "0"))
SEASON = os.environ.get("SEASON")

JST = timezone(timedelta(hours=9))


def main():
    season_int = int(SEASON) if SEASON else None
    now = datetime.now(JST)
    print(f"[{now.isoformat()}] 収集開始 rule={RULE}")

    init_db()

    print("全300件を取得中...")
    trainers, site_updated_at = scrape_all(season=season_int, rule=RULE)
    print(f"取得完了: {len(trainers)}件  サイト更新日時: {site_updated_at}")

    saved = save_rankings(trainers, rule=RULE, site_updated_at=site_updated_at)
    print(f"DB保存完了: {saved}件")


if __name__ == "__main__":
    main()
