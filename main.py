from catalog import collect_catalog
from exporter import save_excel
from settings import FILTERED_CATALOG_FILE, FULL_CATALOG_FILE, SearchConfig

def main() -> None:
    config = SearchConfig()
    products = collect_catalog(config)
    save_excel(products)
    print(f"Собрано товаров: {len(products)}")
    print(f"Файл каталога: {FULL_CATALOG_FILE}")
    print(f"Файл фильтра: {FILTERED_CATALOG_FILE}")


if __name__ == "__main__":
    main()
