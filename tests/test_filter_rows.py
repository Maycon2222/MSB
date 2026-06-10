import pandas as pd

from automacao_correcao.operations.filter_rows import MatchMode, remove_rows_by_values
from automacao_correcao.operations.remove_by_lookup import remove_rows_by_lookup


def test_remove_rows_by_exact_values():
    df = pd.DataFrame({"motivo": ["canceladas", "ok", "erro"], "valor": [1, 2, 3]})

    result = remove_rows_by_values(df, column="motivo", values=["canceladas", "erro"])

    assert result["valor"].tolist() == [2]


def test_remove_rows_by_contains_case_insensitive():
    df = pd.DataFrame({"motivo": ["NF Cancelada", "Aprovada", "cancelamento manual"]})

    result = remove_rows_by_values(
        df,
        column="motivo",
        values=["cancel"],
        mode=MatchMode.CONTAINS,
    )

    assert result["motivo"].tolist() == ["Aprovada"]


def test_remove_rows_by_lookup():
    base = pd.DataFrame({"chave": ["1", "2", "3"], "valor": [10, 20, 30]})
    lookup = pd.DataFrame({"invalidas": ["2", "3"]})

    result = remove_rows_by_lookup(base, "chave", lookup, "invalidas")

    assert result["chave"].tolist() == ["1"]
