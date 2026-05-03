"""
champs.pokedb.tokyo からランキング全300件を取得するスクレイパー
"""
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://champs.pokedb.tokyo/trainer/list"
PAGES = 3        # 1ページ100件 × 3ページ = 300件
PAGE_DELAY = 1.0 # サーバー負荷軽減のためのウェイト（秒）

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def scrape_page(page: int, season: int | None, rule: int) -> tuple[list[dict], str | None]:
    """
    指定ページのトレーナー一覧を取得する。
    戻り値: (トレーナーリスト, 更新日時文字列 or None)
    """
    params = {"rule": rule, "page": page}
    if season is not None:
        params["season"] = season

    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        raise RuntimeError(f"page={page} 取得失敗: {e}") from e

    soup = BeautifulSoup(resp.text, "lxml")

    # 更新日時（page=1 のみ取得すれば十分）
    updated_at = None
    for tag_el in soup.select("span.tag.is-warning"):
        if "更新日" in tag_el.get_text():
            sibling = tag_el.find_next_sibling("span", class_="tag")
            if sibling:
                updated_at = sibling.get_text(strip=True)
            break

    trainers = []
    for card in soup.select("article.trainer-card"):
        # 順位
        rank_el = card.select_one("span.trainer-card-rank-number")
        rank = None
        if rank_el:
            rank = int(rank_el.get_text(strip=True))
        else:
            rank_div = card.select_one("div.trainer-card-rank")
            if rank_div and rank_div.get("data-rank"):
                rank = int(rank_div["data-rank"])

        # レーティング
        int_el = card.select_one("span.rating-integer")
        dec_el = card.select_one("span.rating-decimal")
        rating = None
        if int_el:
            rating_str = int_el.get_text(strip=True)
            if dec_el:
                rating_str += dec_el.get_text(strip=True)
            try:
                rating = float(rating_str)
            except ValueError:
                pass

        # トレーナー名
        name_el = card.select_one("div.trainer-card-name")
        name = name_el.get_text(strip=True) if name_el else None

        if rank is not None and name:
            trainers.append({
                "rank": rank,
                "rating": rating,
                "trainer_name": name,
            })

    return trainers, updated_at


def scrape_all(season: int | None = None, rule: int = 0) -> tuple[list[dict], str | None]:
    """
    全3ページ(300件)を取得してまとめて返す。
    戻り値: (全トレーナーリスト, 更新日時)
    """
    all_trainers = []
    updated_at = None

    for page in range(1, PAGES + 1):
        trainers, page_updated = scrape_page(page, season, rule)
        all_trainers.extend(trainers)
        if updated_at is None and page_updated:
            updated_at = page_updated
        print(f"  page {page}/{PAGES}: {len(trainers)}件取得")
        if page < PAGES:
            time.sleep(PAGE_DELAY)

    return all_trainers, updated_at


def get_trainer_rank(trainer_name: str, season: int | None = None, rule: int = 0) -> dict | None:
    """
    特定トレーナーの順位情報を返す（1件検索用）。
    見つからない場合は None を返す。
    """
    params = {"q": trainer_name, "rule": rule}
    if season is not None:
        params["season"] = season

    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        raise RuntimeError(f"ページ取得失敗: {e}") from e

    soup = BeautifulSoup(resp.text, "lxml")

    updated_at = None
    for tag_el in soup.select("span.tag.is-warning"):
        if "更新日" in tag_el.get_text():
            sibling = tag_el.find_next_sibling("span", class_="tag")
            if sibling:
                updated_at = sibling.get_text(strip=True)
            break

    for card in soup.select("article.trainer-card"):
        name_el = card.select_one("div.trainer-card-name")
        if name_el is None or trainer_name not in name_el.get_text(strip=True):
            continue

        rank_el = card.select_one("span.trainer-card-rank-number")
        rank = None
        if rank_el:
            rank = int(rank_el.get_text(strip=True))
        else:
            rank_div = card.select_one("div.trainer-card-rank")
            if rank_div and rank_div.get("data-rank"):
                rank = int(rank_div["data-rank"])

        int_el = card.select_one("span.rating-integer")
        dec_el = card.select_one("span.rating-decimal")
        rating = None
        if int_el:
            rating_str = int_el.get_text(strip=True)
            if dec_el:
                rating_str += dec_el.get_text(strip=True)
            try:
                rating = float(rating_str)
            except ValueError:
                pass

        return {
            "rank": rank,
            "rating": rating,
            "trainer": name_el.get_text(strip=True),
            "updated_at": updated_at,
        }

    return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 引数あり → 1件検索モード
        name = sys.argv[1]
        result = get_trainer_rank(name)
        if result:
            print(f"順位: {result['rank']}位")
            print(f"レーティング: {result['rating']}")
            print(f"トレーナー: {result['trainer']}")
            if result.get("updated_at"):
                print(f"更新日時: {result['updated_at']}")
        else:
            print(f"「{name}」はランク外または見つかりませんでした")
    else:
        # 引数なし → 全件取得モード
        print("全300件を取得中...")
        trainers, updated_at = scrape_all()
        print(f"\n取得完了: {len(trainers)}件 (更新日時: {updated_at})")
        print("\n--- 上位5件 ---")
        for t in trainers[:5]:
            print(f"{t['rank']:3d}位  {t['rating']:>10.3f}  {t['trainer_name']}")
