from __future__ import annotations

from dataclasses import dataclass


SEARCH_QUERY = "пальто из натуральной шерсти"
FULL_CATALOG_FILE = "full_catalog.xlsx"
FILTERED_CATALOG_FILE = "filtered_catalog.xlsx"
ERROR_LOG_FILE = "run_errors.log"
SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v18/search"
BASKET_HOSTS = [f"basket-{index:02d}.wbbasket.ru" for index in range(1, 61)]


@dataclass
class SearchConfig:
    query: str = SEARCH_QUERY
    page: int = 1
    item_delay_seconds: float = 0.05
    page_delay_seconds: float = 2.5
    dest: int = -1257786
    max_retries: int = 6
    card_workers: int = 4
