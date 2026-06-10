import pandas as pd

from automacao_correcao.operations.filter_rows import normalize_series


def remove_rows_by_lookup(
    base_df: pd.DataFrame,
    base_column: str,
    lookup_df: pd.DataFrame,
    lookup_column: str,
    *,
    case_sensitive: bool = False,
) -> pd.DataFrame:
    if base_column not in base_df.columns:
        raise ValueError(f"Coluna nao encontrada na planilha principal: {base_column}")
    if lookup_column not in lookup_df.columns:
        raise ValueError(f"Coluna nao encontrada na planilha de criterios: {lookup_column}")

    base_values = normalize_series(base_df[base_column], case_sensitive=case_sensitive)
    lookup_values = set(
        normalize_series(lookup_df[lookup_column], case_sensitive=case_sensitive)
        .replace("", pd.NA)
        .dropna()
        .unique()
    )
    return base_df.loc[~base_values.isin(lookup_values)].copy()
