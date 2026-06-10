from pathlib import Path
import getpass

from automacao_correcao.operations.bm010 import previous_business_day, run_bm010
from automacao_correcao.core.io import load_table, save_table
from automacao_correcao.operations.csv_converter import csv_to_xlsx
from automacao_correcao.operations.danfe_pdf import generate_danfes_for_reason
from automacao_correcao.operations.filter_rows import MatchMode, remove_rows_by_values
from automacao_correcao.operations.folders import clean_folder
from automacao_correcao.operations.remove_by_lookup import remove_rows_by_lookup
from automacao_correcao.operations.sieg_reports import download_sieg_and_clean_bm026
from automacao_correcao.operations.xml_nfe import (
    nfe_folder_to_xlsx,
    old_references_to_xlsx,
    reference_rows_when_inf_cpl_matches_to_xlsx,
)


def ask_path(message: str, must_exist: bool = True) -> Path:
    while True:
        value = input(message).strip().strip('"')
        path = Path(value).expanduser()
        if not must_exist or path.exists():
            return path
        print("Caminho nao encontrado. Tente novamente.")


def ask_text_list(message: str) -> list[str]:
    value = input(message).strip()
    return [item.strip() for item in value.split(",") if item.strip()]


def ask_skiprows() -> int:
    value = input("Linhas iniciais para ignorar [0]: ").strip()
    return int(value or "0")


def ask_int(message: str, default: int) -> int:
    value = input(f"{message} [{default}]: ").strip()
    return int(value or str(default))


def safe_folder_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {" ", "_", "-"} else "_" for char in value.strip())
    return safe.strip() or "resultado"


def ask_yes_no(message: str, default: bool = False) -> bool:
    suffix = "S/n" if default else "s/N"
    value = input(f"{message} ({suffix}): ").strip().lower()
    if not value:
        return default
    return value in {"s", "sim", "y", "yes"}


def ask_match_mode() -> MatchMode:
    print("Modo de comparacao:")
    print("1 - Igual ao criterio")
    print("2 - Contem o criterio")
    print("3 - Comeca com o criterio")
    print("4 - Termina com o criterio")
    option = input("Escolha: ").strip()
    return {
        "2": MatchMode.CONTAINS,
        "3": MatchMode.STARTS_WITH,
        "4": MatchMode.ENDS_WITH,
    }.get(option, MatchMode.EXACT)


def apagar_invalidos() -> None:
    input_path = ask_path("Planilha de entrada (.xlsx, .xls ou .csv): ")
    output_path = ask_path("Arquivo de saida: ", must_exist=False)
    df = load_table(input_path, skiprows=ask_skiprows())
    print("Colunas disponiveis:")
    print(", ".join(map(str, df.columns)))
    column = input("Coluna usada como criterio: ").strip()
    values = ask_text_list("Valores para remover, separados por virgula: ")
    mode = ask_match_mode()
    case_sensitive = ask_yes_no("Diferenciar maiusculas/minusculas?", default=False)

    result = remove_rows_by_values(
        df,
        column=column,
        values=values,
        mode=mode,
        case_sensitive=case_sensitive,
    )
    save_table(result, output_path)
    print(f"Linhas originais: {len(df)}")
    print(f"Linhas salvas: {len(result)}")
    print(f"Arquivo gerado: {output_path}")


def remover_por_outra_planilha() -> None:
    base_path = ask_path("Planilha principal: ")
    lookup_path = ask_path("Planilha com valores invalidos: ")
    output_path = ask_path("Arquivo de saida: ", must_exist=False)

    print("Planilha principal")
    base = load_table(base_path, skiprows=ask_skiprows())
    print("Planilha de criterios")
    lookup = load_table(lookup_path, skiprows=ask_skiprows())

    print("Colunas da planilha principal:")
    print(", ".join(map(str, base.columns)))
    base_column = input("Coluna da planilha principal: ").strip()

    print("Colunas da planilha de criterios:")
    print(", ".join(map(str, lookup.columns)))
    lookup_column = input("Coluna com os valores invalidos: ").strip()

    result = remove_rows_by_lookup(base, base_column, lookup, lookup_column)
    save_table(result, output_path)
    print(f"Linhas removidas: {len(base) - len(result)}")
    print(f"Arquivo gerado: {output_path}")


def converter_csv() -> None:
    input_path = ask_path("CSV de entrada: ")
    output_path = ask_path("XLSX de saida: ", must_exist=False)
    encoding = input("Encoding [cp1252]: ").strip() or "cp1252"
    sep = input("Separador [;]: ").strip() or ";"
    csv_to_xlsx(input_path, output_path, encoding=encoding, sep=sep)
    print(f"Arquivo gerado: {output_path}")


def limpar_pasta() -> None:
    folder = ask_path("Pasta para limpar: ")
    delete_dirs = ask_yes_no("Apagar subpastas tambem?", default=False)
    removed = clean_folder(folder, delete_dirs=delete_dirs)
    print(f"Itens removidos: {removed}")


def converter_xml_nfe() -> None:
    input_path = ask_path("Arquivo XML ou pasta com XMLs: ")
    output_path = ask_path("Planilha XLSX de saida: ", must_exist=False)
    generated_path = nfe_folder_to_xlsx(input_path, output_path)
    print(f"Arquivo gerado: {generated_path}")


def referencias_antigas_xml() -> None:
    input_path = ask_path("Arquivo XML ou pasta com XMLs: ")
    output_path = ask_path("Planilha XLSX de saida: ", must_exist=False)
    months_limit = ask_int("Referencia antiga acima de quantos meses?", 5)
    generated_path = old_references_to_xlsx(
        input_path,
        output_path,
        months_limit=months_limit,
    )
    print(f"Arquivo gerado: {generated_path}")


def buscar_motivo_xml() -> None:
    input_path = ask_path("Arquivo XML ou pasta com XMLs: ")
    output_path = ask_path("Planilha XLSX de saida: ", must_exist=False)
    search_text = input("Texto para buscar em infAdic.infCpl: ").strip()
    case_sensitive = ask_yes_no("Diferenciar maiusculas/minusculas?", default=False)
    generated_path = reference_rows_when_inf_cpl_matches_to_xlsx(
        input_path,
        output_path,
        search_text,
        case_sensitive=case_sensitive,
    )
    print(f"Arquivo gerado: {generated_path}")
    danfe_dir = generated_path.parent / f"DANFEs_{safe_folder_name(search_text)}"
    generated_danfes = generate_danfes_for_reason(
        input_path,
        danfe_dir,
        search_text,
        case_sensitive=case_sensitive,
    )
    print(f"DANFEs gerados: {len(generated_danfes)}")
    print(f"Pasta dos DANFEs: {danfe_dir}")


def rodar_bm010() -> None:
    target = previous_business_day()
    print(f"O BM010 sera executado com a data {target.strftime('%d/%m/%Y')}.")
    confirm = input("Deseja continuar? (s/N): ").strip().lower()
    if confirm not in {"s", "sim"}:
        print("Operacao cancelada.")
        return
    password = getpass.getpass("Senha do banco de dados: ")
    image_dir = Path(__file__).resolve().parent / "assets" / "bm010_images"
    executed_date = run_bm010(
        image_dir=image_dir,
        database_password=password,
    )
    print(f"BM010 executado com data {executed_date.strftime('%d/%m/%Y')}.")


def buscar_sieg_limpar_bm026() -> None:
    bm026_path = ask_path("Relatorio BM026 / All (.xlsx, .xls ou .csv): ")
    output_path = ask_path("Planilha limpa de saida: ", must_exist=False)
    password = getpass.getpass("Senha do banco de dados: ")
    work_dir = Path(output_path).expanduser().parent / "_sieg_downloads"
    generated = download_sieg_and_clean_bm026(
        bm026_path=bm026_path,
        output_path=output_path,
        work_dir=work_dir,
        database_password=password,
    )
    print(f"Arquivo gerado: {generated.output_path}")
    print(f"Arquivos baixados em: {work_dir}")


def main() -> None:
    actions = {
        "1": apagar_invalidos,
        "2": remover_por_outra_planilha,
        "3": converter_csv,
        "4": limpar_pasta,
        "5": converter_xml_nfe,
        "6": referencias_antigas_xml,
        "7": buscar_motivo_xml,
        "8": rodar_bm010,
        "9": buscar_sieg_limpar_bm026,
    }

    while True:
        print("")
        print("Automacao Correcao")
        print("1 - Apagar invalidos por coluna")
        print("2 - Remover linhas usando outra planilha")
        print("3 - Converter CSV para XLSX")
        print("4 - Limpar pasta")
        print("5 - Converter XML NF-e para XLSX")
        print("6 - Gerar planilha de referencias antigas")
        print("7 - Buscar texto no motivo do XML")
        print("8 - Rodar BM010 com dia util anterior")
        print("9 - Buscar SIEG e limpar BM026")
        print("0 - Sair")
        option = input("Escolha: ").strip()
        if option == "0":
            return
        action = actions.get(option)
        if action is None:
            print("Opcao invalida.")
            continue
        action()
