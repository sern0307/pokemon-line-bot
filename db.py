"""
SQLite によるランキングデータの蓄積・参照
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "rankings.db"
JST = timezone(timedelta(hours=9))


def init_db(db_path: Path = DB_PATH) -> None:
    """DBとテーブルを初期化する（冪等）。既存DBへのマイグレーションも実行。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _conn(db_path) as conn:
        # ── テーブル作成 ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rankings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT    NOT NULL,
                season          TEXT,
                rule            INTEGER NOT NULL DEFAULT 0,
                rank            INTEGER NOT NULL,
                trainer_name    TEXT    NOT NULL,
                rating          REAL,
                is_final        INTEGER NOT NULL DEFAULT 0,
                site_updated_at TEXT,
                scraped_at      TEXT    NOT NULL
            )
        """)

        # ── インデックス作成（is_final を含む新版） ──
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_rankings_main
                ON rankings(date, rule, rank, trainer_name, is_final)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_trainer_name
                ON rankings(trainer_name)
        """)

        # ── 既存DBへのカラム追加マイグレーション ──
        for stmt in [
            "ALTER TABLE rankings ADD COLUMN season TEXT",
            "ALTER TABLE rankings ADD COLUMN is_final INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                conn.execute(stmt)
            except Exception:
                pass  # カラムが既に存在する場合は無視

        # ── 旧 UNIQUE INDEX（is_final なし）を削除 ──
        # 旧インデックスが残っていると同日に定時・最終の両レコードが共存できない
        try:
            conn.execute("DROP INDEX IF EXISTS ux_date_rule_rank_trainer")
        except Exception:
            pass


@contextmanager
def _conn(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_rankings(
    trainers: list[dict],
    rule: int = 0,
    season: str | None = None,
    site_updated_at: str | None = None,
    date: str | None = None,
    is_final: bool = False,
    replace_all: bool = False,
    db_path: Path = DB_PATH,
) -> int:
    """
    スクレイピングしたランキングをDBに保存する。
    同日・同ルール・同順位・同 is_final のレコードは上書き（UPSERT）。

    Args:
        date:        保存日付を上書きしたい場合に指定（デフォルトは今日のJST日付）。
        is_final:    True = シーズン最終結果。False = 通常定時収集。
        replace_all: True にすると指定日付+ルール+is_final の既存レコードを全削除してから挿入。
    戻り値: 保存件数
    """
    now = datetime.now(JST)
    today = date or now.date().isoformat()
    is_final_int = 1 if is_final else 0

    rows = [
        (
            today, season, rule,
            t["rank"], t["trainer_name"], t.get("rating"),
            is_final_int, site_updated_at, now,
        )
        for t in trainers
    ]

    with _conn(db_path) as conn:
        if replace_all:
            conn.execute(
                "DELETE FROM rankings WHERE date=? AND rule=? AND is_final=?",
                (today, rule, is_final_int),
            )
        conn.executemany(
            """
            INSERT INTO rankings
                (date, season, rule, rank, trainer_name, rating,
                 is_final, site_updated_at, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, rule, rank, trainer_name, is_final) DO UPDATE SET
                rating          = excluded.rating,
                season          = excluded.season,
                site_updated_at = excluded.site_updated_at,
                scraped_at      = excluded.scraped_at
            """,
            rows,
        )

    return len(rows)


def get_latest_season_in_db(
    rule: int,
    db_path: Path = DB_PATH,
) -> tuple[str, str] | None:
    """
    DBの定時収集（is_final=0）に記録されている最新シーズン名とその最終収集日を返す。
    戻り値: (season_label, latest_date) または None
    """
    with _conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT season, MAX(date) AS latest_date
            FROM rankings
            WHERE rule=? AND is_final=0 AND season IS NOT NULL AND season != ''
            GROUP BY season
            ORDER BY latest_date DESC
            LIMIT 1
            """,
            (rule,),
        ).fetchone()
    return (row["season"], row["latest_date"]) if row else None


def get_trainer_history(
    trainer_name: str,
    rule: int = 0,
    limit: int = 30,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """トレーナーの過去N日分の順位履歴を返す（新しい日付順）。"""
    with _conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT date, rank, rating, season, is_final
            FROM rankings
            WHERE trainer_name = ? AND rule = ?
            ORDER BY date DESC, is_final DESC
            LIMIT ?
            """,
            (trainer_name, rule, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_today_ranking(
    rule: int = 0,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """今日の定時収集ランキング全件を返す"""
    today = datetime.now(JST).date().isoformat()
    with _conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT rank, trainer_name, rating, season, site_updated_at
            FROM rankings
            WHERE date = ? AND rule = ? AND is_final = 0
            ORDER BY rank ASC
            """,
            (today, rule),
        ).fetchall()
    return [dict(r) for r in rows]


def get_trainer_today(
    trainer_name: str,
    rule: int = 0,
    db_path: Path = DB_PATH,
) -> dict | None:
    """今日のトレーナー順位を返す（同名複数の場合は最上位）。ランク外なら None。"""
    today = datetime.now(JST).date().isoformat()
    with _conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT rank, rating, season, is_final, site_updated_at
            FROM rankings
            WHERE date = ? AND trainer_name = ? AND rule = ?
            ORDER BY is_final DESC, rank ASC
            LIMIT 1
            """,
            (today, trainer_name, rule),
        ).fetchone()
    return dict(row) if row else None


if __name__ == "__main__":
    init_db()
    print(f"DB初期化完了: {DB_PATH}")
    today_ranking = get_today_ranking()
    print(f"本日のデータ: {len(today_ranking)}件")
