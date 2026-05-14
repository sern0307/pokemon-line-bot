"""
毎日の定時情報収集スクリプト
シングル・ダブル両方の全300件をスクレイピングして SQLite DB に保存する。

シーズン移行検出:
  サイトの最新シーズンがDBの最新シーズンと異なる場合、前シーズンの最終データを
  前回収集日に遡って上書き保存してから、新シーズンを収集する。
"""
import os
import time
from datetime import datetime, timezone, timedelta

from scraper import scrape_all, get_all_seasons
from db import init_db, save_rankings, get_latest_season_in_db

SEASON     = os.environ.get("SEASON")  # 空 = 最新シーズン自動検出
RULE_DELAY = 3.0  # ルール間のウェイト（秒）

JST = timezone(timedelta(hours=9))
RULES = {0: "シングルバトル", 1: "ダブルバトル"}


def _collect(season_int: int, season_label: str, rule: int,
             date: str | None = None,
             is_final: bool = False,
             replace_all: bool = False) -> None:
    """指定シーズンの全300件を取得してDBに保存する。"""
    kind = "最終結果" if is_final else "定時収集"
    print(f"  [{season_label}] {kind} 全300件を取得中...")
    trainers, site_updated_at = scrape_all(season=season_int, rule=rule)
    print(f"  取得完了: {len(trainers)}件  サイト更新日時: {site_updated_at}")
    saved = save_rankings(
        trainers, rule=rule, season=season_label,
        site_updated_at=site_updated_at,
        date=date, is_final=is_final, replace_all=replace_all,
    )
    label = f"日付={date}" if date else "今日"
    print(f"  DB保存完了: {saved}件 ({label}, is_final={is_final})")


def collect_rule(rule: int, forced_season_int: int | None) -> None:
    label = RULES[rule]

    # サイトの全シーズンを取得
    all_site_seasons = get_all_seasons(rule=rule)
    latest_site_int, latest_site_label = all_site_seasons[-1]

    if forced_season_int is not None:
        # 手動指定モード
        label_map = {s: l for s, l in all_site_seasons}
        target_label = label_map.get(forced_season_int, f"シーズン{forced_season_int}")
        print(f"  シーズン指定: {forced_season_int}（{target_label}）")
        _collect(forced_season_int, target_label, rule)
        return

    # 自動モード: シーズン移行チェック
    print(f"  最新シーズン: {latest_site_int}（{latest_site_label}）")
    db_info = get_latest_season_in_db(rule)

    if db_info:
        db_season_label, db_latest_date = db_info
        if db_season_label != latest_site_label:
            # ─── シーズン移行検出 ───
            print(f"  ⚡ シーズン移行検出: {db_season_label} → {latest_site_label}")
            prev_seasons = [(s, l) for s, l in all_site_seasons if l == db_season_label]
            if prev_seasons:
                prev_int, prev_label = prev_seasons[0]
                print(f"  [{prev_label}] 最終結果を {db_latest_date} に保存します（is_final=True）")
                _collect(prev_int, prev_label, rule,
                         date=db_latest_date, is_final=True, replace_all=True)
                time.sleep(2.0)  # サーバー負荷軽減
            else:
                print(f"  ※ 前シーズン ({db_season_label}) はサイトから削除済みのためスキップ")

    # 最新シーズンを収集（通常処理）
    _collect(latest_site_int, latest_site_label, rule)


def main():
    now = datetime.now(JST)
    print(f"[{now.isoformat()}] 収集開始")

    init_db()

    forced = int(SEASON) if SEASON else None

    for rule, label in RULES.items():
        print(f"\n--- {label} (rule={rule}) ---")
        collect_rule(rule, forced)
        if rule < max(RULES):
            time.sleep(RULE_DELAY)

    print("\n完了")


if __name__ == "__main__":
    main()
