"""
毎日の定時情報収集スクリプト
シングル・ダブル両方の全300件をスクレイピングして SQLite DB に保存する。

環境変数:
  SEASON       : 通常収集するシーズン番号（空 = 最新自動検出）
  FINAL_SEASON : 最終結果として保存するシーズン番号（指定時は最終結果モード）
  FINAL_DATE   : 最終結果を保存する日付 YYYY-MM-DD（空 = DBの最終定時収集日を自動使用）

シーズン移行の自動検出:
  サイトの最新シーズンがDBの最新シーズンと異なる場合、前シーズンの最終データを
  前回収集日に遡って保存してから新シーズンを収集する。
"""
import os
import time
from datetime import datetime, timezone, timedelta

from scraper import scrape_all, get_all_seasons
from db import init_db, save_rankings, get_latest_season_in_db

SEASON       = os.environ.get("SEASON", "").strip()
FINAL_SEASON = os.environ.get("FINAL_SEASON", "").strip()
FINAL_DATE   = os.environ.get("FINAL_DATE", "").strip()
RULE_DELAY   = 3.0

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
    date_label = f"日付={date}" if date else "今日"
    print(f"  DB保存完了: {saved}件 ({date_label}, is_final={is_final})")


def collect_final(final_season_int: int, target_date: str | None, rule: int) -> None:
    """指定シーズンの最終結果を手動収集する。"""
    all_site_seasons = get_all_seasons(rule=rule)
    label_map = {s: l for s, l in all_site_seasons}
    season_label = label_map.get(final_season_int, f"シーズン{final_season_int}")

    # 保存先日付: 明示指定 > DBの最終定時収集日 > エラー
    if target_date:
        save_date = target_date
        print(f"  保存先日付（指定）: {save_date}")
    else:
        db_info = get_latest_season_in_db(rule)
        # 指定シーズンの最終定時収集日をDBから探す
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent / "data" / "rankings.db"
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT MAX(date) FROM rankings WHERE rule=? AND season=? AND is_final=0",
            (rule, season_label),
        ).fetchone()
        conn.close()
        save_date = row[0] if row and row[0] else None

        if not save_date:
            print(f"  ⚠ 保存先日付が特定できません。FINAL_DATE を指定してください。")
            return
        print(f"  保存先日付（自動）: {save_date}")

    print(f"  ⚡ 最終結果モード: {season_label} → {save_date} に保存")
    _collect(final_season_int, season_label, rule,
             date=save_date, is_final=True, replace_all=True)


def collect_rule(rule: int, forced_season_int: int | None) -> None:
    all_site_seasons = get_all_seasons(rule=rule)
    latest_site_int, latest_site_label = all_site_seasons[-1]

    if forced_season_int is not None:
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
            print(f"  ⚡ シーズン移行検出: {db_season_label} → {latest_site_label}")
            prev_seasons = [(s, l) for s, l in all_site_seasons if l == db_season_label]
            if prev_seasons:
                prev_int, prev_label = prev_seasons[0]
                print(f"  [{prev_label}] 最終結果を {db_latest_date} に保存します")
                _collect(prev_int, prev_label, rule,
                         date=db_latest_date, is_final=True, replace_all=True)
                time.sleep(2.0)
            else:
                print(f"  ※ 前シーズン ({db_season_label}) はサイトから削除済みのためスキップ")

    _collect(latest_site_int, latest_site_label, rule)


def main():
    now = datetime.now(JST)
    print(f"[{now.isoformat()}] 収集開始")

    init_db()

    # ── 最終結果モード（FINAL_SEASON が指定されている場合） ──
    if FINAL_SEASON:
        final_int = int(FINAL_SEASON)
        date_override = FINAL_DATE or None
        print(f"\n★ 最終結果モードで実行 (FINAL_SEASON={final_int}, FINAL_DATE={date_override or '自動'})")
        for rule, label in RULES.items():
            print(f"\n--- {label} (rule={rule}) ---")
            collect_final(final_int, date_override, rule)
            if rule < max(RULES):
                time.sleep(RULE_DELAY)
        print("\n完了（最終結果モード）")
        return

    # ── 通常収集モード ──
    forced = int(SEASON) if SEASON else None

    for rule, label in RULES.items():
        print(f"\n--- {label} (rule={rule}) ---")
        collect_rule(rule, forced)
        if rule < max(RULES):
            time.sleep(RULE_DELAY)

    print("\n完了")


if __name__ == "__main__":
    main()
