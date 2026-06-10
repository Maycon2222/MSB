from pathlib import Path
import re
import xml.etree.ElementTree as ET

from fpdf import FPDF

from automacao_correcao.operations.xml_nfe import NFE_NAMESPACE, clean_tag, get_first_text, xml_files


def safe_text(value: object) -> str:
    text = "" if value is None else str(value)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def money(value: str) -> str:
    if not value:
        return ""
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return value


def date_text(value: str) -> str:
    if not value:
        return ""
    return value[:10].split("-")[::-1] and "/".join(value[:10].split("-")[::-1])


def number_text(value: str, decimals: int = 2) -> str:
    if not value:
        return ""
    try:
        return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return value


def format_key(key: str) -> str:
    clean = re.sub(r"\D", "", key)
    return " ".join(clean[index : index + 4] for index in range(0, len(clean), 4))


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


def join_address(element: ET.Element, prefix: str) -> str:
    parts = [
        get_first_text(element, f"{prefix}/nfe:xLgr"),
        get_first_text(element, f"{prefix}/nfe:nro"),
        get_first_text(element, f"{prefix}/nfe:xBairro"),
        get_first_text(element, f"{prefix}/nfe:xMun"),
        get_first_text(element, f"{prefix}/nfe:UF"),
        get_first_text(element, f"{prefix}/nfe:CEP"),
    ]
    return " - ".join(part for part in parts if part)


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


class DanfePDF(FPDF):
    def colors(self) -> dict[str, tuple[int, int, int]]:
        return {
            "navy": (22, 59, 92),
            "blue": (31, 111, 235),
            "teal": (15, 118, 110),
            "light": (236, 243, 250),
            "soft": (247, 250, 253),
            "border": (135, 150, 170),
            "text": (22, 32, 51),
            "muted": (82, 96, 118),
        }

    def set_rgb(self, name: str, *, fill: bool = False, text: bool = False, draw: bool = False) -> None:
        r, g, b = self.colors()[name]
        if fill:
            self.set_fill_color(r, g, b)
        if text:
            self.set_text_color(r, g, b)
        if draw:
            self.set_draw_color(r, g, b)

    def fit_text(self, text: str, max_width: float) -> str:
        value = safe_text(text)
        if self.get_string_width(value) <= max_width:
            return value
        suffix = "..."
        while value and self.get_string_width(value + suffix) > max_width:
            value = value[:-1]
        return value + suffix if value else ""

    def section(self, x: float, y: float, w: float, title: str) -> float:
        self.set_rgb("navy", fill=True, draw=True)
        self.rect(x, y, w, 6, "F")
        self.set_xy(x + 2, y + 1.3)
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", "B", 7.5)
        self.cell(w - 4, 3.5, safe_text(title), 0, 0)
        self.set_rgb("text", text=True)
        self.set_rgb("border", draw=True)
        return y + 6

    def plain_cell(self, x: float, y: float, w: float, h: float, text: str, size: int = 6.2, bold: bool = False, align: str = "L") -> None:
        self.set_rgb("border", draw=True)
        self.rect(x, y, w, h)
        self.set_xy(x + 1, y + 1.1)
        self.set_rgb("text", text=True)
        self.set_font("Arial", "B" if bold else "", size)
        self.cell(w - 2, h - 2, safe_text(text)[:90], 0, 0, align)

    def cell_text(self, x: float, y: float, w: float, h: float, label: str, value: str, size: int = 8) -> None:
        self.set_rgb("border", draw=True)
        self.set_rgb("soft", fill=True)
        self.rect(x, y, w, h)
        self.set_xy(x + 1.5, y + 1.2)
        self.set_rgb("muted", text=True)
        self.set_font("Arial", "B", 5.6)
        self.cell(w - 3, 3, safe_text(label), 0, 2)
        self.set_rgb("text", text=True)
        self.set_font("Arial", "", size)
        self.cell(w - 3, h - 4, self.fit_text(value, w - 3), 0, 0)

    def multi_box(self, x: float, y: float, w: float, h: float, label: str, value: str, size: int = 7) -> None:
        self.set_rgb("border", draw=True)
        self.rect(x, y, w, h)
        self.set_xy(x + 1.5, y + 1.2)
        self.set_rgb("muted", text=True)
        self.set_font("Arial", "B", 5.8)
        self.cell(w - 3, 3, safe_text(label), 0, 2)
        self.set_rgb("text", text=True)
        self.set_font("Arial", "", size)
        self.multi_cell(w - 3, 3.4, safe_text(value)[:900])

    def header_band(self, x: float, y: float, w: float, h: float, key: str, emit_name: str, operation_type: str) -> None:
        self.set_rgb("navy", fill=True, draw=True)
        self.rect(x, y, w, h, "F")
        self.set_xy(x + 4, y + 5)
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", "B", 14)
        self.multi_cell(78, 6, safe_text(emit_name[:64]), 0, "L")
        self.set_xy(x + 86, y + 4)
        self.set_font("Arial", "B", 22)
        self.cell(42, 9, "DANFE", 0, 2, "C")
        self.set_font("Arial", "", 7)
        self.multi_cell(42, 3.6, "Documento Auxiliar da\nNota Fiscal Eletronica", 0, "C")
        self.set_xy(x + 86, y + 19)
        self.set_font("Arial", "B", 7.4)
        self.cell(42, 4, safe_text(operation_type), 0, 0, "C")
        self.set_xy(x + 138, y + 4)
        self.set_font("Arial", "B", 7)
        self.cell(50, 4, "CHAVE DE ACESSO", 0, 2, "C")
        self.set_font("Arial", "", 7.2)
        self.multi_cell(50, 4, safe_text(format_key(key)), 0, "C")
        self.set_rgb("teal", fill=True)
        self.rect(x, y + h - 4, w, 4, "F")
        self.set_rgb("text", text=True)


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
                "cfop": get_first_text(product, "nfe:CFOP"),
                "un": get_first_text(product, "nfe:uCom"),
                "qtd": get_first_text(product, "nfe:qCom"),
                "valor_unit": get_first_text(product, "nfe:vUnCom"),
                "valor_total": get_first_text(product, "nfe:vProd"),
                "bc_icms": find_text_any(detail, [
                    ".//nfe:vBC",
                    ".//nfe:ICMS00/nfe:vBC",
                    ".//nfe:ICMS20/nfe:vBC",
                    ".//nfe:ICMS90/nfe:vBC",
                ]),
                "valor_icms": find_text_any(detail, [
                    ".//nfe:vICMS",
                    ".//nfe:ICMS00/nfe:vICMS",
                    ".//nfe:ICMS20/nfe:vICMS",
                    ".//nfe:ICMS90/nfe:vICMS",
                ]),
                "valor_ipi": find_text_any(detail, [".//nfe:IPITrib/nfe:vIPI"]),
                "aliq_icms": find_text_any(detail, [
                    ".//nfe:pICMS",
                    ".//nfe:ICMS00/nfe:pICMS",
                    ".//nfe:ICMS10/nfe:pICMS",
                    ".//nfe:ICMS20/nfe:pICMS",
                    ".//nfe:ICMS51/nfe:pICMS",
                    ".//nfe:ICMS70/nfe:pICMS",
                    ".//nfe:ICMS90/nfe:pICMS",
                ]),
                "aliq_ipi": find_text_any(detail, [".//nfe:IPITrib/nfe:pIPI"]),
            }
        )
    return rows


def collect_references(inf_nfe: ET.Element) -> str:
    refs = [node.text.strip() for node in inf_nfe.findall(".//nfe:NFref/nfe:refNFe", NFE_NAMESPACE) if node.text]
    return " | ".join(refs)


def product_table_header(pdf: DanfePDF, x: float, y: float, headers: list[tuple[str, float]]) -> float:
    pdf.set_fill_color(225, 232, 241)
    pdf.set_rgb("border", draw=True)
    pdf.set_rgb("text", text=True)
    pdf.set_font("Arial", "B", 6.3)
    pdf.set_xy(x, y)
    for label, col_width in headers:
        pdf.cell(col_width, 6, safe_text(label), 1, 0, "C", True)
    pdf.set_rgb("text", text=True)
    pdf.set_rgb("border", draw=True)
    return y + 6


def generate_danfe_pdf(xml_path: str | Path, output_dir: str | Path) -> Path:
    source = Path(xml_path).expanduser()
    destination_dir = Path(output_dir).expanduser()
    destination_dir.mkdir(parents=True, exist_ok=True)

    root = ET.parse(source).getroot()
    inf_nfe = find_inf_nfe(root)
    key = inf_nfe.attrib.get("Id", "").replace("NFe", "") or source.stem

    pdf = DanfePDF("P", "mm", "A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    margin = 8
    width = 194

    emit_name = get_first_text(inf_nfe, "nfe:emit/nfe:xNome")
    operation_code = get_first_text(inf_nfe, "nfe:ide/nfe:tpNF")
    operation_label = "0 - ENTRADA" if operation_code == "0" else "1 - SAIDA" if operation_code == "1" else operation_code
    pdf.header_band(margin, 8, width, 28, key, emit_name, operation_label)

    y = 40
    nat_op = get_first_text(inf_nfe, "nfe:ide/nfe:natOp")
    protocol = get_first_text(root, ".//nfe:infProt/nfe:nProt")
    receipt_date = get_first_text(root, ".//nfe:infProt/nfe:dhRecbto")
    pdf.cell_text(margin, y, 114, 12, "NATUREZA DA OPERACAO", nat_op, 8.2)
    pdf.cell_text(122, y, 80, 12, "PROTOCOLO DE AUTORIZACAO", f"{protocol}  {date_text(receipt_date)}", 8.2)

    y += 14
    pdf.cell_text(margin, y, 54, 11, "INSCRICAO ESTADUAL", get_first_text(inf_nfe, "nfe:emit/nfe:IE"))
    pdf.cell_text(62, y, 58, 11, "CNPJ DO EMITENTE", get_first_text(inf_nfe, "nfe:emit/nfe:CNPJ"))
    pdf.cell_text(120, y, 36, 11, "NUMERO", get_first_text(inf_nfe, "nfe:ide/nfe:nNF"), 9)
    pdf.cell_text(156, y, 46, 11, "DATA EMISSAO", date_text(get_first_text(inf_nfe, "nfe:ide/nfe:dhEmi")), 9)

    y += 15
    y = pdf.section(margin, y, width, "EMITENTE")
    pdf.cell_text(margin, y, 78, 11, "RAZAO SOCIAL", emit_name, 7.2)
    pdf.cell_text(86, y, 40, 11, "CNPJ", get_first_text(inf_nfe, "nfe:emit/nfe:CNPJ"), 7.2)
    pdf.cell_text(126, y, 28, 11, "IE", get_first_text(inf_nfe, "nfe:emit/nfe:IE"), 7.2)
    pdf.cell_text(154, y, 48, 11, "FANTASIA", get_first_text(inf_nfe, "nfe:emit/nfe:xFant"), 7.2)
    y += 11
    pdf.cell_text(margin, y, width, 11, "ENDERECO", join_address(inf_nfe, "nfe:emit/nfe:enderEmit"), 7.2)

    y += 14
    y = pdf.section(margin, y, width, "DESTINATARIO / REMETENTE")
    pdf.cell_text(margin, y, 104, 12, "NOME / RAZAO SOCIAL", get_first_text(inf_nfe, "nfe:dest/nfe:xNome"))
    pdf.cell_text(112, y, 44, 12, "CNPJ / CPF", find_text_any(inf_nfe, ["nfe:dest/nfe:CNPJ", "nfe:dest/nfe:CPF"]))
    pdf.cell_text(156, y, 20, 12, "UF", get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:UF"), 9)
    pdf.cell_text(176, y, 26, 12, "IE", get_first_text(inf_nfe, "nfe:dest/nfe:IE"), 7.2)

    y += 12
    address = join_address(inf_nfe, "nfe:dest/nfe:enderDest")
    pdf.cell_text(margin, y, 104, 12, "ENDERECO", address)
    pdf.cell_text(112, y, 44, 12, "MUNICIPIO", get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:xMun"))
    pdf.cell_text(156, y, 46, 12, "CEP", get_first_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:CEP"))

    y += 15
    y = pdf.section(margin, y, width, "CALCULO DO IMPOSTO")
    total = inf_nfe.find("nfe:total/nfe:ICMSTot", NFE_NAMESPACE)
    get_total = lambda name: get_first_text(total, f"nfe:{name}") if total is not None else ""
    pdf.cell_text(margin, y, 38, 11, "BASE ICMS", money(get_total("vBC")))
    pdf.cell_text(46, y, 38, 11, "VALOR ICMS", money(get_total("vICMS")))
    pdf.cell_text(84, y, 38, 11, "VALOR PRODUTOS", money(get_total("vProd")))
    pdf.cell_text(122, y, 38, 11, "VALOR DESCONTO", money(get_total("vDesc")))
    pdf.cell_text(160, y, 42, 11, "VALOR TOTAL NF", money(get_total("vNF")), 9)

    y += 14
    pdf.cell_text(margin, y, 28, 10, "FRETE", money(get_total("vFrete")), 7.2)
    pdf.cell_text(36, y, 28, 10, "SEGURO", money(get_total("vSeg")), 7.2)
    pdf.cell_text(64, y, 28, 10, "OUTRAS", money(get_total("vOutro")), 7.2)
    pdf.cell_text(92, y, 28, 10, "IPI", money(get_total("vIPI")), 7.2)
    pdf.cell_text(120, y, 28, 10, "PIS", money(get_total("vPIS")), 7.2)
    pdf.cell_text(148, y, 28, 10, "COFINS", money(get_total("vCOFINS")), 7.2)
    pdf.cell_text(176, y, 26, 10, "ICMS DESON.", money(get_total("vICMSDeson")), 7.0)

    y += 13
    y = pdf.section(margin, y, width, "TRANSPORTADOR / VOLUMES")
    pdf.cell_text(margin, y, 32, 10, "MOD. FRETE", get_first_text(inf_nfe, "nfe:transp/nfe:modFrete"), 7.2)
    pdf.cell_text(40, y, 40, 10, "QTD. VOLUMES", get_first_text(inf_nfe, "nfe:transp/nfe:vol/nfe:qVol"), 7.2)
    pdf.cell_text(80, y, 38, 10, "ESPECIE", get_first_text(inf_nfe, "nfe:transp/nfe:vol/nfe:esp"), 7.2)
    pdf.cell_text(118, y, 42, 10, "PESO LIQUIDO", get_first_text(inf_nfe, "nfe:transp/nfe:vol/nfe:pesoL"), 7.2)
    pdf.cell_text(160, y, 42, 10, "PESO BRUTO", get_first_text(inf_nfe, "nfe:transp/nfe:vol/nfe:pesoB"), 7.2)

    y += 13
    y = pdf.section(margin, y, width, "PAGAMENTO")
    pdf.cell_text(margin, y, 46, 10, "TIPO PAGAMENTO", get_first_text(inf_nfe, "nfe:pag/nfe:detPag/nfe:tPag"), 7.2)
    pdf.cell_text(54, y, 46, 10, "VALOR PAGO", money(get_first_text(inf_nfe, "nfe:pag/nfe:detPag/nfe:vPag")), 7.2)
    pdf.cell_text(100, y, 102, 10, "REFERENCIAS NF-E", collect_references(inf_nfe), 5.8)

    y += 15
    y = pdf.section(margin, y, width, "DADOS DOS PRODUTOS / SERVICOS")
    headers = [
        ("COD", 14),
        ("DESCRICAO", 46),
        ("NCM", 15),
        ("CFOP", 11),
        ("UN", 8),
        ("QTD", 14),
        ("V.UNIT", 15),
        ("V.TOTAL", 16),
        ("BC ICMS", 12),
        ("V.ICMS", 12),
        ("V.IPI", 10),
        ("%ICMS", 10),
        ("%IPI", 9),
    ]
    y = product_table_header(pdf, margin, y, headers)

    pdf.set_font("Arial", "", 5.8)
    products = collect_products(inf_nfe)
    pdf.set_y(y)
    for product in products:
        if pdf.get_y() > 238:
            pdf.add_page()
            y = pdf.section(margin, 12, width, "DADOS DOS PRODUTOS / SERVICOS")
            y = product_table_header(pdf, margin, y, headers)
            pdf.set_y(y)
        row_values = [
            product["codigo"][:9],
            product["descricao"][:36],
            product["ncm"],
            product["cfop"],
            product["un"],
            number_text(product["qtd"], 4),
            number_text(product["valor_unit"], 4),
            money(product["valor_total"]),
            money(product["bc_icms"]),
            money(product["valor_icms"]),
            money(product["valor_ipi"]),
            number_text(product["aliq_icms"]),
            number_text(product["aliq_ipi"]),
        ]
        x = margin
        y_row = pdf.get_y()
        heights = 5
        for (value, (_, col_width)) in zip(row_values, headers):
            pdf.set_rgb("border", draw=True)
            pdf.rect(x, y_row, col_width, heights)
            pdf.set_xy(x + 1, y_row + 1.1)
            pdf.cell(col_width - 2, 3, pdf.fit_text(value, col_width - 2), 0, 0)
            x += col_width
        pdf.set_y(y_row + heights)

    obs_y = pdf.get_y() + 8
    if obs_y > 246:
        pdf.add_page()
        obs_y = 14
    obs_y = pdf.section(margin, obs_y, width, "DADOS ADICIONAIS")
    observation = get_first_text(inf_nfe, "nfe:infAdic/nfe:infCpl")
    pdf.multi_box(margin, obs_y, width, 32, "OBSERVACAO", observation, 7.2)

    pdf.set_y(282)
    pdf.set_rgb("muted", text=True)
    pdf.set_font("Arial", "I", 6)
    pdf.cell(0, 4, "Gerado por Automacoes MSB para conferencia interna a partir do XML da NF-e.", 0, 0, "C")
    pdf.set_rgb("text", text=True)

    output_path = destination_dir / f"{key}.pdf"
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
