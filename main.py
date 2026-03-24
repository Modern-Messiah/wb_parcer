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


def normalize_search_product(product: dict[str, Any]) -> dict[str, Any]:
    article = product.get("id") or product.get("nmId")
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

    return {
        "product_url": f"https://www.wildberries.ru/catalog/{article}/detail.aspx",
        "article": article,
        "name": product.get("name", ""),
        "price": round(price / 100, 2) if price else None,
        "description": "",
        "image_urls": "",
        "characteristics": json.dumps({}, ensure_ascii=False),
        "seller_name": "",
        "seller_url": "",
        "sizes": "",
        "stock": None,
        "rating": product.get("rating"),
        "reviews_count": product.get("feedbacks") or product.get("reviewCount"),
        "country": "",
    }


def collect_catalog(config: SearchConfig) -> list[dict[str, Any]]:
    session = build_session()
    page = config.page
    products: list[dict[str, Any]] = []
    seen_articles: set[int] = set()

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
            normalized = normalize_search_product(item)
            article = normalized["article"]
            if not article or article in seen_articles:
                continue
            seen_articles.add(article)
            products.append(normalized)
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
