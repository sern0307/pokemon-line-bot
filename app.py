import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent / "data" / "rankings.db"
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


def show_trainer_detail(trainer_name: str, rule: int) -> None:
    """トレーナーの順位・レーティング推移を表示する共通コンポーネント"""
    history = load_history(trainer_name, rule)
    if history.empty:
        st.warning("履歴データがありません。")
        return

    latest = history.iloc[-1]
    col1, col2, col3 = st.columns(3)
    col1.metric("最新順位", f"{int(latest['順位'])}位")
    col2.metric("最新レーティング", f"{latest['レーティング']:,.3f}")
    col3.metric("記録日数", f"{len(history)}日")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 順位推移")
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
            .properties(height=260)
        )
        st.altair_chart(rank_chart, use_container_width=True)

    with c2:
        st.markdown("##### レーティング推移")
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
            .properties(height=260)
        )
        st.altair_chart(rating_chart, use_container_width=True)

    st.dataframe(
        history.sort_values("日付", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


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

# session_state の初期化
if "selected_trainer" not in st.session_state:
    st.session_state.selected_trainer = ""

# --- タブ ---
tab1, tab2 = st.tabs(["📋 ランキング一覧", "📈 トレーナー検索・推移"])

# ========== Tab1: ランキング一覧 ==========
with tab1:
    st.subheader(f"{selected_date} ランキング（{RULE_LABEL[rule]}）")

    df = load_ranking(selected_date, rule)
    if df.empty:
        st.warning("この日付のデータはありません。")
    else:
        updated = df["サイト更新日時"].iloc[0]
        col1, col2 = st.columns(2)
        col1.metric("1位レーティング", f"{df['レーティング'].max():,.3f}")
        col2.metric("サイト更新日時", updated)

        st.caption("👆 行を選択するとトレーナー詳細を表示します")
        event = st.dataframe(
            df[["順位", "トレーナー名", "レーティング"]],
            use_container_width=True,
            hide_index=True,
            height=400,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "順位":       st.column_config.NumberColumn(width="small"),
                "トレーナー名": st.column_config.TextColumn(width="small", max_chars=12),
                "レーティング": st.column_config.NumberColumn(width="small", format="%.3f"),
            },
        )

        # 行選択時の処理
        selected_rows = event.selection.rows
        if selected_rows:
            trainer_name = df.iloc[selected_rows[0]]["トレーナー名"]
            st.session_state.selected_trainer = trainer_name
            st.markdown(f"---\n#### 📈 {trainer_name} の推移")
            show_trainer_detail(trainer_name, rule)

# ========== Tab2: トレーナー検索・推移 ==========
with tab2:
    st.subheader("トレーナー検索")

    query = st.text_input(
        "トレーナー名を入力",
        value=st.session_state.selected_trainer,
        placeholder="例: ジェミニ",
    )
    # 入力が変わったら session_state を更新
    st.session_state.selected_trainer = query

    if query:
        candidates = search_trainers(query, rule)
        if not candidates:
            st.warning(f"「{query}」に一致するトレーナーはDBに存在しません。")
        else:
            selected_trainer = st.selectbox("トレーナーを選択", candidates)
            show_trainer_detail(selected_trainer, rule)
