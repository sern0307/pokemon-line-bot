import re
import sqlite3
from datetime import date as _date_type, datetime as _dt_type
from pathlib import Path

import altair as alt
import jpholiday
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent / "data" / "rankings.db"
RULE_LABEL = {0: "シングルバトル", 1: "ダブルバトル"}
RULE_ICON  = {0: "⚔️", 1: "🤝"}
RANK_OUT   = 301

st.set_page_config(
    page_title="PokéChamps Ranking",
    page_icon="🏆",
    layout="wide",
)

# ═══════════════════════════ CSS ═══════════════════════════
st.markdown("""
<style>
/* ── Global ── */
.block-container { padding-top: 1.4rem; padding-bottom: 2.5rem; }

/* ── Hero Banner ── */
.hero {
    background: linear-gradient(135deg, #1b2460 0%, #2b1f6e 100%);
    border: 1px solid #3a3890;
    border-radius: 16px;
    padding: 22px 32px;
    margin-bottom: 22px;
    display: flex;
    align-items: center;
    gap: 18px;
}
.hero-icon  { font-size: 2.6rem; line-height: 1; }
.hero-title { color: #eef0ff; font-size: 1.65rem; font-weight: 800;
              margin: 0; letter-spacing: -0.02em; }
.hero-sub   { color: #9a93d8; font-size: 0.8rem; margin: 4px 0 0; font-weight: 400; }

/* ── Section heading ── */
.sec { font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
       letter-spacing: 0.1em; color: #7C6FFF; margin: 20px 0 8px; }

/* ── Stat cards row ── */
.scards { display: flex; gap: 12px; margin-bottom: 4px; }
.sc {
    flex: 1;
    background: #131828;
    border: 1px solid #232d52;
    border-radius: 12px;
    padding: 14px 18px;
    min-width: 0;
}
.sc-label { color: #7b84b0; font-size: 0.68rem; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.09em; }
.sc-value { color: #e8eaff; font-size: 1.4rem; font-weight: 700;
            margin-top: 3px; line-height: 1.2; white-space: nowrap; }
.sc-value-sm { color: #e8eaff; font-size: 0.95rem; font-weight: 600;
               margin-top: 3px; line-height: 1.2; }

/* ── Trainer detail card ── */
.tcard {
    background: #0f1428;
    border: 1px solid #232d52;
    border-radius: 14px;
    padding: 20px 24px;
    margin-top: 16px;
}
.tcard-name {
    color: #dde0ff; font-size: 1.05rem; font-weight: 700;
    border-bottom: 1px solid #232d52;
    padding-bottom: 12px; margin-bottom: 14px;
}

/* ── Search box emphasis ── */
div[data-testid="stTextInput"] > div > div > input {
    border-radius: 10px;
    font-size: 1.05rem;
    padding: 10px 14px;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] > div:first-child { padding-top: 1.8rem; }
.sb-logo { font-size: 1.3rem; font-weight: 800; color: #eef0ff;
           letter-spacing: -0.01em; margin-bottom: 2px; }
.sb-sub  { font-size: 0.72rem; color: #7b84b0; margin-bottom: 20px; }

/* ── Tab style ── */
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 9px 20px;
    font-weight: 600;
    font-size: 0.88rem;
}

/* ── Caption / helper text ── */
.hint { font-size: 0.78rem; color: #6a72a0; margin-top: -4px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════ Name normalization (OCR誤認識対策) ══════════════════
# 小文字カナ → 大文字カナ（例: ジェミニ ↔ ジエミニ）
_SMALL_TO_LARGE = str.maketrans(
    "ァィゥェォッャュョぁぃぅぇぉっゃゅょ",
    "アイウエオツヤユヨあいうえおつやゆよ",
)

def normalize_name(name: str) -> str:
    """小文字カナを大文字に統一し、表記ゆれを吸収する。"""
    return name.translate(_SMALL_TO_LARGE)


# ══════════════════ 曜日 / 祝日ヘルパー ══════════════════════
_WEEKDAY_JP   = ["月", "火", "水", "木", "金", "土", "日"]
SAT_COLOR     = "#3b82f6"   # 土曜: 青
SUN_HOL_COLOR = "#ef4444"   # 日曜・祝日: 赤
BG_OPACITY    = 0.12


def _parse_date(s: str) -> _date_type:
    return _dt_type.strptime(s[:10], "%Y-%m-%d").date()


def _day_suffix(date_str: str) -> str:
    """'2026-05-14' → '（木）'"""
    return f"（{_WEEKDAY_JP[_parse_date(date_str).weekday()]}）"


def _date_kind(date_str: str) -> str | None:
    """土曜='sat', 日曜・祝日='sun_hol', 平日=None"""
    try:
        d = _parse_date(date_str)
    except Exception:
        return None
    if jpholiday.is_holiday(d):
        return "sun_hol"
    wd = d.weekday()
    if wd == 5:
        return "sat"
    if wd == 6:
        return "sun_hol"
    return None


def _fmt_date_label(date_str: str, is_final: bool = False) -> str:
    """表示ラベル: '2026-05-14（木）' / '★ 2026-05-14（木）'（最終結果）"""
    base = date_str + _day_suffix(date_str)
    return f"★ {base}" if is_final else base


def _raw_date_from_label(label: str) -> str:
    """表示ラベルから YYYY-MM-DD を抽出する。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", label)
    return m.group(1) if m else ""


def _build_bg_layers(
    display_dates: list[str],
    x_sort: list[str],
    y0: float,
    y1: float,
    y_scale: alt.Scale,
    reverse_y: bool = False,
) -> list[alt.Chart]:
    """
    土曜（青）・日曜＆祝日（赤）の背景 mark_rect レイヤーリストを返す。
    display_dates: x 軸に表示されている日付_表示ラベルの全リスト
    """
    sat_x, sun_hol_x = [], []
    for lbl in display_dates:
        raw = _raw_date_from_label(lbl)
        kind = _date_kind(raw) if raw else None
        if kind == "sat":
            sat_x.append(lbl)
        elif kind == "sun_hol":
            sun_hol_x.append(lbl)

    layers: list[alt.Chart] = []
    for xs, color in [(sat_x, SAT_COLOR), (sun_hol_x, SUN_HOL_COLOR)]:
        if not xs:
            continue
        bg_df = pd.DataFrame({"_x": xs, "_y0": float(y0), "_y1": float(y1)})
        layer = (
            alt.Chart(bg_df)
            .mark_rect(opacity=BG_OPACITY, color=color)
            .encode(
                x=alt.X("_x:O", sort=x_sort),
                y=alt.Y("_y0:Q", scale=y_scale),
                y2=alt.Y2("_y1:Q"),
            )
        )
        layers.append(layer)
    return layers


def _apply_row_style(df: pd.DataFrame, date_col: str = "日付"):
    """曜日・祝日に応じた行背景色を持つ Styler を返す（ダークテーマ向け）。"""
    def _row_bg(row):
        raw = _raw_date_from_label(str(row[date_col]))
        kind = _date_kind(raw) if raw else None
        if kind == "sat":
            bg = "background-color: rgba(59,130,246,0.20)"
        elif kind == "sun_hol":
            bg = "background-color: rgba(239,68,68,0.20)"
        else:
            bg = ""
        return [bg] * len(row)
    return df.style.apply(_row_bg, axis=1)


# ═══════════════════════ Chart helper ═══════════════════════
def _styled(chart, height: int | None = None):
    if height:
        chart = chart.properties(height=height)
    return (
        chart
        .configure_view(fill="transparent", stroke="transparent")
        .configure_axis(
            gridColor="#252d55", domainColor="#252d55", tickColor="#252d55",
            labelColor="#8891b5", titleColor="#9ea8d0", labelFontSize=11,
        )
        .configure_legend(labelColor="#c8ccee", titleColor="#9ea8d0",
                          labelFontSize=11, titleFontSize=11)
    )


# ═══════════════════════ Data functions ═══════════════════════
@st.cache_data(ttl=300)
def load_all_dates() -> list[str]:
    """全ルール・全シーズンの集計日一覧（新しい順）。サイドバー統計用。"""
    conn = sqlite3.connect(DB_PATH)
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM rankings ORDER BY date DESC"
    ).fetchall()]
    conn.close()
    return dates


@st.cache_data(ttl=300)
def load_seasons(rule: int) -> list[str]:
    """DBに存在するシーズン一覧を新しい順で返す。"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT season, MAX(date) AS latest
        FROM rankings
        WHERE rule=? AND season IS NOT NULL
        GROUP BY season
        ORDER BY latest DESC
        """,
        (rule,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


@st.cache_data(ttl=300)
def load_date_options(season: str | None, rule: int) -> list[tuple[str, int]]:
    """
    シーズンでフィルタした (date, is_final) の選択肢リストを返す。
    同日に定時・最終の両方がある場合は両方を含む。
    新しい日付順、同日は最終結果を先に。
    """
    conn = sqlite3.connect(DB_PATH)
    has_is_final = bool(conn.execute(
        "SELECT 1 FROM pragma_table_info('rankings') WHERE name='is_final'"
    ).fetchone())

    if has_is_final:
        select_col = "is_final"
        order = "date DESC, is_final DESC"
    else:
        select_col = "0 AS is_final"
        order = "date DESC"

    if season is None:
        rows = conn.execute(
            f"SELECT DISTINCT date, {select_col} FROM rankings "
            f"WHERE rule=? ORDER BY {order}",
            (rule,),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT DISTINCT date, {select_col} FROM rankings "
            f"WHERE rule=? AND season=? ORDER BY {order}",
            (rule, season),
        ).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


@st.cache_data(ttl=300)
def load_ranking(date: str, rule: int, is_final: int = 0) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    has_is_final = bool(conn.execute(
        "SELECT 1 FROM pragma_table_info('rankings') WHERE name='is_final'"
    ).fetchone())
    if has_is_final:
        df = pd.read_sql_query(
            "SELECT rank, trainer_name, rating, season, site_updated_at "
            "FROM rankings WHERE date=? AND rule=? AND is_final=? ORDER BY rank",
            conn, params=(date, rule, is_final),
        )
    else:
        df = pd.read_sql_query(
            "SELECT rank, trainer_name, rating, season, site_updated_at "
            "FROM rankings WHERE date=? AND rule=? ORDER BY rank",
            conn, params=(date, rule),
        )
    conn.close()
    df.columns = ["順位", "トレーナー名", "レーティング", "シーズン", "サイト更新日時"]
    return df


@st.cache_data(ttl=300)
def load_season_for_date(date: str, rule: int, is_final: int = 0) -> str:
    """指定日付・ルール・種別のシーズン名を返す。未記録なら空文字。"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT season FROM rankings WHERE date=? AND rule=? AND is_final=? "
        "AND season IS NOT NULL LIMIT 1",
        (date, rule, is_final),
    ).fetchone()
    conn.close()
    return row[0] if row else ""


@st.cache_data(ttl=300)
def find_name_variants(trainer_name: str, rule: int) -> tuple[str, ...]:
    """
    正規化後に同一となる全表記バリアントを返す（自身を含む）。
    例: "ジェミニ" → ("ジェミニ", "ジエミニ")
    """
    conn = sqlite3.connect(DB_PATH)
    all_names = [r[0] for r in conn.execute(
        "SELECT DISTINCT trainer_name FROM rankings WHERE rule=?", (rule,)
    ).fetchall()]
    conn.close()
    target = normalize_name(trainer_name)
    return tuple(sorted(n for n in all_names if normalize_name(n) == target))


@st.cache_data(ttl=300)
def load_history(trainer_names: tuple[str, ...], rule: int, top_only: bool = True) -> pd.DataFrame:
    """
    複数の表記バリアントをまとめて集計する。
    同日に定時・最終の両データがある場合は最終結果（is_final=1）を優先使用。
    """
    conn = sqlite3.connect(DB_PATH)
    ph = ",".join(["?"] * len(trainer_names))

    # is_final カラムが存在するか確認（旧DBへの後方互換）
    has_is_final = bool(conn.execute(
        "SELECT 1 FROM pragma_table_info('rankings') WHERE name='is_final'"
    ).fetchone())

    if has_is_final:
        all_dates = pd.read_sql_query(
            "SELECT DISTINCT date FROM rankings WHERE rule=? AND is_final=0 ORDER BY date",
            conn, params=(rule,),
        )
        raw = pd.read_sql_query(
            f"SELECT date, rank, rating, is_final FROM rankings "
            f"WHERE trainer_name IN ({ph}) AND rule=? "
            f"ORDER BY date, is_final DESC, rank ASC",
            conn, params=(*trainer_names, rule),
        )
    else:
        # 旧DB（is_final なし）: 全データを定時収集扱いで取得
        all_dates = pd.read_sql_query(
            "SELECT DISTINCT date FROM rankings WHERE rule=? ORDER BY date",
            conn, params=(rule,),
        )
        raw = pd.read_sql_query(
            f"SELECT date, rank, rating, 0 AS is_final FROM rankings "
            f"WHERE trainer_name IN ({ph}) AND rule=? "
            f"ORDER BY date, rank ASC",
            conn, params=(*trainer_names, rule),
        )
    conn.close()

    if raw.empty:
        df = all_dates.copy()
        df.columns = ["日付"]
        df["順位"] = pd.NA
        df["レーティング"] = pd.NA
        df["最終結果"] = False
        return df

    if top_only:
        # 同日内で is_final DESC → rank ASC に並んでいるので先頭行（最終優先の最上位）を取る
        trainer_df = raw.drop_duplicates(subset=["date"], keep="first")
    else:
        trainer_df = raw

    trainer_df = trainer_df.rename(columns={"is_final": "最終結果"})
    trainer_df["最終結果"] = trainer_df["最終結果"].astype(bool)

    df = all_dates.merge(trainer_df[["date", "rank", "rating", "最終結果"]],
                         on="date", how="left")
    df.columns = ["日付", "順位", "レーティング", "最終結果"]
    df["最終結果"] = df["最終結果"].fillna(False)
    return df


@st.cache_data(ttl=300)
def load_avg_rating(rule: int) -> pd.DataFrame:
    """
    平均レート推移。定時収集・最終結果の両方を含む。
    is_final=0: 定時収集、is_final=1: 最終結果。
    チャートの x 軸は date ASC, is_final ASC（最終結果が同日の定時より右に来る）。
    """
    conn = sqlite3.connect(DB_PATH)
    has_is_final = bool(conn.execute(
        "SELECT 1 FROM pragma_table_info('rankings') WHERE name='is_final'"
    ).fetchone())
    if has_is_final:
        df = pd.read_sql_query(
            """
            SELECT date, is_final,
                   ROUND(AVG(rating), 3) AS avg,
                   ROUND(MAX(rating), 3) AS max,
                   ROUND(MIN(rating), 3) AS min
            FROM rankings WHERE rule=?
            GROUP BY date, is_final
            ORDER BY date ASC, is_final ASC
            """,
            conn, params=(rule,),
        )
        df.columns = ["日付", "最終結果", "平均", "最高", "最低"]
        df["最終結果"] = df["最終結果"].astype(bool)
    else:
        df = pd.read_sql_query(
            """
            SELECT date,
                   ROUND(AVG(rating), 3) AS avg,
                   ROUND(MAX(rating), 3) AS max,
                   ROUND(MIN(rating), 3) AS min
            FROM rankings WHERE rule=?
            GROUP BY date ORDER BY date
            """,
            conn, params=(rule,),
        )
        df.columns = ["日付", "平均", "最高", "最低"]
        df["最終結果"] = False
    conn.close()
    # チャート・テーブル用ラベル（曜日付き、最終結果は ★ プレフィックス）
    df["日付_表示"] = df.apply(
        lambda r: _fmt_date_label(r["日付"], bool(r["最終結果"])), axis=1
    )
    return df


@st.cache_data(ttl=300)
def search_trainers(query: str, rule: int) -> list[str]:
    """名前でDBを検索。正規化後の一致も含め、表記ゆれを網羅する。"""
    conn = sqlite3.connect(DB_PATH)
    all_names = [r[0] for r in conn.execute(
        "SELECT DISTINCT trainer_name FROM rankings WHERE rule=? ORDER BY trainer_name",
        (rule,),
    ).fetchall()]
    conn.close()

    norm_q = normalize_name(query)

    # 1) 部分一致（元のクエリ）
    exact = [n for n in all_names if query in n]
    seen_norm = {normalize_name(n) for n in exact}

    # 2) 正規化後に一致するが上記に含まれない名前（代表1件のみ）
    by_norm: list[str] = []
    for name in all_names:
        nn = normalize_name(name)
        if nn == norm_q and name not in exact and nn not in seen_norm:
            by_norm.append(name)
            seen_norm.add(nn)

    return exact + by_norm


# ═══════════════════ Trainer detail component ═══════════════════
def show_trainer_detail(trainer_name: str, rule: int, key_prefix: str = "") -> None:
    # ── 表記ゆれ検出 ──
    all_variants = find_name_variants(trainer_name, rule)
    other_variants = [v for v in all_variants if v != trainer_name]
    if other_variants:
        st.info(
            f"🔗 表記ゆれの可能性がある別名と合わせて集計しています："
            f"**{'、'.join(other_variants)}**"
        )

    top_only = st.checkbox(
        "同名トレーナーが複数いる場合は最上位のみ表示",
        value=True,
        key=f"{key_prefix}top_only_{trainer_name}_{rule}",
    )
    history = load_history(all_variants, rule, top_only=top_only)
    if history.empty:
        st.warning("履歴データがありません。")
        return

    # 後方互換: is_final 未対応DBからのキャッシュ等で列が欠落する場合
    if "最終結果" not in history.columns:
        history["最終結果"] = False

    history["ランク外"] = history["順位"].isna()
    history["順位_表示"] = history["順位"].apply(
        lambda x: "ランク外" if pd.isna(x) else f"{int(x)}位"
    )
    history["順位_グラフ"] = history["順位"].fillna(RANK_OUT)
    # 曜日付き日付ラベル（グラフ軸用、最終結果は ★ プレフィックス）
    history["日付_表示"] = history.apply(
        lambda r: _fmt_date_label(r["日付"], bool(r["最終結果"])), axis=1
    )

    ranked = history.dropna(subset=["順位"])
    latest = history.iloc[-1]

    # ── Metrics ──
    col1, col2, col3 = st.columns(3)
    col1.metric("最新順位", latest["順位_表示"])
    col2.metric(
        "最新レーティング",
        f"{latest['レーティング']:,.3f}" if pd.notna(latest["レーティング"]) else "―",
    )
    col3.metric("記録日数", f"{len(history)}日（ランクイン {len(ranked)}日）")

    # ── Charts ──
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="sec">順位推移　　<span style="font-size:0.75em;color:#f59e0b;">★ = 最終結果</span></div>',
                    unsafe_allow_html=True)
        rank_x_sort  = list(history["日付_表示"])
        rank_y_scale = alt.Scale(reverse=True, domainMax=RANK_OUT + 5)
        base = alt.Chart(history).encode(
            x=alt.X("日付_表示:O", title=None,
                    sort=rank_x_sort,
                    axis=alt.Axis(labelAngle=-45)),
            tooltip=["日付_表示:O", "順位_表示:N", "レーティング:Q"],
        )
        line = base.mark_line(strokeWidth=2).encode(
            y=alt.Y(
                "順位_グラフ:Q", title="順位",
                scale=rank_y_scale,
                axis=alt.Axis(
                    tickMinStep=1,
                    values=list(range(0, 301, 50)) + [RANK_OUT],
                    labelExpr=f"datum.value == {RANK_OUT} ? 'ランク外' : datum.value",
                ),
            ),
            strokeDash=alt.condition(
                alt.datum["ランク外"], alt.value([5, 4]), alt.value([0])
            ),
            color=alt.condition(
                alt.datum["ランク外"], alt.value("#555577"), alt.value("#7C6FFF")
            ),
        )
        pts_normal = base.transform_filter(
            ~alt.datum["最終結果"]
        ).mark_point(size=55, filled=True).encode(
            y=alt.Y("順位_グラフ:Q", scale=rank_y_scale),
            color=alt.condition(
                alt.datum["ランク外"], alt.value("#444466"), alt.value("#7C6FFF")
            ),
        )
        pts_final = base.transform_filter(
            alt.datum["最終結果"]
        ).mark_point(size=120, filled=True, shape="diamond").encode(
            y=alt.Y("順位_グラフ:Q", scale=rank_y_scale),
            color=alt.value("#f59e0b"),
        )
        # 曜日・祝日背景レイヤー
        rank_bg = _build_bg_layers(
            rank_x_sort, rank_x_sort,
            y0=0, y1=RANK_OUT + 5, y_scale=rank_y_scale,
        )
        rank_chart = line + pts_normal + pts_final
        for bg in rank_bg:
            rank_chart = bg + rank_chart
        st.altair_chart(
            _styled(rank_chart, height=250),
            use_container_width=True,
        )

    with c2:
        st.markdown('<div class="sec">レーティング推移</div>', unsafe_allow_html=True)
        r_vals = history["レーティング"].dropna()
        if not r_vals.empty:
            r_min, r_max = r_vals.min(), r_vals.max()
            margin = (r_max - r_min) * 0.1 or 10
            r_y0, r_y1 = r_min - margin, r_max + margin
            r_y_scale  = alt.Scale(domain=[r_y0, r_y1])
            h_rated    = history.dropna(subset=["レーティング"])
            r_x_sort   = list(h_rated["日付_表示"])
            line_r = (
                alt.Chart(h_rated)
                .mark_line(strokeWidth=2, color="#7C6FFF")
                .encode(
                    x=alt.X("日付_表示:O", title=None,
                            sort=r_x_sort,
                            axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("レーティング:Q", scale=r_y_scale),
                    tooltip=["日付_表示:O", "順位_表示:N", "レーティング:Q"],
                )
            )
            pts_r_normal = (
                alt.Chart(h_rated[~h_rated["最終結果"]])
                .mark_point(size=50, filled=True, color="#7C6FFF")
                .encode(
                    x=alt.X("日付_表示:O", sort=r_x_sort),
                    y=alt.Y("レーティング:Q", scale=r_y_scale),
                )
            )
            pts_r_final = (
                alt.Chart(h_rated[h_rated["最終結果"]])
                .mark_point(size=120, filled=True, shape="diamond", color="#f59e0b")
                .encode(
                    x=alt.X("日付_表示:O", sort=r_x_sort),
                    y=alt.Y("レーティング:Q", scale=r_y_scale),
                )
            )
            # 曜日・祝日背景レイヤー
            r_bg = _build_bg_layers(
                r_x_sort, r_x_sort,
                y0=r_y0, y1=r_y1, y_scale=r_y_scale,
            )
            rating_chart = line_r + pts_r_normal + pts_r_final
            for bg in r_bg:
                rating_chart = bg + rating_chart
            st.altair_chart(
                _styled(rating_chart, height=250),
                use_container_width=True,
            )
        else:
            st.info("レーティングデータがありません。")

    # ── Table ──
    st.markdown('<div class="sec">履歴テーブル</div>', unsafe_allow_html=True)
    tbl = history[["日付", "順位_表示", "レーティング", "最終結果"]].copy()
    tbl["日付"] = tbl.apply(
        lambda r: _fmt_date_label(r["日付"], bool(r["最終結果"])), axis=1
    )
    tbl = tbl.drop(columns=["最終結果"])
    tbl.columns = ["日付", "順位", "レーティング"]
    tbl = tbl.sort_values("日付", ascending=False)
    styled_tbl = _apply_row_style(tbl, date_col="日付")
    styled_tbl = styled_tbl.format({"レーティング": lambda v: f"{v:.3f}" if pd.notna(v) else "―"})
    st.dataframe(
        styled_tbl,
        use_container_width=True,
        hide_index=True,
        column_config={
            "レーティング": st.column_config.NumberColumn(format="%.3f"),
        },
    )


# ═══════════════════════════ Sidebar ═══════════════════════════
st.sidebar.markdown('<div class="sb-logo">🏆 PokéChamps</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sb-sub">ランキングアーカイブ</div>', unsafe_allow_html=True)
st.sidebar.markdown("---")

rule = st.sidebar.radio(
    "バトルルール",
    [0, 1],
    format_func=lambda x: f"{RULE_ICON[x]}  {RULE_LABEL[x]}",
)

# ── シーズン選択 ──
seasons = load_seasons(rule)
ALL_SEASONS_LABEL = "📅 全シーズン"
if seasons:
    season_options = seasons + [ALL_SEASONS_LABEL]
    sel_season_ui = st.sidebar.selectbox("シーズン", season_options, index=0)
    selected_season = None if sel_season_ui == ALL_SEASONS_LABEL else sel_season_ui
else:
    selected_season = None
    sel_season_ui = ALL_SEASONS_LABEL

# ── 日付選択（定時・最終を区別した選択肢） ──
date_options = load_date_options(selected_season, rule)  # list[tuple[str, int]]
all_dates = load_all_dates()

if not all_dates:
    st.error("データがありません。GitHub Actions を実行してください。")
    st.stop()

if not date_options:
    st.warning("このシーズンのデータはまだありません。")
    st.stop()

def _fmt_date(opt: tuple[str, int]) -> str:
    date, is_final = opt
    base = date + _day_suffix(date)
    return f"★ {base}（最終結果）" if is_final else base

selected_opt = st.sidebar.selectbox("集計日付", date_options, format_func=_fmt_date)
selected_date, selected_is_final = selected_opt

st.sidebar.markdown("---")
st.sidebar.markdown(f"""
<div style="font-size:0.75rem; color:#6a72a0; line-height:1.9;">
  最終収集：<span style="color:#9a93d8">{all_dates[0]}</span><br>
  蓄積日数：<span style="color:#9a93d8">{len(all_dates)} 日分（全体）</span>
</div>
""", unsafe_allow_html=True)

if "selected_trainer" not in st.session_state:
    st.session_state.selected_trainer = ""

season_hero = selected_season or load_season_for_date(selected_date, rule, selected_is_final) or "全シーズン"
final_badge = "　／　<span style='color:#f59e0b;font-weight:700;'>★ 最終結果</span>" if selected_is_final else ""

# ═══════════════════════ Hero Header ═══════════════════════════
st.markdown(f"""
<div class="hero">
  <div class="hero-icon">🏆</div>
  <div>
    <div class="hero-title">ポケモンチャンピオンズ ランキング</div>
    <div class="hero-sub">
      {RULE_ICON[rule]}&nbsp;{RULE_LABEL[rule]}　／　🗓&nbsp;{season_hero}　／　集計日：{selected_date}{_day_suffix(selected_date)}{final_badge}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════ Tabs ═══════════════════════════════
tab1, tab2, tab3 = st.tabs(["　📋  ランキング一覧　", "　🔍  トレーナー検索　", "　📊  レート統計　"])


# ══════════════════ Tab 1 — ランキング一覧 ══════════════════════
with tab1:
    df = load_ranking(selected_date, rule, is_final=selected_is_final)
    if df.empty:
        st.warning("この日付のデータはありません。")
    else:
        updated = df["サイト更新日時"].iloc[0]
        top_rating = df["レーティング"].max()
        p300_rating = df["レーティング"].min()
        tab1_season = df["シーズン"].dropna().iloc[0] if df["シーズン"].notna().any() else "―"

        # Stats row (custom HTML cards)
        st.markdown(f"""
        <div class="scards">
          <div class="sc">
            <div class="sc-label">シーズン</div>
            <div class="sc-value-sm">{tab1_season}</div>
          </div>
          <div class="sc">
            <div class="sc-label">1 位レーティング</div>
            <div class="sc-value">{top_rating:,.3f}</div>
          </div>
          <div class="sc">
            <div class="sc-label">300 位レーティング</div>
            <div class="sc-value">{p300_rating:,.3f}</div>
          </div>
          <div class="sc">
            <div class="sc-label">サイト更新日時</div>
            <div class="sc-value-sm">{updated}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="hint">👆 行をクリックするとトレーナーの推移を表示します</div>',
                    unsafe_allow_html=True)

        event = st.dataframe(
            df[["順位", "トレーナー名", "レーティング"]],
            use_container_width=True,
            hide_index=True,
            height=420,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "順位":        st.column_config.NumberColumn(width="small"),
                "トレーナー名": st.column_config.TextColumn(width="small", max_chars=12),
                "レーティング": st.column_config.NumberColumn(width="small", format="%.3f"),
            },
        )

        selected_rows = event.selection.rows
        if selected_rows:
            trainer_name = df.iloc[selected_rows[0]]["トレーナー名"]
            st.session_state.selected_trainer = trainer_name
            st.markdown(f"""
            <div class="tcard">
              <div class="tcard-name">📈 {trainer_name} の推移</div>
            </div>
            """, unsafe_allow_html=True)
            # render inside a container placed after the card HTML
            with st.container():
                show_trainer_detail(trainer_name, rule, key_prefix="tab1_")


# ══════════════════ Tab 2 — トレーナー検索 ══════════════════════
with tab2:
    st.markdown('<div class="sec">トレーナー名で検索</div>', unsafe_allow_html=True)
    query = st.text_input(
        "トレーナー名",
        value=st.session_state.selected_trainer,
        placeholder="例：ジェミニ",
        label_visibility="collapsed",
    )
    st.session_state.selected_trainer = query

    if query:
        candidates = search_trainers(query, rule)
        if not candidates:
            st.warning(f"「{query}」に一致するトレーナーはDBに存在しません。")
        else:
            trainer = candidates[0]
            st.markdown(f"""
            <div class="tcard">
              <div class="tcard-name">📈 {trainer} の推移</div>
            </div>
            """, unsafe_allow_html=True)
            with st.container():
                show_trainer_detail(trainer, rule, key_prefix="tab2_")
    else:
        st.markdown(
            '<div style="color:#6a72a0; font-size:0.88rem; margin-top:12px;">'
            "トレーナー名を入力すると順位・レーティング推移が表示されます。</div>",
            unsafe_allow_html=True,
        )


# ══════════════════ Tab 3 — レート統計 ══════════════════════════
with tab3:
    avg_df = load_avg_rating(rule)
    if avg_df.empty:
        st.warning("データがありません。")
    else:
        # メトリクス用: 定時収集の最新行を参照
        regular_df = avg_df[~avg_df["最終結果"]]
        final_df   = avg_df[avg_df["最終結果"]]
        latest_reg = regular_df.iloc[-1] if not regular_df.empty else avg_df.iloc[-1]
        prev_reg   = regular_df.iloc[-2] if len(regular_df) >= 2 else None
        diff = round(latest_reg["平均"] - prev_reg["平均"], 3) if prev_reg is not None else None

        # 最終結果の最新行（あれば）
        latest_final = final_df.iloc[-1] if not final_df.empty else None

        diff_str  = f"{diff:+.3f}" if diff is not None else "―"
        diff_color = "#4ade80" if (diff or 0) >= 0 else "#f87171"

        # Stats row
        final_card = ""
        if latest_final is not None:
            final_card = f"""
          <div class="sc" style="border-color:#f59e0b55;">
            <div class="sc-label" style="color:#f59e0b;">★ 最終結果 平均レーティング</div>
            <div class="sc-value">{latest_final['平均']:,.3f}</div>
          </div>"""

        st.markdown(f"""
        <div class="scards">
          <div class="sc">
            <div class="sc-label">最新 平均レーティング（定時）</div>
            <div class="sc-value">{latest_reg['平均']:,.3f}
              <span style="font-size:0.8rem; color:{diff_color}; font-weight:600;">
                &nbsp;{diff_str}
              </span>
            </div>
          </div>
          <div class="sc">
            <div class="sc-label">最新 最高レーティング</div>
            <div class="sc-value">{latest_reg['最高']:,.3f}</div>
          </div>
          <div class="sc">
            <div class="sc-label">最新 最低レーティング</div>
            <div class="sc-value">{latest_reg['最低']:,.3f}</div>
          </div>
          {final_card}
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sec">レーティング推移チャート　　<span style="font-size:0.75em;color:#f59e0b;">★ = 最終結果</span></div>',
                    unsafe_allow_html=True)

        # x 軸ラベル順（定時 → 同日最終の順）
        x_order = list(avg_df["日付_表示"])

        COLOR_MAP = {"平均": "#7C6FFF", "最高": "#f59e0b", "最低": "#60a5fa"}
        r_min   = avg_df["最低"].min()
        r_max   = avg_df["最高"].max()
        margin  = (r_max - r_min) * 0.06 or 10
        t3_y0   = r_min - margin
        t3_y1   = r_max + margin
        y_scale = alt.Scale(domain=[t3_y0, t3_y1])

        # 全データ（定時＋最終）を melt — 折れ線はすべてのデータを通す
        melted_all = avg_df.melt(
            id_vars="日付_表示", value_vars=["平均", "最高", "最低"],
            var_name="指標", value_name="レーティング",
        )
        melted_reg = regular_df.melt(
            id_vars="日付_表示", value_vars=["平均", "最高", "最低"],
            var_name="指標", value_name="レーティング",
        )

        color_enc = alt.Color(
            "指標:N",
            scale=alt.Scale(domain=list(COLOR_MAP.keys()),
                            range=list(COLOR_MAP.values())),
            legend=alt.Legend(title="指標", orient="top-left"),
        )

        # 折れ線: 定時→最終→次の定時 をすべて繋ぐ（点なし）
        line_chart = (
            alt.Chart(melted_all)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("日付_表示:O", title=None, sort=x_order,
                        axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("レーティング:Q", scale=y_scale),
                color=color_enc,
                strokeDash=alt.condition(
                    alt.datum["指標"] == "平均",
                    alt.value([0]), alt.value([5, 4]),
                ),
                tooltip=["日付_表示:O", "指標:N", "レーティング:Q"],
            )
        )
        # 定時点: 丸
        reg_points = (
            alt.Chart(melted_reg)
            .mark_point(filled=True, size=45)
            .encode(
                x=alt.X("日付_表示:O", sort=x_order),
                y=alt.Y("レーティング:Q", scale=y_scale),
                color=color_enc,
            )
        )

        # 最終結果点: ◆ マーカー（線は上の line_chart が通過済み）
        final_charts = []
        if not final_df.empty:
            melted_fin = final_df.melt(
                id_vars="日付_表示", value_vars=["平均", "最高", "最低"],
                var_name="指標", value_name="レーティング",
            )
            final_points = (
                alt.Chart(melted_fin)
                .mark_point(shape="diamond", size=130, filled=True, opacity=0.9)
                .encode(
                    x=alt.X("日付_表示:O", sort=x_order),
                    y=alt.Y("レーティング:Q", scale=y_scale),
                    color=color_enc,
                    tooltip=["日付_表示:O", "指標:N", "レーティング:Q"],
                )
            )
            final_charts.append(final_points)

        # 曜日・祝日背景レイヤー（x_order 全体を対象）
        t3_bg = _build_bg_layers(
            x_order, x_order,
            y0=t3_y0, y1=t3_y1, y_scale=y_scale,
        )
        combined = line_chart + reg_points
        for fc in final_charts:
            combined = combined + fc
        for bg in t3_bg:
            combined = bg + combined

        st.altair_chart(_styled(combined, height=380), use_container_width=True)

        # 集計テーブル（最終結果を最上部に、曜日付き、週末・祝日に色付け）
        st.markdown('<div class="sec">集計テーブル</div>', unsafe_allow_html=True)
        t3_tbl = avg_df.sort_values(["日付", "最終結果"], ascending=[False, False]).copy()
        t3_tbl["日付"] = t3_tbl["日付_表示"].apply(
            lambda v: f"{v}（最終結果）" if v.startswith("★") else v
        )
        t3_tbl = t3_tbl[["日付", "平均", "最高", "最低"]]
        styled_t3 = _apply_row_style(t3_tbl, date_col="日付")
        styled_t3 = styled_t3.format({
            "平均": "{:.3f}", "最高": "{:.3f}", "最低": "{:.3f}",
        })
        st.dataframe(
            styled_t3,
            use_container_width=True,
            hide_index=True,
            column_config={
                "平均": st.column_config.NumberColumn(format="%.3f"),
                "最高": st.column_config.NumberColumn(format="%.3f"),
                "最低": st.column_config.NumberColumn(format="%.3f"),
            },
        )
