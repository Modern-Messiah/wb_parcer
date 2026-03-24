from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


SEARCH_QUERY = "пальто из натуральной шерсти"
FULL_CATALOG_FILE = "full_catalog.xlsx"
FILTERED_CATALOG_FILE = "filtered_catalog.xlsx"
SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v18/search"
BASKET_HOSTS = [f"basket-{index:02d}.wbbasket.ru" for index in range(1, 31)]


@dataclass
class SearchConfig:
    query: str = SEARCH_QUERY
    page: int = 1
    delay_seconds: float = 0.5
    dest: int = -1257786
    max_retries: int = 6


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": "https://www.wildberries.ru/",
        }
    )
    return session


def request_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
    max_retries: int = 6,
) -> Any:
    for attempt in range(1, max_retries + 1):
        response = session.get(url, params=params, timeout=timeout)
        if response.status_code == 429:
            time.sleep(min(20, attempt * 2))
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError(f"Не удалось получить ответ после {max_retries} попыток: {url}")


def fetch_search_page(
    session: requests.Session,
    query: str,
    page: int,
    dest: int,
    max_retries: int,
) -> list[dict[str, Any]]:
    params = {
        "appType": 1,
        "curr": "rub",
        "dest": dest,
        "lang": "ru",
        "page": page,
        "query": query,
        "resultset": "catalog",
        "sort": "popular",
        "spp": 30,
        "suppressSpellcheck": "false",
    }
    data = request_json(session, SEARCH_URL, params=params, max_retries=max_retries)
    return data.get("products", []) or data.get("data", {}).get("products", [])


def product_path_parts(article: int) -> tuple[int, int]:
    return article // 100000, article // 1000


def build_product_url(article: int) -> str:
    return f"https://www.wildberries.ru/catalog/{article}/detail.aspx"


def build_seller_url(supplier_id: int | None) -> str:
    if not supplier_id:
        return ""
    return f"https://www.wildberries.ru/seller/{supplier_id}"


def get_product_price(product: dict[str, Any]) -> float | None:
    sizes = product.get("sizes") or []
    first_size = sizes[0] if sizes else {}
    price_block = first_size.get("price") or {}
    price = (
        price_block.get("product")
        or price_block.get("total")
        or product.get("salePriceU")
        or product.get("priceU")
        or 0
    )
    return round(price / 100, 2) if price else None


def get_product_sizes(product: dict[str, Any]) -> str:
    sizes = []
    for size in product.get("sizes") or []:
        name = size.get("origName") or size.get("name")
        if name:
            sizes.append(str(name))
    return ", ".join(dict.fromkeys(sizes))


def extract_country(options: list[dict[str, Any]]) -> str:
    for item in options:
        if item.get("name") == "Страна производства":
            return item.get("value", "")
    return ""


def normalize_characteristics(card: dict[str, Any]) -> list[dict[str, Any]]:
    grouped = card.get("grouped_options") or []
    if grouped:
        return grouped

    options = card.get("options") or []
    return [{"group_name": "Характеристики", "options": options}] if options else []


def resolve_basket_host(
    session: requests.Session,
    article: int,
    host_cache: dict[int, str],
) -> str:
    vol, part = product_path_parts(article)
    cached_host = host_cache.get(vol)
    if cached_host:
        return cached_host

    for host in BASKET_HOSTS:
        url = f"https://{host}/vol{vol}/part{part}/{article}/info/ru/card.json"
        response = session.get(url, timeout=30)
        if response.status_code == 429:
            time.sleep(2)
            continue
        if response.ok and response.headers.get("content-type", "").startswith("application/json"):
            host_cache[vol] = host
            return host

    raise RuntimeError(f"Не удалось определить basket host для товара {article}")


def fetch_product_card(
    session: requests.Session,
    article: int,
    host_cache: dict[int, str],
    max_retries: int,
) -> tuple[dict[str, Any], str]:
    host = resolve_basket_host(session, article, host_cache)
    vol, part = product_path_parts(article)
    url = f"https://{host}/vol{vol}/part{part}/{article}/info/ru/card.json"
    card = request_json(session, url, max_retries=max_retries)
    return card, host


def build_image_urls(article: int, photo_count: int, host: str) -> str:
    if photo_count <= 0:
        return ""

    vol, part = product_path_parts(article)
    urls = []
    for index in range(1, photo_count + 1):
        urls.append(
            f"https://{host}/vol{vol}/part{part}/{article}/images/c516x688/{index}.webp"
        )
    return ", ".join(urls)


def enrich_product(
    session: requests.Session,
    product: dict[str, Any],
    host_cache: dict[int, str],
    config: SearchConfig,
) -> dict[str, Any]:
    article = int(product.get("id") or product.get("nmId"))
    card, host = fetch_product_card(session, article, host_cache, config.max_retries)
    options = card.get("options") or []
    selling = card.get("selling") or {}

    return {
        "product_url": build_product_url(article),
        "article": article,
        "name": product.get("name") or card.get("imt_name", ""),
        "price": get_product_price(product),
        "description": card.get("description", ""),
        "image_urls": build_image_urls(
            article,
            (card.get("media") or {}).get("photo_count", 0),
            host,
        ),
        "characteristics": json.dumps(normalize_characteristics(card), ensure_ascii=False),
        "seller_name": product.get("supplier") or selling.get("brand_name", ""),
        "seller_url": build_seller_url(selling.get("supplier_id") or product.get("supplierId")),
        "sizes": get_product_sizes(product),
        "stock": product.get("totalQuantity"),
        "rating": product.get("rating"),
        "reviews_count": product.get("feedbacks") or product.get("reviewCount"),
        "country": extract_country(options),
    }


def collect_catalog(config: SearchConfig) -> list[dict[str, Any]]:
    session = build_session()
    page = config.page
    products: list[dict[str, Any]] = []
    seen_articles: set[int] = set()
    host_cache: dict[int, str] = {}

    while True:
        page_items = fetch_search_page(
            session,
            config.query,
            page,
            config.dest,
            config.max_retries,
        )
        if not page_items:
            break

        added = 0
        for item in page_items:
            article = item.get("id") or item.get("nmId")
            if not article or article in seen_articles:
                continue

            seen_articles.add(article)
            products.append(enrich_product(session, item, host_cache, config))
            added += 1

        if added == 0:
            break

        page += 1
        time.sleep(config.delay_seconds)

    return products


def save_excel(products: list[dict[str, Any]]) -> None:
    df = pd.DataFrame(products)
    df.to_excel(FULL_CATALOG_FILE, index=False)

    filtered_df = df[
        (df["rating"].fillna(0) >= 4.5)
        & (df["price"].fillna(0) <= 10000)
        & (df["country"].fillna("").str.lower() == "россия")
    ]
    filtered_df.to_excel(FILTERED_CATALOG_FILE, index=False)


def main() -> None:
    config = SearchConfig()
    products = collect_catalog(config)
    save_excel(products)
    print(f"Собрано товаров: {len(products)}")
    print(f"Файл каталога: {FULL_CATALOG_FILE}")
    print(f"Файл фильтра: {FILTERED_CATALOG_FILE}")


if __name__ == "__main__":
    main()
