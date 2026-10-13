from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import textwrap
import xml.etree.ElementTree as ET

from fpdf import FPDF

from automacao_correcao.operations.danfe_pdf import (
    date_text,
    decimal_text,
    digits,
    format_cep,
    format_doc,
    format_key,
    format_phone,
    money,
    safe_text,
    time_text,
    unique_pdf_path,
)


NFSE_NACIONAL_NAMESPACE = "http://www.sped.fazenda.gov.br/nfse"
MAX_XML_BYTES = 10 * 1024 * 1024
PAGE_X = 5
PAGE_W = 200
PAGE_RIGHT = PAGE_X + PAGE_W
GRAY = 242


@dataclass(frozen=True)
class PartyData:
    doc: str = ""
    municipal_registration: str = ""
    phone: str = ""
    name: str = ""
    city: str = ""
    uf: str = ""
    city_code: str = ""
    cep: str = ""
    address: str = ""
    email: str = ""
    simples: str = ""
    sn_regime: str = ""


@dataclass(frozen=True)
class DanfseData:
    key: str
    number: str
    competence: str
    emission_datetime: str
    dps_number: str
    dps_series: str
    dps_emission_datetime: str
    issuer: str
    status: str
    purpose: str
    environment: str
    issue_location: str
    service_location: str
    incidence_city: str
    incidence_code: str
    provider: PartyData
    taker: PartyData | None
    recipient: PartyData | None
    intermediary: PartyData | None
    national_tax_code: str
    municipal_tax_code: str
    nbs_code: str
    national_tax_description: str
    municipal_tax_description: str
    nbs_description: str
    service_description: str
    issqn: dict[str, str]
    federal: dict[str, str]
    ibs_cbs: dict[str, str]
    totals: dict[str, str]
    additional_info: str


class UnsupportedDanfseLayoutError(ValueError):
    pass


def _read_xml_text(xml_path: str | Path) -> str:
    source = Path(xml_path).expanduser()
    if source.suffix.lower() != ".xml":
        raise ValueError("Arquivo nao e XML.")
    if source.stat().st_size == 0:
        raise ValueError("XML vazio.")
    if source.stat().st_size > MAX_XML_BYTES:
        raise ValueError("XML muito grande para processamento seguro.")
    content = source.read_text(encoding="utf-8-sig", errors="ignore")
    lowered = content[:4096].lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("XML rejeitado por conter DOCTYPE ou entidade externa.")
    return content


def safe_parse_xml(xml_path: str | Path) -> ET.Element:
    content = _read_xml_text(xml_path)
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("XML invalido ou malformado.") from exc


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def namespace_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def child(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    for node in list(parent):
        if local_name(node.tag) == name:
            return node
    return None


def find_path(parent: ET.Element | None, path: str) -> ET.Element | None:
    node = parent
    for part in path.split("/"):
        node = child(node, part)
        if node is None:
            return None
    return node


def text_at(parent: ET.Element | None, path: str) -> str:
    node = find_path(parent, path)
    return (node.text or "").strip() if node is not None and node.text else ""


def first_text(parent: ET.Element | None, paths: list[str]) -> str:
    for path in paths:
        value = text_at(parent, path)
        if value:
            return value
    return ""


def find_first(root: ET.Element, name: str) -> ET.Element | None:
    for node in root.iter():
        if local_name(node.tag) == name:
            return node
    return None


def is_nfse_nacional(root: ET.Element) -> bool:
    inf_nfse = find_first(root, "infNFSe")
    if inf_nfse is None:
        return False
    key = digits(inf_nfse.attrib.get("Id", ""))
    return local_name(root.tag) == "NFSe" and namespace_uri(root.tag) == NFSE_NACIONAL_NAMESPACE and len(key) == 50


def find_inf_nfse(root: ET.Element) -> ET.Element:
    if not is_nfse_nacional(root):
        if find_first(root, "infNFSe") is not None:
            raise UnsupportedDanfseLayoutError("Leiaute de NFS-e ainda nao suportado.")
        raise ValueError("XML nao reconhecido como NFS-e Nacional.")
    inf_nfse = find_first(root, "infNFSe")
    if inf_nfse is None:
        raise ValueError("XML nao reconhecido como NFS-e Nacional.")
    return inf_nfse


def _date_time(value: str) -> str:
    if not value:
        return ""
    date = date_text(value)
    hour = time_text(value)
    return f"{date} {hour}".strip()


def _money_or_blank(value: str) -> str:
    return money(value) if value else ""


def _decimal_or_blank(value: str) -> str:
    return decimal_text(value) if value else ""


def _dash(value: str) -> str:
    return value if value else "-"


def _money_or_dash(value: str) -> str:
    return f"R$ {money(value)}" if value else "-"


def _percent_or_dash(value: str) -> str:
    return f"{decimal_text(value)}%" if value else "-"


def _environment_label(value: str) -> str:
    return {"1": "Producao", "2": "Homologacao"}.get(value, value or "Producao")


def _address(parent: ET.Element | None, address_path: str) -> str:
    address = find_path(parent, address_path)
    if address is None:
        return ""
    parts = [
        text_at(address, "xLgr"),
        text_at(address, "nro"),
        text_at(address, "xCpl"),
        text_at(address, "xBairro"),
    ]
    return ", ".join(part for part in parts if part)


def _party(
    base: ET.Element | None,
    *,
    details: ET.Element | None = None,
    address_path: str,
    registration_path: str = "IM",
) -> PartyData | None:
    if base is None and details is None:
        return None
    doc = first_text(base, ["CNPJ", "CPF", "NIF"]) or first_text(details, ["CNPJ", "CPF", "NIF"])
    name = text_at(base, "xNome") or text_at(details, "xNome")
    address = _address(base, address_path) or _address(details, address_path)
    base_address = find_path(base, address_path)
    detail_address = find_path(details, address_path)
    base_national_address = child(base_address, "endNac") or base_address
    detail_national_address = child(detail_address, "endNac") or detail_address
    city = text_at(base_national_address, "xMun") or text_at(detail_national_address, "xMun")
    uf = text_at(base_national_address, "UF") or text_at(detail_national_address, "UF")
    city_code = text_at(base_national_address, "cMun") or text_at(detail_national_address, "cMun")
    cep = text_at(base_national_address, "CEP") or text_at(detail_national_address, "CEP")
    phone = text_at(base, "fone") or text_at(details, "fone")
    email = text_at(base, "email") or text_at(details, "email")
    municipal_registration = text_at(base, registration_path) or text_at(details, registration_path)
    simples = first_text(details, ["regTrib/opSimpNac"]) or first_text(base, ["regTrib/opSimpNac"])
    sn_regime = first_text(details, ["regTrib/regApTribSN"]) or first_text(base, ["regTrib/regApTribSN"])
    if not any([doc, name, address, city, uf, city_code, cep, phone, email, municipal_registration]):
        return None
    return PartyData(
        doc=doc,
        municipal_registration=municipal_registration,
        phone=phone,
        name=name,
        city=city,
        uf=uf,
        city_code=city_code,
        cep=cep,
        address=address,
        email=email,
        simples=simples,
        sn_regime=sn_regime,
    )


def _status_label(value: str) -> str:
    return {"100": "NFS-e Gerada", "101": "Cancelada"}.get(value, value)


def _purpose_label(value: str) -> str:
    return {"0": "Normal", "1": "Substituicao", "2": "Cancelamento"}.get(value, value)


def _retention_label(value: str) -> str:
    return {"1": "Nao retido", "2": "Retido pelo tomador"}.get(value, value)


def parse_danfse_data(xml_path: str | Path) -> DanfseData:
    root = safe_parse_xml(xml_path)
    inf_nfse = find_inf_nfse(root)
    inf_dps = find_first(inf_nfse, "infDPS")
    if inf_dps is None:
        raise UnsupportedDanfseLayoutError("Leiaute de NFS-e ainda nao suportado.")

    key = digits(inf_nfse.attrib.get("Id", ""))
    if len(key) != 50:
        raise ValueError("Chave de acesso da NFS-e invalida.")

    emit_nfse = child(inf_nfse, "emit")
    prest_dps = child(inf_dps, "prest")
    toma = child(inf_dps, "toma")
    dest = child(inf_dps, "dest")
    interm = child(inf_dps, "interm")
    serv = child(inf_dps, "serv")
    cserv = find_path(serv, "cServ")
    valores_nfse = child(inf_nfse, "valores")
    valores_dps = child(inf_dps, "valores")
    trib = child(valores_dps, "trib")
    trib_mun = child(trib, "tribMun")
    trib_fed = child(trib, "tribFed")
    piscofins = child(trib_fed, "piscofins")
    tot_trib = find_path(trib, "totTrib/vTotTrib")
    ibs_cbs_nfse = child(inf_nfse, "IBSCBS")
    ibs_cbs_dps = child(inf_dps, "IBSCBS")
    ibs_values = child(ibs_cbs_nfse, "valores")
    ibs_total = child(ibs_cbs_nfse, "totCIBS")

    provider = _party(emit_nfse, details=prest_dps, address_path="enderNac")
    if provider is None:
        provider = PartyData()
    taker = _party(toma, address_path="end")
    recipient = _party(dest, address_path="end")
    intermediary = _party(interm, address_path="end")

    additional = first_text(serv, ["infoCompl/xInfComp"])
    approx = []
    for label, value in [
        ("Federais", text_at(tot_trib, "vTotTribFed")),
        ("Estaduais", text_at(tot_trib, "vTotTribEst")),
        ("Municipais", text_at(tot_trib, "vTotTribMun")),
    ]:
        if value:
            approx.append(f"{label}: R$ {money(value)}")
    if approx:
        additional = f"{additional}\nTotais Aproximados dos Tributos: {'; '.join(approx)}".strip()

    return DanfseData(
        key=key,
        number=text_at(inf_nfse, "nNFSe"),
        competence=date_text(text_at(inf_dps, "dCompet")),
        emission_datetime=_date_time(text_at(inf_nfse, "dhProc") or text_at(inf_dps, "dhEmi")),
        dps_number=text_at(inf_dps, "nDPS"),
        dps_series=text_at(inf_dps, "serie"),
        dps_emission_datetime=_date_time(text_at(inf_dps, "dhEmi")),
        issuer=text_at(inf_nfse, "verAplic") or text_at(inf_dps, "verAplic"),
        status=_status_label(text_at(inf_nfse, "cStat")),
        purpose=_purpose_label(first_text(ibs_cbs_dps, ["finNFSe"])),
        environment=text_at(inf_dps, "tpAmb"),
        issue_location=text_at(inf_nfse, "xLocEmi"),
        service_location=text_at(inf_nfse, "xLocPrestacao"),
        incidence_city=text_at(inf_nfse, "xLocIncid"),
        incidence_code=text_at(inf_nfse, "cLocIncid"),
        provider=provider,
        taker=taker,
        recipient=recipient,
        intermediary=intermediary,
        national_tax_code=text_at(cserv, "cTribNac"),
        municipal_tax_code=text_at(cserv, "cTribMun"),
        nbs_code=text_at(cserv, "cNBS"),
        national_tax_description=text_at(inf_nfse, "xTribNac"),
        municipal_tax_description=text_at(inf_nfse, "xTribMun"),
        nbs_description=text_at(inf_nfse, "xNBS"),
        service_description=text_at(cserv, "xDescServ"),
        issqn={
            "type": text_at(trib_mun, "tribISSQN"),
            "incidence": f"{text_at(inf_nfse, 'xLocIncid')} / {text_at(inf_nfse, 'cLocIncid')}".strip(" /"),
            "special_regime": first_text(prest_dps, ["regTrib/regEspTrib"]),
            "deductions": first_text(valores_dps, ["vDescCondIncond/vDescIncond", "vDescIncond"]),
            "bc": text_at(valores_nfse, "vBC"),
            "rate": text_at(valores_nfse, "pAliqAplic") or text_at(trib_mun, "pAliq"),
            "retention": _retention_label(text_at(trib_mun, "tpRetISSQN")),
            "value": text_at(valores_nfse, "vISSQN"),
        },
        federal={
            "irrf": text_at(trib_fed, "vRetIRRF"),
            "prev": text_at(trib_fed, "vRetCP"),
            "social": text_at(trib_fed, "vRetCSLL"),
            "pis": text_at(piscofins, "vPis"),
            "cofins": text_at(piscofins, "vCofins"),
            "pis_cofins_desc": text_at(piscofins, "tpRetPisCofins"),
        },
        ibs_cbs={
            "cst_class": " / ".join(part for part in [first_text(ibs_cbs_dps, ["valores/trib/gIBSCBS/CST"]), first_text(ibs_cbs_dps, ["valores/trib/gIBSCBS/cClassTrib"])] if part),
            "indicator": " / ".join(part for part in [text_at(ibs_cbs_dps, "cIndOp"), text_at(ibs_cbs_nfse, "cLocalidadeIncid"), text_at(ibs_cbs_nfse, "xLocalidadeIncid")] if part),
            "exclusions": text_at(ibs_values, "vCalcReeRepRes"),
            "bc": text_at(ibs_values, "vBC"),
            "rate_reduction": " / ".join(part for part in [first_text(ibs_values, ["uf/pRedAliqUF"]), first_text(ibs_values, ["mun/pRedAliqMun"]), first_text(ibs_values, ["fed/pRedAliqCBS"])] if part),
            "rate_ibs": " / ".join(part for part in [first_text(ibs_values, ["uf/pIBSUF"]), first_text(ibs_values, ["mun/pIBSMun"])] if part),
            "effective_mun": first_text(ibs_values, ["mun/pAliqEfetMun"]),
            "value_mun": first_text(ibs_total, ["gIBS/gIBSMunTot/vIBSMun"]),
            "effective_uf": first_text(ibs_values, ["uf/pAliqEfetUF"]),
            "value_uf": first_text(ibs_total, ["gIBS/gIBSUFTot/vIBSUF"]),
            "value_ibs": first_text(ibs_total, ["gIBS/vIBSTot"]),
            "rate_cbs": first_text(ibs_values, ["fed/pCBS"]),
            "effective_cbs": first_text(ibs_values, ["fed/pAliqEfetCBS"]),
            "value_cbs": first_text(ibs_total, ["gCBS/vCBS"]),
        },
        totals={
            "service": first_text(valores_dps, ["vServPrest/vServ"]) or text_at(valores_nfse, "vBC"),
            "unconditional_discount": first_text(valores_dps, ["vDescCondIncond/vDescIncond", "vDescIncond"]),
            "conditional_discount": first_text(valores_dps, ["vDescCondIncond/vDescCond", "vDescCond"]),
            "retentions": text_at(valores_nfse, "vTotalRet"),
            "net": text_at(valores_nfse, "vLiq"),
            "ibs_cbs": first_text(ibs_total, ["vTotNF"]),
            "net_with_ibs_cbs": first_text(ibs_total, ["vTotNF"]) or text_at(valores_nfse, "vLiq"),
        },
        additional_info=additional,
    )


class DanfsePDF(FPDF):
    def __init__(self, data: DanfseData):
        super().__init__("P", "mm", "A4")
        self.data = data
        self.set_auto_page_break(False)
        self.set_margins(PAGE_X, 4, PAGE_X)
        self.set_line_width(0.16)
        self.set_draw_color(0, 0, 0)
        self.set_text_color(0, 0, 0)

    def fit(self, text: str, width: float) -> str:
        value = safe_text(text)
        if self.get_string_width(value) <= width:
            return value
        while value and self.get_string_width(value + "...") > width:
            value = value[:-1]
        return value + "..." if value else ""

    def section_title(self, x: float, y: float, w: float, title: str) -> None:
        self.set_fill_color(GRAY, GRAY, GRAY)
        self.rect(x, y, w, 3.8, "DF")
        self.set_xy(x + 1, y + 0.55)
        self.set_font("Arial", "B", 5.5)
        self.cell(w - 2, 2.4, safe_text(title), 0, 0)

    def field(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        label: str,
        value: str = "",
        *,
        fill: bool = False,
        align: str = "L",
        value_size: float = 5.5,
    ) -> None:
        if fill:
            self.set_fill_color(GRAY, GRAY, GRAY)
            self.rect(x, y, w, h, "DF")
        else:
            self.rect(x, y, w, h)
        self.set_xy(x + 0.9, y + 0.55)
        self.set_font("Arial", "B", 4.8)
        self.cell(w - 1.8, 2.0, self.fit(label, w - 1.8), 0, 0)
        if value:
            self.set_xy(x + 0.9, y + 2.9)
            self.set_font("Arial", "", value_size)
            self.multi_cell(
                w - 1.8,
                2.25,
                safe_text(textwrap.shorten(value, width=max(12, int(w * 2.7)), placeholder="...")),
                0,
                align,
            )

    def field_row(self, y: float, fields: list[tuple[str, str, float]], h: float = 6.0) -> float:
        x = PAGE_X
        for label, value, width in fields:
            self.field(x, y, width, h, label, value)
            x += width
        return y + h

    def paragraph_box(self, x: float, y: float, w: float, h: float, label: str, value: str, chars: int = 520) -> None:
        self.rect(x, y, w, h)
        start_y = y + 0.7
        if label:
            self.set_xy(x + 1, start_y)
            self.set_font("Arial", "B", 4.8)
            self.cell(w - 2, 2.0, safe_text(label), 0, 0)
            start_y += 2.6
        self.set_xy(x + 1, start_y)
        self.set_font("Arial", "", 5.15)
        self.multi_cell(w - 2, 2.2, safe_text(textwrap.shorten(value or "", width=chars, placeholder="...")), 0, "L")

    def party_block(self, y: float, title: str, party: PartyData | None, missing: str, *, include_regime: bool = False) -> float:
        self.section_title(PAGE_X, y, PAGE_W, title)
        y += 3.8
        if party is None:
            self.field(PAGE_X, y, PAGE_W, 5.2, "", missing, value_size=5.4)
            return y + 5.2
        self.field_row(y, [
            ("CPF / CNPJ / NIF", _dash(format_doc(party.doc)), 70),
            ("INSCRICAO MUNICIPAL", _dash(party.municipal_registration), 65),
            ("TELEFONE", _dash(format_phone(party.phone)), 65),
        ], h=6.0)
        y += 6.0
        self.field_row(y, [
            ("NOME / NOME EMPRESARIAL", _dash(party.name), 100),
            ("MUNICIPIO / UF", _dash(" / ".join(part for part in [party.city, party.uf] if part)), 50),
            ("CODIGO IBGE / CEP", _dash(" / ".join(part for part in [party.city_code, format_cep(party.cep)] if part)), 50),
        ], h=6.0)
        y += 6.0
        self.field_row(y, [
            ("ENDERECO", _dash(party.address), 100),
            ("E-MAIL", _dash(party.email), 100),
        ], h=6.0)
        y += 6.0
        if include_regime:
            self.field_row(y, [
                ("SIMPLES NACIONAL NA COMPETENCIA", _dash(party.simples), 100),
                ("REGIME DE APURACAO PELO SN", _dash(party.sn_regime), 100),
            ], h=6.0)
            y += 6.0
        return y

    def draw_header(self) -> float:
        d = self.data
        y = 4
        self.rect(PAGE_X, y, PAGE_W, 289)
        self.set_fill_color(GRAY, GRAY, GRAY)
        self.rect(PAGE_X, y, PAGE_W, 15.5, "DF")

        logo_x = PAGE_X + 2.2
        self.set_fill_color(49, 83, 151)
        self.rect(logo_x + 0.2, y + 3.1, 1.45, 1.45, "F")
        self.set_fill_color(250, 188, 58)
        self.rect(logo_x + 1.9, y + 3.1, 1.45, 1.45, "F")
        self.set_fill_color(63, 132, 72)
        self.rect(logo_x + 3.6, y + 3.1, 1.45, 1.45, "F")

        self.set_font("Arial", "B", 18)
        nfs_width = self.get_string_width("NFS")
        self.set_text_color(63, 132, 72)
        self.text(logo_x, y + 10.9, "NFS")
        self.set_font("Arial", "B", 16)
        self.set_text_color(49, 83, 151)
        self.text(logo_x + nfs_width - 0.75, y + 10.9, "e")
        self.set_text_color(0, 0, 0)

        self.set_xy(PAGE_X + 38, y + 3.05)
        self.set_font("Arial", "", 4.9)
        self.multi_cell(34, 2.1, "Nota Fiscal de\nServico Eletronica", 0, "L")

        self.set_xy(PAGE_X + 75, y + 2.15)
        self.set_font("Arial", "B", 7.4)
        self.cell(50, 3.8, "DANFSe v2.0", 0, 2, "C")
        self.cell(50, 3.8, "Documento Auxiliar da NFS-e", 0, 2, "C")
        if d.environment == "2":
            self.set_font("Arial", "B", 5.6)
            self.cell(50, 3.1, "NFS-e SEM VALIDADE JURIDICA", 0, 2, "C")

        self.set_xy(PAGE_RIGHT - 31, y + 2.25)
        self.set_font("Arial", "", 5.2)
        self.cell(29, 2.9, _dash(d.issue_location), 0, 2, "R")
        self.cell(29, 2.9, f"Ambiente: {_environment_label(d.environment)}", 0, 2, "R")
        self.cell(29, 2.9, "Tipo: Producao", 0, 2, "R")
        return y + 15.5

    def draw_identification(self, y: float) -> float:
        d = self.data
        self.section_title(PAGE_X, y, PAGE_W, "DADOS DE IDENTIFICACAO DA NFS-e")
        y += 3.8
        left_w = 145
        qr_x = PAGE_X + left_w
        qr_w = PAGE_W - left_w
        qr_h = 42.0
        self.rect(qr_x, y, qr_w, qr_h)
        self.field(PAGE_X, y, left_w, 13.0, "CHAVE DE ACESSO DA NFS-e", d.key, value_size=5.4)
        y += 13.0
        self.field_row(y, [
            ("NUMERO DA NFS-e", _dash(d.number), 48),
            ("COMPETENCIA", _dash(d.competence), 52),
            ("EMISSAO DA NFS-e", _dash(d.emission_datetime), 45),
        ], h=9.0)
        y += 9.0
        self.field_row(y, [
            ("NUMERO DA DPS", _dash(d.dps_number), 48),
            ("SERIE DA DPS", _dash(d.dps_series), 52),
            ("EMISSAO DA DPS", _dash(d.dps_emission_datetime), 45),
        ], h=9.0)
        y += 9.0
        self.field_row(y, [
            ("EMITENTE DA NFS-e", "Prestador", 48),
            ("SITUACAO DA NFS-e", _dash(d.status), 52),
            ("FINALIDADE", _dash(d.purpose), 45),
        ], h=11.0)
        return y + 11.0

    def draw_service(self, y: float) -> float:
        d = self.data
        self.section_title(PAGE_X, y, PAGE_W, "SERVICO PRESTADO")
        y += 3.8
        y = self.field_row(y, [
            ("COD. TRIBUTACAO NACIONAL / MUNICIPAL", _dash(" / ".join(part for part in [d.national_tax_code, d.municipal_tax_code] if part)), 70),
            ("CODIGO NBS", _dash(d.nbs_code), 48),
            ("LOCAL DA PRESTACAO", _dash(d.service_location), 82),
        ], h=8.0)
        desc = " / ".join(part for part in [d.national_tax_description, d.municipal_tax_description, d.nbs_description] if part)
        self.paragraph_box(PAGE_X, y, PAGE_W, 7.0, "", desc, chars=210)
        y += 7.0
        self.paragraph_box(PAGE_X, y, PAGE_W, 14.0, "DESCRICAO DO SERVICO", d.service_description, chars=520)
        return y + 14.0

    def draw_tax_and_totals(self, y: float) -> float:
        d = self.data
        self.section_title(PAGE_X, y, PAGE_W, "TRIBUTACAO MUNICIPAL (ISSQN)")
        y += 3.8
        y = self.field_row(y, [
            ("TIPO DE TRIBUTACAO DO ISSQN", _dash(d.issqn["type"]), 66),
            ("MUNICIPIO / UF / PAIS DA INCIDENCIA", _dash(d.issqn["incidence"]), 67),
            ("REGIME ESPECIAL DE TRIBUTACAO", _dash(d.issqn["special_regime"]), 67),
        ], h=6.0)
        y = self.field_row(y, [
            ("TIPO DE IMUNIDADE", "-", 66),
            ("TOTAL DEDUCOES / REDUCOES", _money_or_dash(d.issqn["deductions"]), 67),
            ("CALCULO DO BENEFICIO", "-", 67),
        ], h=6.0)
        y = self.field_row(y, [
            ("DESCONTO INCONDICIONADO", _money_or_dash(d.totals["unconditional_discount"]), 38),
            ("BC ISSQN", _money_or_dash(d.issqn["bc"]), 35),
            ("ALIQUOTA APLICADA", _percent_or_dash(d.issqn["rate"]), 40),
            ("RETENCAO DO ISSQN", _dash(d.issqn["retention"]), 50),
            ("ISSQN APURADO", _money_or_dash(d.issqn["value"]), 37),
        ], h=6.0)
        self.section_title(PAGE_X, y, PAGE_W, "TRIBUTACAO FEDERAL (EXCETO CBS)")
        y += 3.8
        y = self.field_row(y, [
            ("IRRF", _money_or_dash(d.federal["irrf"]), 66),
            ("CONTRIBUICAO PREVIDENCIARIA - RETIDA", _money_or_dash(d.federal["prev"]), 67),
            ("CONTRIBUICOES SOCIAIS - RETIDAS", _money_or_dash(d.federal["social"]), 67),
        ], h=6.0)
        y = self.field_row(y, [
            ("PIS - DEBITO APURACAO PROPRIA", _money_or_dash(d.federal["pis"]), 66),
            ("COFINS - DEBITO APURACAO PROPRIA", _money_or_dash(d.federal["cofins"]), 67),
            ("DESCRICAO CONTRIB. SOCIAIS - RETIDAS", _dash(d.federal["pis_cofins_desc"]), 67),
        ], h=6.0)
        self.section_title(PAGE_X, y, PAGE_W, "TRIBUTACAO IBS / CBS")
        y += 3.8
        y = self.field_row(y, [
            ("CST / CCLASSTRIB", _dash(d.ibs_cbs["cst_class"]), 66),
            ("IND. OPERACAO / MUNICIPIO INCIDENCIA", _dash(d.ibs_cbs["indicator"]), 67),
            ("EXCLUSOES E REDUCOES DA BC", _money_or_dash(d.ibs_cbs["exclusions"]), 67),
        ], h=6.0)
        y = self.field_row(y, [
            ("BC APOS EXCLUSOES E REDUCOES", _money_or_dash(d.ibs_cbs["bc"]), 66),
            ("RED. ALIQUOTA IBS UF / MUN / CBS", _dash(d.ibs_cbs["rate_reduction"]), 67),
            ("ALIQUOTA IBS UF / MUN", _dash(d.ibs_cbs["rate_ibs"]), 67),
        ], h=6.0)
        y = self.field_row(y, [
            ("ALIQ. EFETIVA MUNICIPAL - IBS", _percent_or_dash(d.ibs_cbs["effective_mun"]), 50),
            ("VALOR APURADO MUNICIPAL - IBS", _money_or_dash(d.ibs_cbs["value_mun"]), 50),
            ("ALIQ. EFETIVA ESTADUAL - IBS", _percent_or_dash(d.ibs_cbs["effective_uf"]), 50),
            ("VALOR APURADO ESTADUAL - IBS", _money_or_dash(d.ibs_cbs["value_uf"]), 50),
        ], h=6.0)
        y = self.field_row(y, [
            ("VALOR TOTAL APURADO - IBS", _money_or_dash(d.ibs_cbs["value_ibs"]), 50),
            ("ALIQUOTA - CBS", _percent_or_dash(d.ibs_cbs["rate_cbs"]), 50),
            ("ALIQUOTA EFETIVA - CBS", _percent_or_dash(d.ibs_cbs["effective_cbs"]), 50),
            ("VALOR TOTAL APURADO - CBS", _money_or_dash(d.ibs_cbs["value_cbs"]), 50),
        ], h=6.0)
        self.section_title(PAGE_X, y, PAGE_W, "VALOR TOTAL DA NFS-e")
        y += 3.8
        y = self.field_row(y, [
            ("VALOR DO SERVICO", _money_or_dash(d.totals["service"]), 50),
            ("DESCONTO INCONDICIONADO", _money_or_dash(d.totals["unconditional_discount"]), 50),
            ("DESCONTO CONDICIONADO", _money_or_dash(d.totals["conditional_discount"]), 50),
            ("TOTAL DAS RETENCOES", _money_or_dash(d.totals["retentions"]), 50),
        ], h=6.0)
        y = self.field_row(y, [
            ("VALOR LIQUIDO DA NFS-e", _money_or_dash(d.totals["net"]), 66),
            ("TOTAL DO IBS/CBS", _money_or_dash(d.totals["ibs_cbs"]), 67),
            ("VALOR LIQUIDO + IBS/CBS", _money_or_dash(d.totals["net_with_ibs_cbs"]), 67),
        ], h=6.0)
        return y

    def draw_additional_and_stub(self, y: float) -> None:
        d = self.data
        self.section_title(PAGE_X, y, PAGE_W, "INFORMACOES COMPLEMENTARES")
        y += 3.8
        box_h = max(18, 293 - y)
        self.rect(PAGE_X, y, PAGE_W, box_h)
        if d.additional_info:
            self.set_xy(PAGE_X + 1, y + 1.0)
            self.set_font("Arial", "", 5.1)
            self.multi_cell(PAGE_W - 2, 2.2, safe_text(textwrap.shorten(d.additional_info, width=760, placeholder="...")), 0, "L")

    def render(self) -> None:
        self.add_page()
        y = self.draw_header()
        y = self.draw_identification(y)
        y = self.party_block(y, "PRESTADOR / FORNECEDOR DA NFS-e", self.data.provider, "PRESTADOR / FORNECEDOR NAO IDENTIFICADO NA NFS-e", include_regime=True)
        y = self.party_block(y, "TOMADOR / ADQUIRENTE DA OPERACAO", self.data.taker, "TOMADOR/ADQUIRENTE DA OPERACAO NAO IDENTIFICADO NA NFS-e")
        y = self.party_block(y, "DESTINATARIO DA OPERACAO", self.data.recipient, "DESTINATARIO DA OPERACAO NAO IDENTIFICADO NA NFS-e")
        y = self.party_block(y, "INTERMEDIARIO DA OPERACAO", self.data.intermediary, "INTERMEDIARIO DA OPERACAO NAO IDENTIFICADO NA NFS-e")
        y = self.draw_service(y)
        y = self.draw_tax_and_totals(y)
        self.draw_additional_and_stub(y)


def generate_danfse_pdf(xml_path: str | Path, output_dir: str | Path) -> Path:
    source = Path(xml_path).expanduser()
    destination = Path(output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    data = parse_danfse_data(source)
    pdf = DanfsePDF(data)
    pdf.render()
    output_path = unique_pdf_path(destination, f"{data.key}.pdf")
    pdf.output(str(output_path))
    return output_path
