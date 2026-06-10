from pathlib import Path
from datetime import date
import xml.etree.ElementTree as ET

import pandas as pd

NFE_NAMESPACE = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
NFE_URI = "http://www.portalfiscal.inf.br/nfe"
FIXED_REASON_OPTIONS = ["vencimento", "qualidade", "avaria", "peso", "outros"]


def clean_tag(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def text_value(element: ET.Element) -> str:
    return (element.text or "").strip()


def flatten_element(
    element: ET.Element,
    prefix: str = "",
    name_override: str | None = None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    tag = name_override or clean_tag(element.tag)
    key = f"{prefix}.{tag}" if prefix else tag

    for attr_name, attr_value in element.attrib.items():
        values[f"{key}.@{attr_name}"] = attr_value

    children = list(element)
    if not children:
        value = text_value(element)
        if value:
            values[key] = value
        return values

    repeated_count: dict[str, int] = {}
    for child in children:
        child_tag = clean_tag(child.tag)
        repeated_count[child_tag] = repeated_count.get(child_tag, 0) + 1
        if repeated_count[child_tag] > 1:
            indexed_tag = f"{child_tag}_{repeated_count[child_tag]}"
            values.update(flatten_element(child, key, indexed_tag))
        else:
            values.update(flatten_element(child, key))

    return values


def find_inf_nfe(root: ET.Element) -> ET.Element:
    inf_nfe = root.find(".//nfe:infNFe", NFE_NAMESPACE)
    if inf_nfe is None:
        raise ValueError("XML nao parece ser uma NF-e: tag infNFe nao encontrada.")
    return inf_nfe


def find_protocol(root: ET.Element) -> dict[str, str]:
    inf_prot = root.find(".//nfe:infProt", NFE_NAMESPACE)
    if inf_prot is None:
        return {}
    return {
        key.replace("infProt.", "protocolo.", 1): value
        for key, value in flatten_element(inf_prot).items()
    }


def xml_files(path: str | Path) -> list[Path]:
    target = Path(path).expanduser()
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(target.glob("*.xml"))
    raise ValueError(f"Caminho nao encontrado: {target}")


def nfe_to_rows(xml_path: str | Path) -> list[dict[str, str]]:
    source = Path(xml_path).expanduser()
    root = ET.parse(source).getroot()
    inf_nfe = find_inf_nfe(root)
    protocol = find_protocol(root)

    base: dict[str, str] = {
        "arquivo_xml": source.name,
        "chave_acesso": inf_nfe.attrib.get("Id", "").replace("NFe", ""),
        "infNFe.@Id": inf_nfe.attrib.get("Id", ""),
        "infNFe.@versao": inf_nfe.attrib.get("versao", ""),
    }

    for child in list(inf_nfe):
        if clean_tag(child.tag) in {"det", "Signature"}:
            continue
        values = flatten_element(child)
        base.update(values)

    base.update(protocol)

    rows: list[dict[str, str]] = []
    details = inf_nfe.findall("nfe:det", NFE_NAMESPACE)
    if not details:
        rows.append(base)
        return rows

    for detail in details:
        row = dict(base)
        row["det.@nItem"] = detail.attrib.get("nItem", "")
        for child in list(detail):
            row.update(flatten_element(child))
        rows.append(row)

    return rows


def nfe_folder_to_dataframe(path: str | Path) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for xml_file in xml_files(path):
        rows.extend(nfe_to_rows(xml_file))
    return pd.DataFrame(rows)


def nfe_folder_to_xlsx(input_path: str | Path, output_path: str | Path) -> Path:
    df = nfe_folder_to_dataframe(input_path)
    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(destination, index=False)
    return destination


def month_distance(reference_year: int, reference_month: int, today: date | None = None) -> int:
    current = today or date.today()
    return (current.year - reference_year) * 12 + (current.month - reference_month)


def parse_nfe_key_date(nfe_key: str) -> tuple[int, int]:
    key = str(nfe_key).strip()
    if len(key) < 6 or not key[2:6].isdigit():
        raise ValueError(f"Chave NF-e invalida para extrair data: {nfe_key}")
    year = int(f"20{key[2:4]}")
    month = int(key[4:6])
    return year, month


def get_first_text(element: ET.Element, xpath: str) -> str:
    found = element.find(xpath, NFE_NAMESPACE)
    if found is None:
        return ""
    return text_value(found)


def get_all_texts(element: ET.Element, xpath: str) -> list[str]:
    return [text_value(found) for found in element.findall(xpath, NFE_NAMESPACE) if text_value(found)]


def normalize_text(value: str) -> str:
    return str(value).casefold()


def contains_any(text: str, terms: list[str]) -> bool:
    comparable = normalize_text(text)
    return any(term.casefold() in comparable for term in terms)


def contains_all(text: str, terms: list[str]) -> bool:
    comparable = normalize_text(text)
    return all(term.casefold() in comparable for term in terms)


def nfe_total_value(inf_nfe: ET.Element) -> float:
    value = get_first_text(inf_nfe, "nfe:total/nfe:ICMSTot/nfe:vNF")
    try:
        return float(value)
    except ValueError:
        return 0.0


def nfe_reference_rows(xml_path: str | Path, *, months_limit: int = 5) -> list[dict[str, str | int]]:
    source = Path(xml_path).expanduser()
    root = ET.parse(source).getroot()
    inf_nfe = find_inf_nfe(root)

    source_key = inf_nfe.attrib.get("Id", "").replace("NFe", "")
    inf_cpl = get_first_text(inf_nfe, "nfe:infAdic/nfe:infCpl")
    source_number = get_first_text(inf_nfe, "nfe:ide/nfe:nNF")
    source_date = get_first_text(inf_nfe, "nfe:ide/nfe:dhEmi")
    emit_cnpj = get_first_text(inf_nfe, "nfe:emit/nfe:CNPJ")
    emit_name = get_first_text(inf_nfe, "nfe:emit/nfe:xNome")
    dest_cnpj = get_first_text(inf_nfe, "nfe:dest/nfe:CNPJ")
    dest_name = get_first_text(inf_nfe, "nfe:dest/nfe:xNome")
    dest_uf = get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:UF")
    total_value = nfe_total_value(inf_nfe)

    rows: list[dict[str, str | int]] = []
    for reference in get_all_texts(inf_nfe, ".//nfe:NFref/nfe:refNFe"):
        ref_year, ref_month = parse_nfe_key_date(reference)
        age_months = month_distance(ref_year, ref_month)
        rows.append(
            {
                "arquivo_xml": source.name,
                "chave_acesso": source_key,
                "numero_nota": source_number,
                "data_emissao": source_date,
                "emit_cnpj": emit_cnpj,
                "emit_nome": emit_name,
                "dest_cnpj": dest_cnpj,
                "dest_nome": dest_name,
                "dest_uf": dest_uf,
                "valor_total_nota": total_value,
                "referencia_chave": reference,
                "referencia_numero": reference[-17:-10],
                "referencia_ano": ref_year,
                "referencia_mes": ref_month,
                "referencia_idade_meses": age_months,
                "referencia_antiga": "sim" if age_months > months_limit else "nao",
                "classificacao_por_idade": "vencimento" if age_months > months_limit else "",
                "infAdic.infCpl": inf_cpl,
            }
        )
    return rows


def old_references_to_dataframe(input_path: str | Path, *, months_limit: int = 5) -> pd.DataFrame:
    rows: list[dict[str, str | int]] = []
    for xml_file in xml_files(input_path):
        rows.extend(nfe_reference_rows(xml_file, months_limit=months_limit))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df[df["referencia_idade_meses"] > months_limit].copy()


def old_references_to_xlsx(
    input_path: str | Path,
    output_path: str | Path,
    *,
    months_limit: int = 5,
) -> Path:
    df = old_references_to_dataframe(input_path, months_limit=months_limit)
    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(destination, index=False)
    return destination


def search_inf_cpl_to_dataframe(
    input_path: str | Path,
    search_text: str,
    *,
    case_sensitive: bool = False,
) -> pd.DataFrame:
    df = nfe_folder_to_dataframe(input_path)
    if df.empty or "infAdic.infCpl" not in df.columns:
        return pd.DataFrame()

    values = df["infAdic.infCpl"].fillna("").astype(str)
    needle = search_text.strip()
    if not case_sensitive:
        values = values.str.casefold()
        needle = needle.casefold()

    return df[values.str.contains(needle, regex=False, na=False)].copy()


def reference_rows_when_inf_cpl_matches(
    input_path: str | Path,
    search_text: str,
    *,
    case_sensitive: bool = False,
    months_limit: int = 5,
) -> pd.DataFrame:
    rows: list[dict[str, str | int]] = []
    needle = search_text.strip()
    comparable_needle = needle if case_sensitive else needle.casefold()

    for xml_file in xml_files(input_path):
        xml_rows = nfe_reference_rows(xml_file, months_limit=months_limit)
        if not xml_rows:
            continue

        inf_cpl = str(xml_rows[0].get("infAdic.infCpl", ""))
        comparable_inf_cpl = inf_cpl if case_sensitive else inf_cpl.casefold()
        if comparable_needle not in comparable_inf_cpl:
            continue

        for row in xml_rows:
            rows.append(
                {
                    "motivo_buscado": needle,
                    "chave_acesso_nota": row["chave_acesso"],
                    "referencia_chave": row["referencia_chave"],
                    "referencia_ano": row["referencia_ano"],
                    "referencia_mes": row["referencia_mes"],
                    "UF": row["dest_uf"],
                    "Cliente": row["dest_nome"],
                    "Observacao": row["infAdic.infCpl"],
                }
            )

    return pd.DataFrame(rows)


def row_matches_fixed_reason(row: dict[str, str | int], reason: str) -> bool:
    observation = str(row["infAdic.infCpl"])
    age_months = int(row["referencia_idade_meses"])
    total_value = float(row.get("valor_total_nota", 0) or 0)

    if reason == "vencimento":
        return contains_any(observation, ["troca"]) or 4 <= age_months <= 6
    if reason == "qualidade":
        return contains_any(observation, ["qualid", "impropri", "condicoes"]) or age_months <= 3
    if reason == "avaria":
        return contains_any(observation, ["avaria"])
    if reason == "peso":
        return contains_any(observation, ["diferenca", "falt"]) and total_value < 50

    raise ValueError(f"Motivo fixo invalido: {reason}")


def compact_reference_row(row: dict[str, str | int], reason: str) -> dict[str, str | int | float]:
    return {
        "motivo_buscado": reason,
        "chave_acesso_nota": row["chave_acesso"],
        "referencia_chave": row["referencia_chave"],
        "referencia_ano": row["referencia_ano"],
        "referencia_mes": row["referencia_mes"],
        "UF": row["dest_uf"],
        "Cliente": row["dest_nome"],
        "Observacao": row["infAdic.infCpl"],
    }


def fixed_reason_reference_rows(input_path: str | Path, reason: str) -> pd.DataFrame:
    if reason not in FIXED_REASON_OPTIONS or reason == "outros":
        raise ValueError("Use um motivo fixo: vencimento, qualidade, avaria ou peso.")

    rows: list[dict[str, str | int | float]] = []
    for xml_file in xml_files(input_path):
        xml_rows = nfe_reference_rows(xml_file)
        matched_rows = [row for row in xml_rows if row_matches_fixed_reason(row, reason)]
        for row in matched_rows:
            rows.append(compact_reference_row(row, reason))

    return pd.DataFrame(rows)


def fixed_reason_xml_files(input_path: str | Path, reason: str) -> list[Path]:
    if reason not in FIXED_REASON_OPTIONS or reason == "outros":
        raise ValueError("Use um motivo fixo: vencimento, qualidade, avaria ou peso.")

    matches: list[Path] = []
    for xml_file in xml_files(input_path):
        xml_rows = nfe_reference_rows(xml_file)
        if any(row_matches_fixed_reason(row, reason) for row in xml_rows):
            matches.append(xml_file)
    return matches


def fixed_reason_reference_rows_to_xlsx(input_path: str | Path, output_path: str | Path, reason: str) -> Path:
    df = fixed_reason_reference_rows(input_path, reason)
    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(destination, index=False)
    return destination


def reference_rows_when_inf_cpl_matches_to_xlsx(
    input_path: str | Path,
    output_path: str | Path,
    search_text: str,
    *,
    case_sensitive: bool = False,
    months_limit: int = 5,
) -> Path:
    df = reference_rows_when_inf_cpl_matches(
        input_path,
        search_text,
        case_sensitive=case_sensitive,
        months_limit=months_limit,
    )
    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(destination, index=False)
    return destination


def search_inf_cpl_to_xlsx(
    input_path: str | Path,
    output_path: str | Path,
    search_text: str,
    *,
    case_sensitive: bool = False,
) -> Path:
    df = search_inf_cpl_to_dataframe(
        input_path,
        search_text,
        case_sensitive=case_sensitive,
    )
    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(destination, index=False)
    return destination
