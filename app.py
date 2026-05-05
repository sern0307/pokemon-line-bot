import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

import streamlit as st
import pandas as pd
import altair as alt

DB_PATH = Path(__file__).parent / "data" / "rankings.db"
JST = timezone(timedelta(hours=9))
RULE_LABEL = {0: "シングルバトル", 1: "ダブルバトル"}

st.set_page_config(
    page_title="ポケモンチャンピオンズ ランキング",
    page_icon="🏆",
    layout="wide",
)


@st.cache_data(ttl=300)
def load_dates() -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM rankings ORDER BY date DESC"
    ).fetchall()]
    conn.close()
    return dates


@st.cache_data(ttl=300)
def load_ranking(date: str, rule: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT rank, trainer_name, rating, site_updated_at "
        "FROM rankings WHERE date=? AND rule=? ORDER BY rank",
        conn, params=(date, rule)
    )
    conn.close()
    df.columns = ["順位", "トレーナー名", "レーティング", "サイト更新日時"]
    return df


@st.cache_data(ttl=300)
def load_history(trainer_name: str, rule: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT date, rank, rating FROM rankings "
        "WHERE trainer_name=? AND rule=? ORDER BY date",
        conn, params=(trainer_name, rule)
    )
    conn.close()
    df.columns = ["日付", "順位", "レーティング"]
    return df


@st.cache_data(ttl=300)
def search_trainers(query: str, rule: int) -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT DISTINCT trainer_name FROM rankings "
        "WHERE trainer_name LIKE ? AND rule=? ORDER BY trainer_name",
        (f"%{query}%", rule)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# --- サイドバー ---
st.sidebar.title("🏆 ランキング閲覧")

rule = st.sidebar.radio("バトルルール", [0, 1], format_func=lambda x: RULE_LABEL[x])

dates = load_dates()
if not dates:
    st.error("データがありません。GitHub Actionsを実行してください。")
    st.stop()

selected_date = st.sidebar.selectbox("日付", dates)

st.sidebar.markdown("---")
st.sidebar.caption(f"最終収集: {dates[0]}")
st.sidebar.caption(f"蓄積日数: {len(dates)}日分")

# --- メインエリア ---
tab1, tab2 = st.tabs(["📋 ランキング一覧", "📈 トレーナー検索・推移"])

# ========== Tab1: ランキング一覧 ==========
with tab1:
    st.subheader(f"{selected_date} ランキング（{RULE_LABEL[rule]}）")

    df = load_ranking(selected_date, rule)
    if df.empty:
        st.warning("この日付のデータはありません。")
    else:
        updated = df["サイト更新日時"].iloc[0] if not df.empty else "-"
        col1, col2, col3 = st.columns(3)
        col1.metric("取得件数", f"{len(df)} 件")
        col2.metric("1位レーティング", f"{df['レーティング'].max():,.3f}")
        col3.metric("サイト更新日時", updated)

        st.dataframe(
            df[["順位", "トレーナー名", "レーティング"]],
            use_container_width=True,
            hide_index=True,
            height=600,
        )

# ========== Tab2: トレーナー検索・推移 ==========
with tab2:
    st.subheader("トレーナー検索")

    query = st.text_input("トレーナー名を入力", placeholder="例: ジェミニ")

    if query:
        candidates = search_trainers(query, rule)
        if not candidates:
            st.warning(f"「{query}」に一致するトレーナーはDBに存在しません。")
        else:
            selected_trainer = st.selectbox("トレーナーを選択", candidates)

            history = load_history(selected_trainer, rule)
            if history.empty:
                st.warning("履歴データがありません。")
            else:
                latest = history.iloc[-1]
                col1, col2, col3 = st.columns(3)
                col1.metric("最新順位", f"{int(latest['順位'])}位")
                col2.metric("最新レーティング", f"{latest['レーティング']:,.3f}")
                col3.metric("記録日数", f"{len(history)}日")

                # 順位推移チャート（Y軸反転：1位が上）
                st.markdown("#### 順位推移")
                rank_chart = (
                    alt.Chart(history)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("日付:O", title="日付", axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y(
                            "順位:Q",
                            title="順位",
                            scale=alt.Scale(reverse=True),
                            axis=alt.Axis(tickMinStep=1),
                        ),
                        tooltip=["日付:O", "順位:Q", "レーティング:Q"],
                    )
                    .properties(height=300)
                )
                st.altair_chart(rank_chart, use_container_width=True)

                st.markdown("#### レーティング推移")
                r_min = history["レーティング"].min()
                r_max = history["レーティング"].max()
                margin = (r_max - r_min) * 0.1 or 10
                rating_chart = (
                    alt.Chart(history)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("日付:O", title="日付", axis=alt.Axis(labelAngle=-45)),
                        y=alt.Y(
                            "レーティング:Q",
                            title="レーティング",
                            scale=alt.Scale(domain=[r_min - margin, r_max + margin]),
                        ),
                        tooltip=["日付:O", "順位:Q", "レーティング:Q"],
                    )
                    .properties(height=300)
                )
                st.altair_chart(rating_chart, use_container_width=True)

                st.markdown("#### 履歴テーブル")
                st.dataframe(
                    history.sort_values("日付", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )
