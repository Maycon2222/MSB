from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET

import pandas as pd

from automacao_correcao.operations.xml_nfe import (
    NFE_NAMESPACE,
    get_all_texts,
    get_first_text,
    parse_nfe_key_date,
    xml_files,
)


OLD_REFERENCE_MONTHS = 6
EXPIRATION_REFERENCE_MONTHS = 4
WEIGHT_TOLERANCE = 0.05
WEIGHT_REFERENCE_MONTHS_LIMIT = 2
LOGISTICS_VALUE_LIMIT = 650.0

NOTE_REASON_PRIORITY = {
    "Referencia antiga/Vencidos": 400,
    "Vencimento": 300,
    "Qualidade/Avaria": 250,
    "Diferenca de peso": 200,
    "Analise logistica": 100,
}
CHEESE_TERMS = [
    "mussarela",
    "mucarela",
    "mozarela",
    "parmesao",
    "prato",
    "minas",
    "provolone",
    "gouda",
    "estepe",
    "edam",
    "reino",
    "coalho",
    "azul",
    "brie",
    "emmental",
    "queijo",
    "qj",
]

STOPWORDS = {
    "kg",
    "g",
    "gr",
    "cx",
    "un",
    "und",
    "pc",
    "pct",
    "pote",
    "forma",
    "peca",
    "fracionado",
    "frac",
    "fat",
    "fatiado",
    "regina",
    "tradicional",
    "light",
}

NORMALIZATION_REPLACEMENTS = {
    "m lanch": "mini lanche",
    "mlanch": "mini lanche",
    "m lanche": "mini lanche",
    "esf": "esferico",
    "lig": "light",
    "parm": "parmesao",
    "prov": "provolone",
    "muss": "mussarela",
    "mussar": "mussarela",
    "muc": "mussarela",
    "pad": "padrao",
    "frac": "fracionado",
    "rf": "fracionado",
}


@dataclass(frozen=True)
class ProductMatch:
    codigo_catalogo: str
    produto_catalogo: str
    peso_liq: str
    peso_kg: float | None
    qtde_caixa: float | None
    shelf_dias: float | None
    score: float
    metodo: str


def strip_accents(value: object) -> str:
    normalized = unicodedata.normalize("NFD", str(value))
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize(value: object) -> str:
    text = strip_accents(value).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for source, target in NORMALIZATION_REPLACEMENTS.items():
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(value: object) -> set[str]:
    return {token for token in normalize(value).split() if token and token not in STOPWORDS and not token.isdigit()}


def contains_any(value: object, terms: list[str]) -> bool:
    normalized = normalize(value)
    return any(normalize(term) in normalized for term in terms)


def has_word(value: object, word: str) -> bool:
    return re.search(rf"\b{re.escape(normalize(word))}\b", normalize(value)) is not None


def to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        match = re.search(r"\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None


def parse_weight_to_kg(value: object) -> float | None:
    text = strip_accents(value).casefold().replace(",", ".")
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(kg|gr|g)\b", text)
    if matches:
        amount_text, unit = matches[-1]
        amount = float(amount_text)
        return amount / 1000 if unit in {"g", "gr"} else amount
    return to_float(value)


CATALOG_COLUMN_ALIASES = {
    "COD FISCAL": {
        "cod fiscal",
        "codigo fiscal",
        "codigo",
        "cod",
        "c d fiscal",
    },
    "PRODUTO": {
        "produto",
        "descricao",
        "descricao produto",
        "nome produto",
    },
    "PESO LIQ": {
        "peso liq",
        "peso liquido",
        "peso l q",
        "peso",
    },
    "QTDE CAIXA": {
        "qtde caixa",
        "qtd caixa",
        "quantidade caixa",
        "quant caixa",
    },
    "SHELF (DIAS)": {
        "shelf dias",
        "shelf",
        "shelf life",
        "shelf life dias",
        "validade dias",
    },
}


def normalize_column_name(value: object) -> str:
    text = strip_accents(value).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_catalog_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[object, str] = {}
    used: set[str] = set()
    for column in df.columns:
        column_norm = normalize_column_name(column)
        for canonical, aliases in CATALOG_COLUMN_ALIASES.items():
            if canonical in used:
                continue
            if column_norm == normalize_column_name(canonical) or column_norm in aliases:
                renamed[column] = canonical
                used.add(canonical)
                break
    return df.rename(columns=renamed)


def load_catalog(path: str | Path) -> pd.DataFrame:
    source = Path(path).expanduser()
    if source.suffix.lower() == ".json":
        with source.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        df = pd.DataFrame(data)
    else:
        df = pd.read_excel(source, sheet_name=0)

    df = normalize_catalog_columns(df)
    required = {"COD FISCAL", "PRODUTO", "PESO LIQ", "QTDE CAIXA", "SHELF (DIAS)"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Planilha/JSON de shelf sem colunas obrigatorias: {', '.join(sorted(missing))}")

    catalog = df.copy()
    catalog["codigo_catalogo"] = catalog["COD FISCAL"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    catalog["produto_catalogo"] = catalog["PRODUTO"].astype(str)
    catalog["produto_norm"] = catalog["produto_catalogo"].map(normalize)
    catalog["tokens"] = catalog["produto_catalogo"].map(tokens)
    catalog["peso_kg"] = catalog["PESO LIQ"].map(parse_weight_to_kg)
    catalog["qtde_caixa_num"] = catalog["QTDE CAIXA"].map(to_float)
    catalog["shelf_dias_num"] = catalog["SHELF (DIAS)"].map(to_float)
    return catalog


def best_match(codigo_xml: object, descricao_xml: object, catalog: pd.DataFrame) -> ProductMatch | None:
    codigo = str(codigo_xml).replace(".0", "").strip()
    desc_norm = normalize(descricao_xml)
    desc_tokens = tokens(descricao_xml)
    desc_weight = parse_weight_to_kg(descricao_xml)

    candidates = catalog
    method_prefix = "nome"
    if codigo:
        by_code = catalog[catalog["codigo_catalogo"] == codigo]
        if not by_code.empty:
            candidates = by_code
            method_prefix = "codigo+nome"

    best: ProductMatch | None = None
    best_score = -1.0
    for _, row in candidates.iterrows():
        cat_tokens = row["tokens"]
        union = desc_tokens | cat_tokens
        overlap = len(desc_tokens & cat_tokens) / len(union) if union else 0.0
        ratio = SequenceMatcher(None, desc_norm, row["produto_norm"]).ratio()
        score = (overlap * 0.72) + (ratio * 0.28)
        cat_weight = row.get("peso_kg")
        if desc_weight and cat_weight:
            diff = abs(float(desc_weight) - float(cat_weight))
            tolerance = max(float(cat_weight) * 0.15, 0.02)
            score += 0.25 if diff <= tolerance else -0.12
        if method_prefix == "codigo+nome":
            score = max(score, 0.72 if overlap > 0 else 0.5)
        if score > best_score:
            best_score = score
            best = ProductMatch(
                codigo_catalogo=row["codigo_catalogo"],
                produto_catalogo=row["produto_catalogo"],
                peso_liq=str(row["PESO LIQ"]),
                peso_kg=row["peso_kg"],
                qtde_caixa=row["qtde_caixa_num"],
                shelf_dias=row["shelf_dias_num"],
                score=round(float(score), 4),
                metodo=method_prefix,
            )
    return best


def parse_xml_date(value: str) -> date | None:
    if not value:
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text[:19]).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def key_month_start(nfe_key: str) -> date | None:
    try:
        year, month = parse_nfe_key_date(nfe_key)
    except ValueError:
        return None
    return date(year, month, 1)


def month_distance_between(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def days_between(later: date, earlier: date) -> int:
    return max((later - earlier).days, 0)


def get_xml_note(xml_path: Path) -> dict[str, object] | None:
    root = ET.parse(xml_path).getroot()
    inf_nfe = root.find(".//nfe:infNFe", NFE_NAMESPACE)
    if inf_nfe is None:
        return None

    key = inf_nfe.attrib.get("Id", "").replace("NFe", "") or xml_path.stem
    emission_date = parse_xml_date(get_first_text(inf_nfe, "nfe:ide/nfe:dhEmi"))
    if emission_date is None:
        emission_date = parse_xml_date(get_first_text(inf_nfe, "nfe:ide/nfe:dEmi"))
    if emission_date is None:
        emission_date = key_month_start(key)

    observation = get_first_text(inf_nfe, "nfe:infAdic/nfe:infCpl")
    xml_references = get_all_texts(inf_nfe, ".//nfe:NFref/nfe:refNFe")
    observation_references = re.findall(r"\b\d{44}\b", observation)
    references = list(dict.fromkeys(xml_references + observation_references))
    reference_rows = []
    for reference in references:
        reference_date = key_month_start(reference)
        if reference_date is None or emission_date is None:
            continue
        reference_rows.append(
            {
                "referencia": reference,
                "referencia_data": reference_date,
                "idade_referencia_meses": month_distance_between(emission_date, reference_date),
                "idade_referencia_dias": days_between(emission_date, reference_date),
            }
        )

    items: list[dict[str, object]] = []
    for det in inf_nfe.findall("nfe:det", NFE_NAMESPACE):
        prod = det.find("nfe:prod", NFE_NAMESPACE)
        if prod is None:
            continue
        items.append(
            {
                "n_item": det.attrib.get("nItem", ""),
                "codigo_xml": get_first_text(prod, "nfe:cProd"),
                "descricao_xml": get_first_text(prod, "nfe:xProd"),
                "unidade": get_first_text(prod, "nfe:uCom"),
                "quantidade_xml": to_float(get_first_text(prod, "nfe:qCom")),
                "valor_produto": to_float(get_first_text(prod, "nfe:vProd")) or 0.0,
            }
        )

    total_value = to_float(get_first_text(inf_nfe, "nfe:total/nfe:ICMSTot/nfe:vNF"))
    if total_value is None:
        total_value = sum(float(item["valor_produto"] or 0) for item in items)

    return {
        "arquivo_xml": xml_path.name,
        "chave_nota": key,
        "data_xml": emission_date,
        "cliente": get_first_text(inf_nfe, "nfe:dest/nfe:xNome"),
        "uf": get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:UF"),
        "observacao": observation,
        "referencias": references,
        "referencias_detalhe": reference_rows,
        "valor_total": total_value,
        "items": items,
    }


def classify_item(item: dict[str, object], catalog: pd.DataFrame) -> dict[str, object]:
    match = best_match(item.get("codigo_xml", ""), item.get("descricao_xml", ""), catalog)
    result = dict(item)
    result.update(
        {
            "produto_identificado": "",
            "codigo_catalogo": "",
            "peso_catalogo": "",
            "peso_kg": "",
            "qtde_caixa": "",
            "shelf_dias": "",
            "match_score": "",
            "match_metodo": "",
            "status_analise": "incerto",
            "peso_caixa_kg": "",
            "peso_esperado_kg": "",
            "diferenca_peso_kg": "",
            "diferenca_peso_percentual": "",
            "status_peso": "",
        }
    )

    minimum_score = 0.32 if contains_any(item.get("descricao_xml", ""), CHEESE_TERMS) else 0.5
    if match is None or match.score < minimum_score:
        result["status_analise"] = "produto sem match confiavel no shelf"
        return result

    result.update(
        {
            "produto_identificado": match.produto_catalogo,
            "codigo_catalogo": match.codigo_catalogo,
            "peso_catalogo": match.peso_liq,
            "peso_kg": match.peso_kg or "",
            "qtde_caixa": match.qtde_caixa or "",
            "shelf_dias": match.shelf_dias or "",
            "match_score": match.score,
            "match_metodo": match.metodo,
            "status_analise": "analisado",
        }
    )
    return result


def is_box_unit(unit: str) -> bool:
    return unit.startswith("cx")


def is_unit_count_unit(unit: str) -> bool:
    return unit.startswith("un") or unit.startswith("und") or unit.startswith("pc")


def is_integer_quantity(quantity: float) -> bool:
    return abs(quantity - round(quantity)) <= 0.0001


def closes_full_box(unit: str, quantity: float, qtde_caixa: float) -> bool:
    if quantity <= 0:
        return False
    if is_box_unit(unit):
        return is_integer_quantity(quantity)
    if qtde_caixa <= 0:
        return False
    remainder = quantity % qtde_caixa
    return remainder <= 0.0001 or abs(remainder - qtde_caixa) <= 0.0001


def analyze_weight(item: dict[str, object]) -> dict[str, object]:
    quantity = item.get("quantidade_xml")
    peso_kg = item.get("peso_kg")
    qtde_caixa = item.get("qtde_caixa")
    unit = normalize(item.get("unidade", ""))
    if not quantity or not qtde_caixa:
        return item

    quantity = float(quantity)
    qtde_caixa = float(qtde_caixa)
    if not unit.startswith("kg"):
        if (is_box_unit(unit) or is_unit_count_unit(unit)) and closes_full_box(unit, quantity, qtde_caixa):
            item["status_peso"] = "caixa fechada por unidade"
        else:
            item["status_peso"] = "unidade nao e KG"
        return item

    if not peso_kg:
        return item
    peso_kg = float(peso_kg)
    box_weight = peso_kg * qtde_caixa
    item["peso_caixa_kg"] = round(box_weight, 4)
    if box_weight <= 0:
        return item
    if quantity >= box_weight:
        item["status_peso"] = "uma caixa ou mais"
        return item

    max_units = max(int(qtde_caixa) - 1, 1)
    expected_options = [peso_kg * units for units in range(1, max_units + 1)]
    expected = min(expected_options, key=lambda value: abs(quantity - value))
    diff = quantity - expected
    ratio = abs(diff) / expected if expected else 0
    item["peso_esperado_kg"] = round(expected, 4)
    item["diferenca_peso_kg"] = round(diff, 4)
    item["diferenca_peso_percentual"] = round(ratio * 100, 2)
    item["status_peso"] = "diferenca acima de 5%" if ratio > WEIGHT_TOLERANCE else "peso dentro da margem"
    return item


def has_old_reference(note: dict[str, object]) -> bool:
    return any(
        int(ref["idade_referencia_meses"]) >= OLD_REFERENCE_MONTHS
        for ref in note["referencias_detalhe"]
    )


def has_expiration_by_reference_count(note: dict[str, object]) -> bool:
    count = sum(
        1
        for ref in note["referencias_detalhe"]
        if int(ref["idade_referencia_meses"]) > EXPIRATION_REFERENCE_MONTHS
    )
    return count >= 2


def has_expiration_by_shelf(note: dict[str, object], items: list[dict[str, object]]) -> bool:
    reference_days = [int(ref["idade_referencia_dias"]) for ref in note["referencias_detalhe"]]
    if not reference_days:
        return False
    max_reference_days = max(reference_days)
    return any(
        item.get("status_analise") == "analisado"
        and item.get("shelf_dias")
        and max_reference_days > float(item["shelf_dias"])
        for item in items
    )


def has_weight_difference(note: dict[str, object], items: list[dict[str, object]]) -> bool:
    if has_word(note.get("observacao", ""), "diferenca"):
        return True
    if any(item.get("status_peso") == "uma caixa ou mais" for item in items):
        return False
    return any(item.get("status_peso") == "diferenca acima de 5%" for item in items)


def is_close_to_box_multiple(quantity: float, box_quantity: float) -> bool:
    if box_quantity <= 0 or quantity <= 0:
        return False
    nearest_boxes = round(quantity / box_quantity)
    if nearest_boxes < 1:
        return False
    expected = nearest_boxes * box_quantity
    return abs(quantity - expected) / expected <= WEIGHT_TOLERANCE


def duplicate_group_key(note: dict[str, object], item: dict[str, object]) -> tuple[str, str]:
    product_key = str(item.get("codigo_catalogo") or normalize(item.get("produto_identificado", "")))
    reference_key = "|".join(note.get("referencias", []))
    return product_key, reference_key


def mark_duplicate_product_closed_box(note: dict[str, object], items: list[dict[str, object]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for item in items:
        if item.get("status_analise") != "analisado":
            continue
        key = duplicate_group_key(note, item)
        if not key[0] or not key[1]:
            continue
        groups.setdefault(key, []).append(item)

    for group in groups.values():
        if len(group) < 2:
            continue
        first = group[0]
        qtde_caixa = first.get("qtde_caixa")
        total_quantity = sum(float(item.get("quantidade_xml") or 0) for item in group)
        if not qtde_caixa or total_quantity <= 0:
            continue

        unit = normalize(first.get("unidade", ""))
        closes_box = False
        if unit.startswith("kg") and first.get("peso_kg"):
            closes_box = is_close_to_box_multiple(total_quantity, float(first["peso_kg"]) * float(qtde_caixa))
        elif is_box_unit(unit) or is_unit_count_unit(unit):
            closes_box = closes_full_box(unit, total_quantity, float(qtde_caixa))

        if closes_box:
            for item in group:
                item["status_peso"] = "caixa fechada por produto repetido"


def has_closed_unit_box(items: list[dict[str, object]]) -> bool:
    return any(
        item.get("status_peso") in {"caixa fechada por unidade", "caixa fechada por produto repetido"}
        for item in items
    )


def reason_value_totals(note: dict[str, object], items: list[dict[str, object]]) -> dict[str, float]:
    total_value = float(note.get("valor_total") or 0)
    values: dict[str, float] = {}

    if has_old_reference(note):
        values["Referencia antiga/Vencidos"] = total_value

    expiration_by_note = (
        has_expiration_by_reference_count(note)
        or has_word(note.get("observacao", ""), "troca")
    )
    expiration_items_value = sum(
        float(item.get("valor_produto") or 0)
        for item in items
        if item.get("status_analise") == "analisado"
        and item.get("shelf_dias")
        and item.get("idade_referencia_max_dias")
        and float(item["idade_referencia_max_dias"]) > float(item["shelf_dias"])
    )
    if expiration_by_note or expiration_items_value > 0:
        values["Vencimento"] = total_value if expiration_by_note else expiration_items_value

    reference_months = [int(ref["idade_referencia_meses"]) for ref in note["referencias_detalhe"]]
    reference_over_weight_limit = bool(reference_months) and max(reference_months) >= WEIGHT_REFERENCE_MONTHS_LIMIT
    weight_reason = "Qualidade/Avaria" if reference_over_weight_limit else "Diferenca de peso"

    weight_by_observation = has_word(note.get("observacao", ""), "diferenca")
    if weight_by_observation:
        values[weight_reason] = total_value
    elif has_weight_difference(note, items):
        values[weight_reason] = sum(
            float(item.get("valor_produto") or 0)
            for item in items
            if item.get("status_peso") == "diferenca acima de 5%"
        )

    if has_closed_unit_box(items):
        values["Analise logistica"] = total_value

    if not values:
        values["Analise logistica"] = total_value
    return values


def select_note_reason(reason_values: dict[str, float]) -> str:
    if "Analise logistica" in reason_values:
        return "Analise logistica"
    return sorted(
        reason_values,
        key=lambda reason: (float(reason_values[reason]), NOTE_REASON_PRIORITY[reason]),
        reverse=True,
    )[0]


def classify_note(note: dict[str, object], catalog: pd.DataFrame) -> tuple[dict[str, object], list[dict[str, object]]]:
    items = [analyze_weight(classify_item(item, catalog)) for item in note["items"]]
    reference_months = [ref["idade_referencia_meses"] for ref in note["referencias_detalhe"]]
    reference_days = [ref["idade_referencia_dias"] for ref in note["referencias_detalhe"]]
    max_reference_days = max(reference_days) if reference_days else ""
    for item in items:
        item["idade_referencia_max_dias"] = max_reference_days
    mark_duplicate_product_closed_box(note, items)

    reason_values = reason_value_totals(note, items)
    selected_reason = select_note_reason(reason_values)

    note_row = {
        "arquivo_xml": note["arquivo_xml"],
        "chave_nota": note["chave_nota"],
        "data_xml": note["data_xml"].isoformat() if note["data_xml"] else "",
        "cliente": note["cliente"],
        "uf": note["uf"],
        "motivo_sugerido_nota": selected_reason,
        "motivos_encontrados": selected_reason,
        "valor_total": note["valor_total"],
        "acima_650": float(note.get("valor_total") or 0) > LOGISTICS_VALUE_LIMIT,
        "qtd_itens": len(items),
        "qtd_itens_match": sum(1 for item in items if item.get("status_analise") == "analisado"),
        "referencias": " | ".join(note["referencias"]),
        "idade_referencia_max_meses": max(reference_months) if reference_months else "",
        "idade_referencia_max_dias": max(reference_days) if reference_days else "",
        "observacao": note["observacao"],
    }

    for item in items:
        item.update(
            {
                "arquivo_xml": note["arquivo_xml"],
                "chave_nota": note["chave_nota"],
                "motivo_sugerido_nota": selected_reason,
                "motivos_encontrados": selected_reason,
                "idade_referencia_max_meses": note_row["idade_referencia_max_meses"],
                "idade_referencia_max_dias": note_row["idade_referencia_max_dias"],
            }
        )
    return note_row, items


def analyze_xml_products(input_path: str | Path, catalog_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    catalog = load_catalog(catalog_path)
    note_rows: list[dict[str, object]] = []
    item_rows: list[dict[str, object]] = []
    for xml_path in xml_files(input_path):
        note = get_xml_note(xml_path)
        if note is None:
            continue
        note_row, items = classify_note(note, catalog)
        note_rows.append(note_row)
        item_rows.extend(items)
    return pd.DataFrame(note_rows), pd.DataFrame(item_rows)


def analyze_xml_products_to_xlsx(input_path: str | Path, catalog_path: str | Path, output_path: str | Path) -> Path:
    notes, items = analyze_xml_products(input_path, catalog_path)
    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        notes.to_excel(writer, sheet_name="notas_lancamento", index=False)
        items.to_excel(writer, sheet_name="itens_detalhe", index=False)
        uncertain = items[items["status_analise"] != "analisado"].copy() if not items.empty else pd.DataFrame()
        uncertain.to_excel(writer, sheet_name="itens_incertos", index=False)
        if notes.empty:
            summary = pd.DataFrame(columns=["motivo_sugerido_nota", "notas"])
        else:
            summary = notes.groupby("motivo_sugerido_nota").size().reset_index(name="notas")
        summary.to_excel(writer, sheet_name="resumo", index=False)

    return destination











