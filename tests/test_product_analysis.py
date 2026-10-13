from pathlib import Path

import pandas as pd

from automacao_correcao.operations.product_analysis import load_catalog


def test_load_catalog_accepts_spreadsheet_column_variants(tmp_path: Path) -> None:
    shelf_path = tmp_path / "produtos.xlsx"
    pd.DataFrame(
        [
            {
                "C�d. Fiscal": 1001001,
                "Produto": "PRATO ESFERICO",
                "Peso L�q.": "1,8Kg",
                "Qtde. Caixa": 3,
                "Shelf (dias)": 180,
            }
        ]
    ).to_excel(shelf_path, index=False)

    catalog = load_catalog(shelf_path)

    assert catalog.loc[0, "codigo_catalogo"] == "1001001"
    assert catalog.loc[0, "produto_catalogo"] == "PRATO ESFERICO"
    assert catalog.loc[0, "peso_kg"] == 1.8
    assert catalog.loc[0, "qtde_caixa_num"] == 3
    assert catalog.loc[0, "shelf_dias_num"] == 180
