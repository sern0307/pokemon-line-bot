"""
LINE Messaging API を使って Push Message を送信する
"""
import os
import requests


def send_line_push(message: str, user_id: str = None, channel_token: str = None) -> None:
    """
    LINE Push Message を送信する。

    環境変数:
        LINE_CHANNEL_ACCESS_TOKEN: チャンネルアクセストークン
        LINE_USER_ID: 送信先のユーザーID
    """
    token = channel_token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    uid = user_id or os.environ.get("LINE_USER_ID")

    if not token:
        raise ValueError("LINE_CHANNEL_ACCESS_TOKEN が設定されていません")
    if not uid:
        raise ValueError("LINE_USER_ID が設定されていません")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "to": uid,
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ],
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(
            f"LINE送信失敗 [{resp.status_code}]: {resp.text}"
        )
