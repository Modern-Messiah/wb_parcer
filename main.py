from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
from settings import ERROR_LOG_FILE, FILTERED_CATALOG_FILE, FULL_CATALOG_FILE, SearchConfig
from wb_api import (
    build_session,
    fetch_product_card,
    fetch_search_page,
    product_path_parts,
)


def clear_error_log() -> None:
    with open(ERROR_LOG_FILE, "w", encoding="utf-8") as file:
        file.write("")


def append_error_log(message: str) -> None:
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(message + "\n")


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
    clear_error_log()
    page = config.page
    products: list[dict[str, Any]] = []
    seen_articles: set[int] = set()
    host_cache: dict[int, str] = {}
    session = build_session()

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

        page_candidates: list[dict[str, Any]] = []
        for item in page_items:
            article = item.get("id") or item.get("nmId")
            if not article or article in seen_articles:
                continue

            seen_articles.add(article)
            page_candidates.append(item)

        added = 0
        with ThreadPoolExecutor(max_workers=config.card_workers) as executor:
            futures = {
                executor.submit(enrich_product, build_session(), item, host_cache, config): item
                for item in page_candidates
            }
            for future in as_completed(futures):
                item = futures[future]
                article = item.get("id") or item.get("nmId")
                try:
                    products.append(future.result())
                    added += 1
                    print(f"[page {page}] parsed article {article}")
                except Exception as error:
                    message = f"[page {page}] skip article {article}: {error}"
                    print(message)
                    append_error_log(message)

                time.sleep(config.item_delay_seconds)

        if added == 0:
            break

        print(f"Страница {page} обработана, всего товаров: {len(products)}")
        page += 1
        time.sleep(config.page_delay_seconds)

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
