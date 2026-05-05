"""
毎日の定時情報収集スクリプト
シングル・ダブル両方の全300件をスクレイピングして SQLite DB に保存する。
LINE通知は行わない。
"""
import os
import time
from datetime import datetime, timezone, timedelta

from scraper import scrape_all, get_latest_season
from db import init_db, save_rankings

SEASON     = os.environ.get("SEASON")  # 空 = 最新シーズン自動検出
RULE_DELAY = 3.0  # ルール間のウェイト（秒）

JST = timezone(timedelta(hours=9))
RULES = {0: "シングルバトル", 1: "ダブルバトル"}


def collect_rule(rule: int, season_int: int | None) -> None:
    label = RULES[rule]

    if season_int is None:
        season_int, season_label = get_latest_season(rule=rule)
        print(f"  最新シーズン自動検出: {season_int}（{season_label}）")

    print(f"  全300件を取得中...")
    trainers, site_updated_at = scrape_all(season=season_int, rule=rule)
    print(f"  取得完了: {len(trainers)}件  サイト更新日時: {site_updated_at}")

    saved = save_rankings(trainers, rule=rule, site_updated_at=site_updated_at)
    print(f"  DB保存完了: {saved}件")


def main():
    now = datetime.now(JST)
    print(f"[{now.isoformat()}] 収集開始")

    init_db()

    season_int = int(SEASON) if SEASON else None

    for rule, label in RULES.items():
        print(f"\n--- {label} (rule={rule}) ---")
        collect_rule(rule, season_int)
        if rule < max(RULES):
            time.sleep(RULE_DELAY)

    print("\n完了")


if __name__ == "__main__":
    main()
