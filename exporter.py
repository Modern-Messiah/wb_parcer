from __future__ import annotations

import pandas as pd

from settings import FILTERED_CATALOG_FILE, FULL_CATALOG_FILE


def save_excel(products: list[dict]) -> None:
    df = pd.DataFrame(products)
    df.to_excel(FULL_CATALOG_FILE, index=False)

    filtered_df = df[
        (df["rating"].fillna(0) >= 4.5)
        & (df["price"].fillna(0) <= 10000)
        & (df["country"].fillna("").str.lower() == "россия")
    ]
    filtered_df.to_excel(FILTERED_CATALOG_FILE, index=False)
