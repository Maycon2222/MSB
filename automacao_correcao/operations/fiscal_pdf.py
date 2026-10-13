from __future__ import annotations

from pathlib import Path

from automacao_correcao.operations.danfe_pdf import find_inf_nfe, generate_danfe_pdf
from automacao_correcao.operations.danfse_pdf import (
    UnsupportedDanfseLayoutError,
    generate_danfse_pdf,
    is_nfse_nacional,
    safe_parse_xml,
)


def detect_fiscal_document_type(xml_path: str | Path) -> str:
    root = safe_parse_xml(xml_path)
    try:
        inf_nfe = find_inf_nfe(root)
        key = inf_nfe.attrib.get("Id", "").replace("NFe", "")
        if len(key) == 44 and key.isdigit():
            return "nfe"
    except ValueError:
        pass

    if is_nfse_nacional(root):
        return "nfse_nacional"

    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "infNFSe":
            raise UnsupportedDanfseLayoutError("Leiaute de NFS-e ainda nao suportado.")

    raise ValueError("Documento fiscal nao reconhecido.")


def generate_fiscal_pdf(xml_path: str | Path, output_dir: str | Path) -> tuple[Path, str]:
    document_type = detect_fiscal_document_type(xml_path)
    if document_type == "nfe":
        return generate_danfe_pdf(xml_path, output_dir), "DANFE"
    if document_type == "nfse_nacional":
        return generate_danfse_pdf(xml_path, output_dir), "DANFSe"
    raise ValueError("Documento fiscal nao reconhecido.")
