"""
LINE通知スクリプト
DB から指定トレーナーの今日の順位を読み取り、LINE に送信する。
スクレイピングは行わない（collect.py が事前に実行済みであること）。
"""
import os
from datetime import datetime, timezone, timedelta

from db import get_trainer_today, get_trainer_history
from line_notify import send_line_push

TRAINER_NAME = os.environ.get("TRAINER_NAME", "ジェミニ")
RULE         = int(os.environ.get("RULE", "0"))
TARGET_URL   = "https://champs.pokedb.tokyo/trainer/list"

JST = timezone(timedelta(hours=9))
RULE_LABEL = {0: "シングル", 1: "ダブル"}


def build_message(trainer_name: str, today: dict | None, history: list[dict]) -> str:
    now_str  = datetime.now(JST).strftime("%Y/%m/%d")
    rule_str = RULE_LABEL.get(RULE, "")

    if today is None:
        last = history[0] if history else None
        lines = [
            f"【{now_str} ランキング通知】",
            f"トレーナー: {trainer_name}（{rule_str}）",
            "",
            "📭 本日はランク外（300位以下）",
        ]
        if last:
            lines.append(f"📅 最終ランクイン: {last['date']}（{last['rank']}位）")
        lines.append(f"\n🔗 {TARGET_URL}?q={trainer_name}")
        return "\n".join(lines)

    rank    = today["rank"]
    rating  = today.get("rating")
    season  = today.get("season") or "最新"
    updated = today.get("site_updated_at") or ""

    medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 \
        else "🏆" if rank <= 10 else "⭐" if rank <= 50 else "📊"

    trend = ""
    if len(history) >= 2:
        prev_rank = history[1]["rank"]
        diff = prev_rank - rank
        if diff > 0:
            trend = f"  ▲{diff}"
        elif diff < 0:
            trend = f"  ▼{abs(diff)}"
        else:
            trend = "  →"

    lines = [
        f"【{now_str} ランキング通知】",
        f"トレーナー: {trainer_name}（{rule_str}）",
        "",
        f"{medal} 順位: {rank}位{trend}",
    ]
    if rating:
        lines.append(f"📈 レーティング: {rating:,.3f}")
    if season:
        lines.append(f"🗓  シーズン: {season}")
    if updated:
        lines.append(f"🕐 更新: {updated}")
    lines.append(f"\n🔗 {TARGET_URL}?q={trainer_name}")
    return "\n".join(lines)


def main():
    today_data = get_trainer_today(TRAINER_NAME, rule=RULE)
    history    = get_trainer_history(TRAINER_NAME, rule=RULE, limit=7)

    message = build_message(TRAINER_NAME, today_data, history)
    print("送信メッセージ:\n" + message)

    send_line_push(message)
    print("LINE送信成功")


if __name__ == "__main__":
    main()
