from pathlib import Path

import pandas as pd


def load_table(path: str | Path, *, sheet_name: str | int = 0, skiprows: int = 0) -> pd.DataFrame:
    file_path = Path(path).expanduser()
    suffix = file_path.suffix.lower()

    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(file_path, sheet_name=sheet_name, skiprows=skiprows)
    if suffix == ".csv":
        return pd.read_csv(file_path, sep=None, engine="python")

    raise ValueError(f"Formato nao suportado: {file_path.suffix}")


def save_table(df: pd.DataFrame, path: str | Path) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()

    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df.to_excel(output_path, index=False)
        return
    if suffix == ".csv":
        df.to_csv(output_path, index=False)
        return

    raise ValueError(f"Formato de saida nao suportado: {output_path.suffix}")
