from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
import re
import textwrap
import xml.etree.ElementTree as ET

from fpdf import FPDF

from automacao_correcao.operations.xml_nfe import NFE_NAMESPACE, get_first_text, xml_files


CODE128_PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
]

PAGE_X = 6
PAGE_W = 198
PAGE_RIGHT = PAGE_X + PAGE_W
CELL_H = 6.5
PRODUCT_ROW_H = 6.5


@dataclass(frozen=True)
class DanfeData:
    key: str
    emit_name: str
    emit_fantasy: str
    emit_cnpj: str
    emit_ie: str
    emit_iest: str
    emit_address: str
    dest_name: str
    dest_doc: str
    dest_ie: str
    dest_address: str
    dest_bairro: str
    dest_cep: str
    dest_city: str
    dest_phone: str
    dest_uf: str
    operation: str
    operation_code: str
    number: str
    series: str
    emission_date: str
    exit_date: str
    exit_time: str
    protocol: str
    protocol_date: str
    totals: dict[str, str]
    transport: dict[str, str]
    references: list[str]
    observation: str
    products: list[dict[str, str]]


def safe_text(value: object) -> str:
    text = "" if value is None else str(value)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def money(value: str) -> str:
    if value in {None, ""}:
        return "0,00"
    try:
        return f"{float(str(value)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return str(value)


def decimal_text(value: str, decimals: int = 2) -> str:
    if not value:
        return ""
    try:
        return f"{float(str(value)):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return str(value)


def date_text(value: str) -> str:
    if not value:
        return ""
    date_part = value[:10]
    if "-" not in date_part:
        return date_part
    parts = date_part.split("-")
    return "/".join(parts[::-1])


def time_text(value: str) -> str:
    if not value or "T" not in value:
        return ""
    return value.split("T", 1)[1][:8]


def format_key(key: str) -> str:
    clean = digits(key)
    return " ".join(clean[index : index + 4] for index in range(0, len(clean), 4))


def format_doc(value: str) -> str:
    clean = digits(value)
    if len(clean) == 14:
        return f"{clean[:2]}.{clean[2:5]}.{clean[5:8]}/{clean[8:12]}-{clean[12:]}"
    if len(clean) == 11:
        return f"{clean[:3]}.{clean[3:6]}.{clean[6:9]}-{clean[9:]}"
    return value


def format_cep(value: str) -> str:
    clean = digits(value)
    return f"{clean[:5]}-{clean[5:]}" if len(clean) == 8 else value


def format_phone(value: str) -> str:
    clean = digits(value)
    if len(clean) == 10:
        return f"({clean[:2]}) {clean[2:6]}-{clean[6:]}"
    if len(clean) == 11:
        return f"({clean[:2]}) {clean[2:7]}-{clean[7:]}"
    return value


def format_nf_number(value: str) -> str:
    clean = digits(value)
    return f"{int(clean):09,d}".replace(",", ".") if clean else value


def find_inf_nfe(root: ET.Element) -> ET.Element:
    inf_nfe = root.find(".//nfe:infNFe", NFE_NAMESPACE)
    if inf_nfe is None:
        raise ValueError("XML nao parece ser uma NF-e: tag infNFe nao encontrada.")
    return inf_nfe


def find_text_any(element: ET.Element, paths: list[str]) -> str:
    for path in paths:
        value = get_first_text(element, path)
        if value:
            return value
    return ""


def address_text(parent: ET.Element, prefix: str) -> str:
    street = get_first_text(parent, f"{prefix}/nfe:xLgr")
    number = get_first_text(parent, f"{prefix}/nfe:nro")
    return ", ".join(part for part in [street, number] if part)


def emit_address_text(parent: ET.Element) -> str:
    bairro = get_first_text(parent, "nfe:emit/nfe:enderEmit/nfe:xBairro")
    city = get_first_text(parent, "nfe:emit/nfe:enderEmit/nfe:xMun")
    uf = get_first_text(parent, "nfe:emit/nfe:enderEmit/nfe:UF")
    cep = format_cep(get_first_text(parent, "nfe:emit/nfe:enderEmit/nfe:CEP"))
    phone = format_phone(get_first_text(parent, "nfe:emit/nfe:enderEmit/nfe:fone"))
    lines = [
        address_text(parent, "nfe:emit/nfe:enderEmit"),
        " - ".join(part for part in [bairro, f"CEP: {cep}" if cep else ""] if part),
        " ".join(part for part in [city, "-", uf, f"Fone: {phone}" if phone else ""] if part),
    ]
    return "\n".join(line for line in lines if line.strip())


def matching_xml_files_by_observation(
    input_path: str | Path,
    search_text: str,
    *,
    case_sensitive: bool = False,
) -> list[Path]:
    needle = search_text.strip()
    comparable_needle = needle if case_sensitive else needle.casefold()
    matches: list[Path] = []

    for xml_file in xml_files(input_path):
        root = ET.parse(xml_file).getroot()
        inf_nfe = find_inf_nfe(root)
        observation = get_first_text(inf_nfe, "nfe:infAdic/nfe:infCpl")
        comparable_observation = observation if case_sensitive else observation.casefold()
        if comparable_needle in comparable_observation:
            matches.append(xml_file)

    return matches


def collect_products(inf_nfe: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for detail in inf_nfe.findall("nfe:det", NFE_NAMESPACE):
        product = detail.find("nfe:prod", NFE_NAMESPACE)
        if product is None:
            continue
        rows.append(
            {
                "codigo": get_first_text(product, "nfe:cProd"),
                "descricao": get_first_text(product, "nfe:xProd"),
                "ncm": get_first_text(product, "nfe:NCM"),
                "cst": find_text_any(detail, [".//nfe:CST", ".//nfe:CSOSN"]),
                "cfop": get_first_text(product, "nfe:CFOP"),
                "un": get_first_text(product, "nfe:uCom"),
                "qtd": get_first_text(product, "nfe:qCom"),
                "valor_unit": get_first_text(product, "nfe:vUnCom"),
                "valor_total": get_first_text(product, "nfe:vProd"),
                "bc_icms": find_text_any(detail, [".//nfe:ICMS00/nfe:vBC", ".//nfe:ICMS20/nfe:vBC", ".//nfe:ICMS90/nfe:vBC", ".//nfe:vBC"]),
                "valor_icms": find_text_any(detail, [".//nfe:ICMS00/nfe:vICMS", ".//nfe:ICMS20/nfe:vICMS", ".//nfe:ICMS90/nfe:vICMS", ".//nfe:vICMS"]),
                "valor_ipi": find_text_any(detail, [".//nfe:IPITrib/nfe:vIPI"]),
                "aliq_icms": find_text_any(detail, [".//nfe:pICMS"]),
                "aliq_ipi": find_text_any(detail, [".//nfe:IPITrib/nfe:pIPI"]),
            }
        )
    return rows


def collect_references(inf_nfe: ET.Element) -> list[str]:
    return [node.text.strip() for node in inf_nfe.findall(".//nfe:NFref/nfe:refNFe", NFE_NAMESPACE) if node.text]


def parse_danfe_data(xml_path: str | Path) -> DanfeData:
    root = ET.parse(xml_path).getroot()
    inf_nfe = find_inf_nfe(root)
    key = inf_nfe.attrib.get("Id", "").replace("NFe", "") or get_first_text(root, ".//nfe:infProt/nfe:chNFe")
    dh_emi = get_first_text(inf_nfe, "nfe:ide/nfe:dhEmi") or get_first_text(inf_nfe, "nfe:ide/nfe:dEmi")
    dh_exit = get_first_text(inf_nfe, "nfe:ide/nfe:dhSaiEnt")
    total = inf_nfe.find("nfe:total/nfe:ICMSTot", NFE_NAMESPACE)
    get_total = lambda name: get_first_text(total, f"nfe:{name}") if total is not None else ""
    transport = inf_nfe.find("nfe:transp", NFE_NAMESPACE)
    get_transp = lambda path: get_first_text(transport, path) if transport is not None else ""
    mod_frete = get_transp("nfe:modFrete")
    freight_labels = {
        "0": "0-Por conta Emitente",
        "1": "1-Por conta Destinatario",
        "2": "2-Por conta Terceiros",
        "3": "3-Proprio Remetente",
        "4": "4-Proprio Destinatario",
        "9": "9-Sem frete",
    }

    return DanfeData(
        key=key,
        emit_name=get_first_text(inf_nfe, "nfe:emit/nfe:xNome"),
        emit_fantasy=get_first_text(inf_nfe, "nfe:emit/nfe:xFant"),
        emit_cnpj=get_first_text(inf_nfe, "nfe:emit/nfe:CNPJ"),
        emit_ie=get_first_text(inf_nfe, "nfe:emit/nfe:IE"),
        emit_iest=get_first_text(inf_nfe, "nfe:emit/nfe:IEST"),
        emit_address=emit_address_text(inf_nfe),
        dest_name=get_first_text(inf_nfe, "nfe:dest/nfe:xNome"),
        dest_doc=find_text_any(inf_nfe, ["nfe:dest/nfe:CNPJ", "nfe:dest/nfe:CPF"]),
        dest_ie=get_first_text(inf_nfe, "nfe:dest/nfe:IE"),
        dest_address=address_text(inf_nfe, "nfe:dest/nfe:enderDest"),
        dest_bairro=get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:xBairro"),
        dest_cep=get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:CEP"),
        dest_city=get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:xMun"),
        dest_phone=get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:fone"),
        dest_uf=get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:UF"),
        operation=get_first_text(inf_nfe, "nfe:ide/nfe:natOp"),
        operation_code=get_first_text(inf_nfe, "nfe:ide/nfe:tpNF"),
        number=get_first_text(inf_nfe, "nfe:ide/nfe:nNF"),
        series=get_first_text(inf_nfe, "nfe:ide/nfe:serie"),
        emission_date=date_text(dh_emi),
        exit_date=date_text(dh_exit or dh_emi),
        exit_time=time_text(dh_exit or dh_emi),
        protocol=get_first_text(root, ".//nfe:infProt/nfe:nProt"),
        protocol_date=f"{date_text(get_first_text(root, './/nfe:infProt/nfe:dhRecbto'))} {time_text(get_first_text(root, './/nfe:infProt/nfe:dhRecbto'))}".strip(),
        totals={name: get_total(name) for name in ["vBC", "vICMS", "vBCST", "vST", "vII", "vFCPUFDest", "vFCP", "vPIS", "vProd", "vFrete", "vSeg", "vDesc", "vOutro", "vIPI", "vICMSUFDest", "vTotTrib", "vCOFINS", "vNF"]},
        transport={
            "xNome": get_transp("nfe:transporta/nfe:xNome"),
            "frete": freight_labels.get(mod_frete, mod_frete),
            "antt": get_transp("nfe:veicTransp/nfe:RNTC"),
            "placa": get_transp("nfe:veicTransp/nfe:placa"),
            "uf_veiculo": get_transp("nfe:veicTransp/nfe:UF"),
            "doc": find_text_any(transport, ["nfe:transporta/nfe:CNPJ", "nfe:transporta/nfe:CPF"]) if transport is not None else "",
            "endereco": get_transp("nfe:transporta/nfe:xEnder"),
            "municipio": get_transp("nfe:transporta/nfe:xMun"),
            "uf": get_transp("nfe:transporta/nfe:UF"),
            "ie": get_transp("nfe:transporta/nfe:IE"),
            "qVol": get_transp("nfe:vol/nfe:qVol"),
            "esp": get_transp("nfe:vol/nfe:esp"),
            "marca": get_transp("nfe:vol/nfe:marca"),
            "nVol": get_transp("nfe:vol/nfe:nVol"),
            "pesoB": get_transp("nfe:vol/nfe:pesoB"),
            "pesoL": get_transp("nfe:vol/nfe:pesoL"),
        },
        references=collect_references(inf_nfe),
        observation=get_first_text(inf_nfe, "nfe:infAdic/nfe:infCpl"),
        products=collect_products(inf_nfe),
    )


class DanfePDF(FPDF):
    def __init__(self, data: DanfeData, total_pages: int):
        super().__init__("P", "mm", "A4")
        self.data = data
        self.total_pages = total_pages
        self.set_auto_page_break(False)
        self.set_margins(PAGE_X, 5, PAGE_X)
        self.set_line_width(0.13)
        self.set_draw_color(0, 0, 0)
        self.set_text_color(0, 0, 0)

    def fit(self, text: str, width: float) -> str:
        value = safe_text(text)
        if self.get_string_width(value) <= width:
            return value
        while value and self.get_string_width(value + "...") > width:
            value = value[:-1]
        return value + "..." if value else ""

    def label(self, x: float, y: float, text: str, size: float = 5.3) -> None:
        self.set_xy(x + 1.0, y + 0.65)
        self.set_font("Times", "", size)
        self.cell(1, 2.5, safe_text(text))

    def value(self, x: float, y: float, w: float, h: float, text: str, size: float = 8, bold: bool = True, align: str = "L") -> None:
        self.set_xy(x + 1.0, y + h - 4.25)
        self.set_font("Times", "B" if bold else "", size)
        self.cell(w - 2.0, 3.5, self.fit(text, w - 2.0), 0, 0, align)

    def box(self, x: float, y: float, w: float, h: float, label: str, value: str = "", size: float = 8, align: str = "L", bold: bool = True) -> None:
        self.rect(x, y, w, h)
        self.set_xy(x + 1.0, y + 0.65)
        self.set_font("Times", "", 5.1 if w < 18 else 5.35)
        label_text = safe_text(label)
        if self.get_string_width(label_text) <= w - 2.0:
            self.cell(w - 2.0, 2.2, label_text)
        else:
            words = label_text.split()
            midpoint = max(1, len(words) // 2)
            wrapped = " ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:])
            self.multi_cell(w - 2.0, 1.85, wrapped, 0, "L")
        self.value(x, y, w, h, value, size=size, align=align, bold=bold)

    def title_line(self, x: float, y: float, w: float, title: str) -> None:
        self.set_xy(x, y - 2.7)
        self.set_font("Times", "", 6.8)
        self.cell(w, 2.7, safe_text(title))

    def wrapped_center(self, x: float, y: float, w: float, h: float, text: str, size: float, bold: bool = True) -> None:
        self.rect(x, y, w, h)
        self.set_xy(x + 1, y + 1)
        self.set_font("Times", "B" if bold else "", size)
        self.multi_cell(w - 2, 4.2, safe_text(text), 0, "C")

    def draw_barcode_code128c(self, x: float, y: float, w: float, h: float, key: str) -> None:
        clean = digits(key)
        if len(clean) % 2:
            clean = "0" + clean
        codes = [105] + [int(clean[i : i + 2]) for i in range(0, len(clean), 2)]
        checksum = codes[0] + sum(code * index for index, code in enumerate(codes[1:], start=1))
        codes.append(checksum % 103)
        codes.append(106)
        pattern = "".join(CODE128_PATTERNS[code] for code in codes)
        total_units = sum(int(char) for char in pattern)
        unit_width = w / total_units
        cursor = x
        draw_bar = True
        self.set_fill_color(0, 0, 0)
        for char in pattern:
            segment = int(char) * unit_width
            if draw_bar:
                self.rect(cursor, y, segment, h, "F")
            cursor += segment
            draw_bar = not draw_bar

    def draw_receipt_stub(self) -> None:
        d = self.data
        x, y, w, h = PAGE_X, 5, PAGE_W, 18
        self.rect(x, y, w, h)
        stub_w = 166
        self.line(x + stub_w, y, x + stub_w, y + h)
        self.set_xy(x + 1, y + 1)
        self.set_font("Times", "", 7.0)
        msg = f"Recebemos de {d.emit_name} os produtos e/ou servicos constantes na Nota Fiscal Eletronica indicada abaixo. Emissao: {d.emission_date} Valor Total: {money(d.totals.get('vNF', ''))}"
        self.multi_cell(stub_w - 2, 2.8, safe_text(msg), 0, "L")
        self.set_xy(x + 1, y + 6.4)
        self.set_font("Times", "B", 7.6)
        self.cell(stub_w - 2, 2.8, self.fit(f"Destinatario: {d.dest_name}", stub_w - 3), 0, 0)
        self.line(x, y + 9, x + stub_w, y + 9)
        self.line(x + 82, y + 9, x + 82, y + h)
        self.label(x, y + 9, "DATA DE RECEBIMENTO", 5.6)
        self.label(x + 82, y + 9, "IDENTIFICACAO E ASSINATURA DO RECEBEDOR", 5.6)
        self.set_xy(x + stub_w, y + 1.6)
        self.set_font("Times", "B", 14)
        self.cell(w - stub_w, 4.6, "NF-e", 0, 2, "C")
        self.set_font("Times", "B", 9.2)
        self.cell(w - stub_w, 4.2, safe_text(f"N.: {format_nf_number(d.number)}"), 0, 2, "C")
        self.cell(w - stub_w, 4.2, safe_text(f"Serie: {d.series}"), 0, 2, "C")
        self.line(x, 25.8, x + w, 25.8)

    def draw_header(self, page_no: int) -> float:
        d = self.data
        self.draw_receipt_stub()
        y = 29
        x = PAGE_X
        emit_w = 75
        danfe_w = 30
        right_x = x + emit_w + danfe_w
        right_w = PAGE_W - emit_w - danfe_w
        header_h = 29
        self.rect(x, y, PAGE_W, header_h)
        self.line(x + emit_w, y, x + emit_w, y + header_h)
        self.line(right_x, y, right_x, y + header_h)
        self.line(right_x, y + 16.3, PAGE_RIGHT, y + 16.3)
        self.line(right_x, y + 22.1, PAGE_RIGHT, y + 22.1)
        self.label(x, y, "IDENTIFICACAO DO EMITENTE", 5.9)
        self.set_xy(x + 2, y + 9.2)
        self.set_font("Times", "B", 10.8)
        self.cell(emit_w - 4, 3.8, self.fit(d.emit_name, emit_w - 5), 0, 2, "C")
        self.set_font("Times", "", 7.0)
        self.multi_cell(emit_w - 4, 3.1, safe_text(d.emit_address), 0, "C")
        self.set_xy(x + emit_w + 1, y + 0.7)
        self.set_font("Times", "B", 15.5)
        self.cell(danfe_w - 2, 5, "DANFE", 0, 2, "C")
        self.set_font("Times", "", 6.8)
        self.multi_cell(danfe_w - 2, 3.2, "Documento Auxiliar da\nNota Fiscal Eletronica", 0, "C")
        self.set_xy(x + emit_w + 2, y + 12.2)
        self.set_font("Times", "", 7.0)
        self.cell(20, 4, "0 - ENTRADA", 0, 2)
        self.cell(20, 4, "1 - SAIDA", 0, 0)
        self.rect(x + emit_w + 24, y + 13, 4.6, 5.4)
        self.set_xy(x + emit_w + 24, y + 13.8)
        self.set_font("Times", "B", 9.2)
        self.cell(5, 4, d.operation_code or "1", 0, 0, "C")
        self.set_xy(x + emit_w + 1, y + 20)
        self.set_font("Times", "B", 8.7)
        self.cell(danfe_w - 2, 3.1, safe_text(f"N.: {format_nf_number(d.number)}"), 0, 2, "C")
        self.cell(danfe_w - 2, 3.1, safe_text(f"Serie: {d.series}"), 0, 2, "C")
        self.cell(danfe_w - 2, 3.1, safe_text(f"Folha {page_no}/{self.total_pages}"), 0, 2, "C")
        self.draw_barcode_code128c(right_x + 8, y + 3, right_w - 16, 10.8, d.key)
        self.label(right_x, y + 16.3, "CHAVE DE ACESSO", 5.35)
        self.set_xy(right_x + 4, y + 19.2)
        self.set_font("Times", "B", 8.1)
        self.cell(right_w - 8, 3.5, safe_text(format_key(d.key)), 0, 0, "C")
        self.set_xy(right_x + 4, y + 23.1)
        self.set_font("Times", "", 6.8)
        self.multi_cell(right_w - 8, 2.7, "Consulta de autenticidade no portal nacional da NF-e\nwww.nfe.fazenda.gov.br/portal ou no site da Sefaz Autorizadora", 0, "C")

        y = 58
        self.box(x, y, 104, CELL_H, "NATUREZA DA OPERACAO", d.operation, 7.6)
        self.box(x + 104, y, 94, CELL_H, "PROTOCOLO DE AUTORIZACAO", f"{d.protocol} - {d.protocol_date}", 7.6, "C")
        y += CELL_H
        self.box(x, y, 65, CELL_H, "INSCRICAO ESTADUAL", d.emit_ie, 7.6, "C")
        self.box(x + 65, y, 65, CELL_H, "INSCRICAO ESTADUAL DO SUBST. TRIBUTARIO", d.emit_iest, 7.2, "C")
        self.box(x + 130, y, 68, CELL_H, "CNPJ / CPF", format_doc(d.emit_cnpj), 7.6, "C")
        y += 10
        self.title_line(x, y, PAGE_W, "DESTINATARIO / REMETENTE")
        self.box(x, y, 124, CELL_H, "RAZAO SOCIAL", d.dest_name, 7.7)
        self.box(x + 124, y, 43, CELL_H, "CNPJ / CPF", format_doc(d.dest_doc), 7.7, "C")
        self.box(x + 167, y, 31, CELL_H, "DATA DE EMISSAO", d.emission_date, 7.7, "C")
        y += CELL_H
        self.box(x, y, 100, CELL_H, "ENDERECO", d.dest_address, 7.6)
        self.box(x + 100, y, 44, CELL_H, "BAIRRO / DISTRITO", d.dest_bairro, 7.6)
        self.box(x + 144, y, 24, CELL_H, "CEP", format_cep(d.dest_cep), 7.6, "C")
        self.box(x + 168, y, 30, CELL_H, "DATA ENTRADA / SAIDA", d.exit_date, 7.6, "C")
        y += CELL_H
        self.box(x, y, 85, CELL_H, "MUNICIPIO", d.dest_city, 7.6)
        self.box(x + 85, y, 34, CELL_H, "FONE / FAX", format_phone(d.dest_phone), 7.6, "C")
        self.box(x + 119, y, 12, CELL_H, "UF", d.dest_uf, 7.6, "C")
        self.box(x + 131, y, 37, CELL_H, "INSCRICAO ESTADUAL", d.dest_ie, 7.6, "C")
        self.box(x + 168, y, 30, CELL_H, "HORA ENTRADA / SAIDA", d.exit_time, 7.6, "C")
        y += 10
        self.title_line(x, y, PAGE_W, "CALCULO DO IMPOSTO")
        labels = [
            ("BASE CALC. ICMS", "vBC"), ("VALOR ICMS", "vICMS"), ("BASE CALC. ICMS ST", "vBCST"),
            ("VALOR ICMS ST", "vST"), ("V. IMP. IMPORT.", "vII"), ("V. ICMS UF REMET.", "vFCPUFDest"),
            ("VALOR FCP", "vFCP"), ("VALOR PIS", "vPIS"), ("V. TOTAL PRODUTOS", "vProd"),
        ]
        widths = [22, 22, 24, 24, 22, 22, 22, 22, 22]
        cursor = x
        for (label, key), width in zip(labels, widths):
            self.box(cursor, y, width, CELL_H, label, money(d.totals.get(key, "")), 6.8, "R")
            cursor += width
        y += CELL_H
        labels2 = [
            ("VALOR FRETE", "vFrete"), ("VALOR SEGURO", "vSeg"), ("DESCONTO", "vDesc"), ("OUTRAS DESPESAS", "vOutro"),
            ("VALOR IPI", "vIPI"), ("V. ICMS UF DEST.", "vICMSUFDest"), ("V. TOT. TRIB.", "vTotTrib"), ("VALOR COFINS", "vCOFINS"),
            ("VALOR TOTAL NOTA", "vNF"),
        ]
        cursor = x
        for (label, key), width in zip(labels2, widths):
            self.box(cursor, y, width, CELL_H, label, money(d.totals.get(key, "")), 6.8, "R")
            cursor += width
        y += 10
        self.title_line(x, y, PAGE_W, "TRANSPORTADOR / VOLUMES TRANSPORTADOS")
        t = d.transport
        self.box(x, y, 74, CELL_H, "RAZAO SOCIAL", t.get("xNome", ""), 6.8)
        self.box(x + 74, y, 32, CELL_H, "FRETE", t.get("frete", ""), 6.8)
        self.box(x + 106, y, 29, CELL_H, "CODIGO ANTT", t.get("antt", ""), 6.8)
        self.box(x + 135, y, 22, CELL_H, "PLACA DO VEICULO", t.get("placa", ""), 6.8)
        self.box(x + 157, y, 8, CELL_H, "UF", t.get("uf_veiculo", ""), 6.8, "C")
        self.box(x + 165, y, 33, CELL_H, "CNPJ / CPF", format_doc(t.get("doc", "")), 6.8)
        y += CELL_H
        self.box(x, y, 108, CELL_H, "ENDERECO", t.get("endereco", ""), 6.8)
        self.box(x + 108, y, 51, CELL_H, "MUNICIPIO", t.get("municipio", ""), 6.8)
        self.box(x + 159, y, 8, CELL_H, "UF", t.get("uf", ""), 6.8, "C")
        self.box(x + 167, y, 31, CELL_H, "INSCRICAO ESTADUAL", t.get("ie", ""), 6.8)
        y += CELL_H
        vol_widths = [20, 44, 44, 30, 30, 30]
        vol_labels = [("QUANTIDADE", "qVol"), ("ESPECIE", "esp"), ("MARCA", "marca"), ("NUMERACAO", "nVol"), ("PESO BRUTO", "pesoB"), ("PESO LIQUIDO", "pesoL")]
        cursor = x
        for (label, key), width in zip(vol_labels, vol_widths):
            self.box(cursor, y, width, CELL_H, label, t.get(key, ""), 7.0)
            cursor += width
        return y + 10

    def product_header(self, y: float) -> float:
        headers = [
            ("CODIGO\nPROD.", 16), ("DESCRICAO DO PRODUTO / SERVICO", 65), ("NCM/SH", 11), ("CST", 9), ("CFOP", 9),
            ("UN", 7), ("QTD.", 12), ("V.UNIT.", 12), ("V.TOTAL", 12), ("BC ICMS", 12),
            ("V.ICMS", 10), ("V.IPI", 10), ("%ICMS", 7), ("%IPI", 6),
        ]
        self.title_line(PAGE_X, y, PAGE_W, "DADOS DOS PRODUTOS / SERVICOS")
        cursor = PAGE_X
        self.set_font("Times", "", 5.0)
        for label, width in headers:
            self.rect(cursor, y, width, 5.6)
            self.set_xy(cursor + 0.5, y + 0.8)
            self.multi_cell(width - 1, 2.0, safe_text(label), 0, "C")
            cursor += width
        return y + 5.6

    def product_row(self, y: float, product: dict[str, str], h: float = PRODUCT_ROW_H) -> None:
        cols = [
            (product["codigo"], 16, "C"), (product["descricao"], 65, "L"), (product["ncm"], 11, "C"), (product["cst"], 9, "C"),
            (product["cfop"], 9, "C"), (product["un"], 7, "C"), (decimal_text(product["qtd"], 2), 12, "R"),
            (decimal_text(product["valor_unit"], 2), 12, "R"), (money(product["valor_total"]), 12, "R"),
            (money(product["bc_icms"]), 12, "R"), (money(product["valor_icms"]), 10, "R"), (money(product["valor_ipi"]), 10, "R"),
            (decimal_text(product["aliq_icms"], 2), 7, "R"), (decimal_text(product["aliq_ipi"], 2), 6, "R"),
        ]
        cursor = PAGE_X
        self.set_font("Times", "", 5.8)
        for value, width, align in cols:
            self.rect(cursor, y, width, h)
            self.set_xy(cursor + 0.8, y + 1.2)
            if width == 65:
                self.multi_cell(width - 1.6, 2.6, safe_text("\n".join(textwrap.wrap(value, width=40)[:2])), 0, align)
            else:
                self.cell(width - 1.6, 3, self.fit(value, width - 1.6), 0, 0, align)
            cursor += width

    def draw_additional_data(self, y: float) -> None:
        if y > 261:
            y = 261
        self.set_fill_color(255, 255, 255)
        self.rect(PAGE_X, y - 2.8, PAGE_W, 30, "F")
        self.title_line(PAGE_X, y, PAGE_W, "DADOS ADICIONAIS")
        info_w = 149
        self.rect(PAGE_X, y, info_w, 27)
        self.rect(PAGE_X + info_w, y, PAGE_W - info_w, 27)
        self.label(PAGE_X, y, "INFORMACOES COMPLEMENTARES", 5.2)
        self.label(PAGE_X + info_w, y, "RESERVADO AO FISCO", 5.2)
        text = self.data.observation
        if self.data.references:
            text = f"{text} NF-e Ref.: {' '.join(self.data.references)}".strip()
        self.set_xy(PAGE_X + 1, y + 3.8)
        self.set_font("Times", "", 6.2)
        self.multi_cell(info_w - 2, 2.8, safe_text(textwrap.shorten(text, width=720, placeholder="...")), 0, "L")


def estimate_pages(products: list[dict[str, str]]) -> int:
    rows_per_page = 15
    if len(products) <= rows_per_page:
        return 1
    return ceil(len(products) / rows_per_page)


def unique_pdf_path(destination_dir: str | Path, file_name: str) -> Path:
    destination = Path(destination_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    name = file_name.strip() or "DANFEs_Unificados.pdf"
    path = Path(name)
    if path.suffix.lower() != ".pdf":
        path = path.with_suffix(".pdf")
    candidate = destination / path.name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        numbered = destination / f"{stem}_{counter}{suffix}"
        if not numbered.exists():
            return numbered
        counter += 1


def merge_danfe_pdfs(pdf_paths: list[Path], destination_dir: str | Path, file_name: str) -> Path:
    if not pdf_paths:
        raise ValueError("Nenhum PDF gerado com sucesso para unificar.")
    try:
        from pypdf import PdfWriter
    except ImportError as exc:
        raise RuntimeError("A biblioteca pypdf nao esta instalada. Instale com: pip install pypdf") from exc

    output_path = unique_pdf_path(destination_dir, file_name)
    writer = PdfWriter()
    try:
        for pdf_path in pdf_paths:
            writer.append(str(pdf_path))
        with output_path.open("wb") as handle:
            writer.write(handle)
    finally:
        writer.close()
    return output_path


def generate_danfe_pdf(xml_path: str | Path, output_dir: str | Path) -> Path:
    source = Path(xml_path).expanduser()
    destination_dir = Path(output_dir).expanduser()
    destination_dir.mkdir(parents=True, exist_ok=True)
    data = parse_danfe_data(source)
    total_pages = estimate_pages(data.products)
    pdf = DanfePDF(data, total_pages)

    product_index = 0
    for page in range(1, total_pages + 1):
        pdf.add_page()
        start_y = pdf.draw_header(page)
        y = pdf.product_header(start_y)
        rows_available = 15
        page_products = data.products[product_index : product_index + rows_available]
        for product in page_products:
            pdf.product_row(y, product)
            y += PRODUCT_ROW_H
        product_index += len(page_products)
        table_bottom = 265 if page == total_pages else 287
        if y < table_bottom:
            pdf.rect(PAGE_X, y, PAGE_W, table_bottom - y)
            cursor = PAGE_X
            for width in [16, 65, 11, 9, 9, 7, 12, 12, 12, 12, 10, 10, 7]:
                cursor += width
                pdf.line(cursor, y, cursor, table_bottom)
        if page == total_pages:
            pdf.draw_additional_data(table_bottom)

    key = digits(data.key) or source.stem
    output_path = unique_pdf_path(destination_dir, f"{key}.pdf")
    pdf.output(str(output_path))
    return output_path


def generate_danfes_for_reason(
    input_path: str | Path,
    output_dir: str | Path,
    search_text: str,
    *,
    case_sensitive: bool = False,
) -> list[Path]:
    generated: list[Path] = []
    for xml_file in matching_xml_files_by_observation(input_path, search_text, case_sensitive=case_sensitive):
        generated.append(generate_danfe_pdf(xml_file, output_dir))
    return generated


def generate_danfes_for_files(xml_paths: list[Path], output_dir: str | Path) -> list[Path]:
    generated: list[Path] = []
    for xml_file in xml_paths:
        generated.append(generate_danfe_pdf(xml_file, output_dir))
    return generated


def generate_danfes_for_files_safe(xml_paths: list[Path], output_dir: str | Path) -> tuple[list[Path], list[tuple[Path, str]]]:
    generated: list[Path] = []
    errors: list[tuple[Path, str]] = []
    for xml_file in xml_paths:
        try:
            generated.append(generate_danfe_pdf(xml_file, output_dir))
        except Exception as exc:
            errors.append((xml_file, str(exc)))
    return generated, errors
