from __future__ import annotations

import time
from typing import Any

import requests

from settings import BASKET_HOSTS, SEARCH_URL


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
