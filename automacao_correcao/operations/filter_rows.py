from enum import Enum

import pandas as pd


class MatchMode(str, Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


def normalize_series(series: pd.Series, *, case_sensitive: bool) -> pd.Series:
    normalized = series.fillna("").astype(str).str.strip()
    if not case_sensitive:
        normalized = normalized.str.casefold()
    return normalized


def normalize_values(values: list[str], *, case_sensitive: bool) -> list[str]:
    normalized = [str(value).strip() for value in values]
    if not case_sensitive:
        normalized = [value.casefold() for value in normalized]
    return [value for value in normalized if value]


def build_mask(
    series: pd.Series,
    values: list[str],
    *,
    mode: MatchMode = MatchMode.EXACT,
    case_sensitive: bool = False,
) -> pd.Series:
    normalized_series = normalize_series(series, case_sensitive=case_sensitive)
    normalized_values = normalize_values(values, case_sensitive=case_sensitive)

    if not normalized_values:
        return pd.Series(False, index=series.index)

    if mode == MatchMode.EXACT:
        return normalized_series.isin(normalized_values)

    mask = pd.Series(False, index=series.index)
    for value in normalized_values:
        if mode == MatchMode.CONTAINS:
            mask = mask | normalized_series.str.contains(value, regex=False, na=False)
        elif mode == MatchMode.STARTS_WITH:
            mask = mask | normalized_series.str.startswith(value, na=False)
        elif mode == MatchMode.ENDS_WITH:
            mask = mask | normalized_series.str.endswith(value, na=False)
        else:
            raise ValueError(f"Modo de comparacao invalido: {mode}")
    return mask


def remove_rows_by_values(
    df: pd.DataFrame,
    *,
    column: str,
    values: list[str],
    mode: MatchMode = MatchMode.EXACT,
    case_sensitive: bool = False,
) -> pd.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Coluna nao encontrada: {column}")

    invalid_mask = build_mask(
        df[column],
        values,
        mode=mode,
        case_sensitive=case_sensitive,
    )
    return df.loc[~invalid_mask].copy()
