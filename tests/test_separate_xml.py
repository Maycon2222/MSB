from pathlib import Path

from automacao_correcao.operations.separate_xml import (
    access_keys_from_xml,
    parse_access_keys,
    separate_xml_by_access_keys,
)


KEY_ONE = "15260706057223035129553000001633421549243869"
KEY_TWO = "27260812345678000123550010000012341000012345"
NFSE_KEY_ONE = "35503081253654352000127000000000036626096718891784"
NFSE_KEY_TWO = "42091022253113791001790000000001813626094979617509"
NFSE_KEY_THREE = "33045572236550850000100000000000003926090130073248"
NFSE_KEY_FOUR = "33045572236550850000100000000000004026090619231109"


def write_nfe(path: Path, key: str) -> None:
    path.write_text(
        f"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
<NFe><infNFe Id="NFe{key}" versao="4.00"></infNFe></NFe>
<protNFe><infProt><chNFe>{key}</chNFe></infProt></protNFe>
</nfeProc>""",
        encoding="utf-8",
    )


def write_nfse(path: Path, key: str) -> None:
    path.write_text(
        f"""<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
<infNFSe Id="NFS{key}" versao="1.00"></infNFSe>
</NFSe>""",
        encoding="utf-8",
    )


def test_parse_access_keys_accepts_formatted_spaces_and_removes_duplicates_for_nfe() -> None:
    formatted = f"{KEY_ONE[:4]} {KEY_ONE[4:20]} {KEY_ONE[20:]}"
    parsed = parse_access_keys(f"{formatted}\n{KEY_TWO} {KEY_TWO}\n123")

    assert parsed.valid_keys == [KEY_ONE, KEY_TWO]
    assert parsed.duplicate_count == 1
    assert parsed.invalid_entries == ["123"]


def test_parse_access_keys_accepts_nfse_50_digits_and_removes_duplicates() -> None:
    formatted = f"{NFSE_KEY_ONE[:7]} {NFSE_KEY_ONE[7:22]} {NFSE_KEY_ONE[22:]}"
    parsed = parse_access_keys(f"{formatted}\n{NFSE_KEY_TWO} {NFSE_KEY_TWO}\n12345")

    assert parsed.valid_keys == [NFSE_KEY_ONE, NFSE_KEY_TWO]
    assert parsed.duplicate_count == 1
    assert parsed.invalid_entries == ["12345"]


def test_separate_xml_by_access_keys_copies_found_xml_and_ignores_invalid_files(tmp_path: Path) -> None:
    source = tmp_path / "origem"
    destination = tmp_path / "destino"
    source.mkdir()
    write_nfe(source / "nome_sem_chave.xml", KEY_ONE)
    (source / "corrompido.xml").write_text("<nfeProc>", encoding="utf-8")
    (source / "ignorar.txt").write_text(KEY_TWO, encoding="utf-8")

    result = separate_xml_by_access_keys(f"{KEY_ONE}\n{KEY_TWO}", source, destination)

    assert result.valid_count == 2
    assert result.found_count == 1
    assert result.copied_count == 1
    assert result.not_found_keys == [KEY_TWO]
    assert (destination / "nome_sem_chave.xml").exists()


def test_separate_xml_by_access_keys_copies_nfse_by_infnfse_id(tmp_path: Path) -> None:
    source = tmp_path / "origem"
    destination = tmp_path / "destino"
    source.mkdir()
    write_nfse(source / "arquivo_sem_chave_no_nome.xml", NFSE_KEY_ONE)
    write_nfse(source / "duplicado.xml", NFSE_KEY_ONE)
    (source / "nao_fiscal.xml").write_text("<root></root>", encoding="utf-8")

    result = separate_xml_by_access_keys(f"{NFSE_KEY_ONE}\n{NFSE_KEY_TWO}", source, destination)

    assert result.valid_count == 2
    assert result.found_count == 1
    assert result.copied_count == 1
    assert result.not_found_keys == [NFSE_KEY_TWO]
    assert result.ignored_files == 1
    assert result.duplicate_xml_count == 1
    assert len(list(destination.glob("*.xml"))) == 1


def test_access_keys_from_real_nfse_examples() -> None:
    examples = [
        (Path(r"C:\Users\BM-USER\Desktop\35503081253654352000127000000000036626096718891784.xml"), NFSE_KEY_ONE),
        (Path(r"C:\Users\BM-USER\Desktop\42091022253113791001790000000001813626094979617509.xml"), NFSE_KEY_TWO),
        (Path(r"C:\Users\BM-USER\Desktop\33045572236550850000100000000000003926090130073248.xml"), NFSE_KEY_THREE),
        (Path(r"C:\Users\BM-USER\Desktop\33045572236550850000100000000000004026090619231109.xml"), NFSE_KEY_FOUR),
    ]

    for xml_path, expected_key in examples:
        if not xml_path.exists():
            continue
        assert expected_key in access_keys_from_xml(xml_path)
