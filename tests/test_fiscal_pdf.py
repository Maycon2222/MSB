from pathlib import Path
import shutil

import pytest

from automacao_correcao.operations.danfe_pdf import generate_danfe_pdf
from automacao_correcao.operations.danfse_pdf import (
    UnsupportedDanfseLayoutError,
    generate_danfse_pdf,
    parse_danfse_data,
    safe_parse_xml,
)
from automacao_correcao.operations.fiscal_pdf import detect_fiscal_document_type, generate_fiscal_pdf


NFE_KEY = "15260706057223035129553000001633421549243869"
NFSE_KEYS = [
    "35503081253654352000127000000000036626096718891784",
    "42091022253113791001790000000001813626094979617509",
    "33045572236550850000100000000000003926090130073248",
    "33045572236550850000100000000000004026090619231109",
]


def write_nfe(path: Path) -> None:
    path.write_text(
        f"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
<NFe><infNFe Id="NFe{NFE_KEY}" versao="4.00">
<ide><natOp>VENDA</natOp><tpNF>1</tpNF><nNF>123</nNF><serie>1</serie><dhEmi>2026-09-08T10:00:00-03:00</dhEmi></ide>
<emit><CNPJ>12345678000190</CNPJ><xNome>EMITENTE TESTE</xNome><enderEmit><xLgr>RUA A</xLgr><nro>1</nro><xMun>SAO PAULO</xMun><UF>SP</UF></enderEmit></emit>
<dest><CNPJ>19273747000141</CNPJ><xNome>TOMADOR TESTE</xNome><enderDest><xLgr>RUA B</xLgr><nro>2</nro><xMun>RIO</xMun><UF>RJ</UF></enderDest></dest>
<det nItem="1"><prod><cProd>1</cProd><xProd>PRODUTO</xProd><NCM>12345678</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>1</qCom><vUnCom>10.00</vUnCom><vProd>10.00</vProd></prod></det>
<total><ICMSTot><vProd>10.00</vProd><vNF>10.00</vNF></ICMSTot></total>
</infNFe></NFe>
<protNFe><infProt><chNFe>{NFE_KEY}</chNFe></infProt></protNFe>
</nfeProc>""",
        encoding="utf-8",
    )


def write_nfse(path: Path, key: str = NFSE_KEYS[0], description: str = "Prestacao de servicos acentuada") -> None:
    path.write_text(
        f"""<NFSe versao="1.01" xmlns="http://www.sped.fazenda.gov.br/nfse">
<infNFSe Id="NFS{key}">
<xLocEmi>Sao Paulo</xLocEmi><xLocPrestacao>Sao Paulo</xLocPrestacao><nNFSe>366</nNFSe>
<cLocIncid>3550308</cLocIncid><xLocIncid>Sao Paulo</xLocIncid><xTribNac>Planejamento tecnico</xTribNac>
<verAplic>Teste</verAplic><cStat>100</cStat><dhProc>2026-09-08T14:45:02-03:00</dhProc>
<emit><CNPJ>53654352000127</CNPJ><IM>79669093</IM><xNome>ZEROK CONSULTORIA LTDA</xNome>
<enderNac><xLgr>CEL JOSE EUSEBIO</xLgr><nro>95</nro><xBairro>HIGIENOPOLIS</xBairro><cMun>3550308</cMun><UF>SP</UF><CEP>01239030</CEP></enderNac>
<email>david@zerok.tec.br</email></emit>
<valores><vBC>2000.00</vBC><pAliqAplic>5.00</pAliqAplic><vISSQN>100.00</vISSQN><vTotalRet>196.00</vTotalRet><vLiq>1877.00</vLiq></valores>
<DPS versao="1.01"><infDPS Id="DPS355030825365435200012700001000000000000366">
<tpAmb>1</tpAmb><dhEmi>2026-09-08T14:45:02-03:00</dhEmi><serie>1</serie><nDPS>366</nDPS><dCompet>2026-09-08</dCompet>
<prest><CNPJ>53654352000127</CNPJ><IM>79669093</IM><regTrib><opSimpNac>1</opSimpNac><regEspTrib>0</regEspTrib></regTrib></prest>
<toma><CNPJ>19273747000141</CNPJ><xNome>BARBOSA E MARQUES S A</xNome><end><endNac><cMun>3127701</cMun><CEP>35032010</CEP></endNac><xLgr>Aluizio Pereira Esteves</xLgr><nro>250</nro><xBairro>Lourdes</xBairro></end><email>fiscal@example.com</email></toma>
<serv><locPrest><cLocPrestacao>3550308</cLocPrestacao></locPrest><cServ><cTribNac>170301</cTribNac><cTribMun>099</cTribMun><xDescServ>{description}</xDescServ><cNBS>999999999</cNBS></cServ></serv>
<valores><vServPrest><vServ>2000.00</vServ></vServPrest><trib><tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN><pAliq>5.00</pAliq></tribMun><tribFed><piscofins><CST>00</CST><vPis>13.00</vPis><vCofins>60.00</vCofins></piscofins><vRetIRRF>30.00</vRetIRRF><vRetCSLL>93.00</vRetCSLL></tribFed></trib></valores>
</infDPS></DPS>
</infNFSe></NFSe>""",
        encoding="utf-8",
    )


def test_current_nfe_conversion_still_generates_danfe(tmp_path: Path) -> None:
    xml_path = tmp_path / "nome_diferente.xml"
    write_nfe(xml_path)

    output, label = generate_fiscal_pdf(xml_path, tmp_path / "pdfs")

    assert label == "DANFE"
    assert output.exists()
    assert output.name == f"{NFE_KEY}.pdf"


def test_nfse_nacional_generates_danfse_from_content_not_filename(tmp_path: Path) -> None:
    xml_path = tmp_path / "arquivo_sem_chave.xml"
    write_nfse(xml_path)

    output, label = generate_fiscal_pdf(xml_path, tmp_path / "pdfs")

    assert label == "DANFSe"
    assert output.exists()
    assert output.name == f"{NFSE_KEYS[0]}.pdf"


def test_detection_distinguishes_44_and_50_digit_keys(tmp_path: Path) -> None:
    nfe = tmp_path / "nfe.xml"
    nfse = tmp_path / "nfse.xml"
    write_nfe(nfe)
    write_nfse(nfse)

    assert detect_fiscal_document_type(nfe) == "nfe"
    assert detect_fiscal_document_type(nfse) == "nfse_nacional"


def test_municipal_nfse_layout_is_rejected(tmp_path: Path) -> None:
    xml_path = tmp_path / "municipal.xml"
    xml_path.write_text('<CompNfse><infNFSe Id="ABC123"></infNFSe></CompNfse>', encoding="utf-8")

    with pytest.raises(UnsupportedDanfseLayoutError, match="Leiaute de NFS-e ainda nao suportado"):
        generate_fiscal_pdf(xml_path, tmp_path / "pdfs")


def test_missing_optional_fields_do_not_break_danfse(tmp_path: Path) -> None:
    xml_path = tmp_path / "nfse_minima.xml"
    xml_path.write_text(
        f"""<NFSe versao="1.01" xmlns="http://www.sped.fazenda.gov.br/nfse">
<infNFSe Id="NFS{NFSE_KEYS[1]}"><nNFSe>1</nNFSe><DPS><infDPS><tpAmb>1</tpAmb><dCompet>2026-09-08</dCompet></infDPS></DPS></infNFSe>
</NFSe>""",
        encoding="utf-8",
    )

    output = generate_danfse_pdf(xml_path, tmp_path / "pdfs")

    assert output.exists()


def test_long_description_and_accented_values_are_mapped(tmp_path: Path) -> None:
    description = "Prestacao de servicos com acentos: acao, emissao, Sao Paulo. " * 20
    xml_path = tmp_path / "nfse_longa.xml"
    write_nfse(xml_path, description=description)

    data = parse_danfse_data(xml_path)
    output = generate_danfse_pdf(xml_path, tmp_path / "pdfs")

    assert "Sao Paulo" in data.issue_location
    assert data.totals["service"] == "2000.00"
    assert output.exists()


def test_invalid_file_does_not_interrupt_manual_batch(tmp_path: Path) -> None:
    valid_xml = tmp_path / "ok.xml"
    invalid_xml = tmp_path / "erro.xml"
    write_nfse(valid_xml)
    invalid_xml.write_text("<NFSe>", encoding="utf-8")
    generated = []
    errors = []

    for xml_path in [valid_xml, invalid_xml]:
        try:
            generated.append(generate_fiscal_pdf(xml_path, tmp_path / "pdfs")[0])
        except Exception as exc:
            errors.append((xml_path, str(exc)))

    assert len(generated) == 1
    assert len(errors) == 1


def test_same_output_names_do_not_overwrite(tmp_path: Path) -> None:
    first = tmp_path / "a.xml"
    second = tmp_path / "b.xml"
    write_nfse(first)
    write_nfse(second)

    out1 = generate_danfse_pdf(first, tmp_path / "pdfs")
    out2 = generate_danfse_pdf(second, tmp_path / "pdfs")

    assert out1.exists()
    assert out2.exists()
    assert out1 != out2


def test_external_entity_is_rejected(tmp_path: Path) -> None:
    xml_path = tmp_path / "xxe.xml"
    xml_path.write_text("""<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><NFSe>&xxe;</NFSe>""", encoding="utf-8")

    with pytest.raises(ValueError, match="DOCTYPE ou entidade externa"):
        safe_parse_xml(xml_path)


def test_real_nfse_examples_generate_danfse(tmp_path: Path) -> None:
    desktop = Path(r"C:\Users\BM-USER\Desktop")
    missing_examples = [key for key in NFSE_KEYS if not (desktop / f"{key}.xml").exists()]
    if missing_examples:
        pytest.skip(f"Exemplos reais ausentes: {missing_examples}")

    source = tmp_path / "renomeados"
    source.mkdir()
    outputs = []
    for index, key in enumerate(NFSE_KEYS):
        copied = source / f"nome_qualquer_{index}.xml"
        shutil.copy2(desktop / f"{key}.xml", copied)
        outputs.append(generate_fiscal_pdf(copied, tmp_path / "pdfs"))

    assert [label for _, label in outputs] == ["DANFSe"] * 4
    assert len(list((tmp_path / "pdfs").glob("*.pdf"))) == 4
