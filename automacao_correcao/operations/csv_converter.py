from pathlib import Path

import pandas as pd


def csv_to_xlsx(
    input_path: str | Path,
    output_path: str | Path,
    *,
    encoding: str = "cp1252",
    sep: str = ";",
    decimal: str = ",",
) -> None:
    source = Path(input_path).expanduser()
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(source, encoding=encoding, sep=sep, index_col=False, decimal=decimal)
    df.to_excel(destination, index=False)
