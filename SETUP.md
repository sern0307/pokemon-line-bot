# セットアップ手順

毎日1回、ジェミニの順位をLINEに通知するBOTです。  
GitHub Actions（無料）を使うのでサーバー不要です。

---

## 1. LINE Messaging API の準備

1. [LINE Developers Console](https://developers.line.biz/) にアクセス
2. **新規プロバイダー作成** → **Messaging API チャネル作成**
3. チャネル設定 → **Messaging API** タブを開く
4. 「チャンネルアクセストークン（長期）」を発行してコピー
5. 同ページ下部の **Your user ID** もコピー（`U` で始まる文字列）

---

## 2. GitHub リポジトリを作る

```bash
cd pokemon-line-bot
git init
git add .
git commit -m "初回コミット"
```

GitHub で新しいリポジトリを作成して push：

```bash
git remote add origin https://github.com/あなたのユーザー名/pokemon-line-bot.git
git push -u origin main
```

---

## 3. GitHub Secrets を設定

リポジトリの **Settings → Secrets and variables → Actions** を開く。

**Secrets（機密情報）:**

| 名前 | 値 |
|------|-----|
| `LINE_CHANNEL_ACCESS_TOKEN` | 手順1でコピーしたトークン |
| `LINE_USER_ID` | 手順1でコピーしたUser ID |

**Variables（設定値）:**

| 名前 | 値 |
|------|-----|
| `TRAINER_NAME` | `ジェミニ` |
| `RULE` | `0`（シングル） または `1`（ダブル） |

---

## 4. 動作確認

GitHub の **Actions タブ** を開き、  
「ポケモン順位 毎日LINE通知」ワークフローの  
**Run workflow** ボタンで手動実行できます。

---

## 5. 自動実行スケジュール

`.github/workflows/daily_notify.yml` の cron 設定：

```yaml
- cron: "0 23 * * *"  # 毎日 JST 08:00 に実行
```

変更したい場合は [crontab.guru](https://crontab.guru/) で確認してください。  
※ GitHub Actions の時刻は UTC です（JST = UTC+9）

---

## ローカルでテストする場合

```bash
pip install -r requirements.txt

# まおうで動作確認
python scraper.py まおう

# LINE送信テスト（要: .envファイルに設定）
set LINE_CHANNEL_ACCESS_TOKEN=your_token
set LINE_USER_ID=your_user_id
set TRAINER_NAME=ジェミニ
python main.py
```
