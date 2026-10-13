from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from automacao_correcao.operations.xml_nfe import NFE_NAMESPACE


MAX_ACCESS_KEYS = 1000
VALID_KEY_LENGTHS = (44, 50)
ACCESS_KEY_RE = re.compile(r"\b(?:\d{44}|\d{50})\b")


@dataclass(frozen=True)
class ParsedAccessKeys:
    valid_keys: list[str]
    invalid_entries: list[str]
    duplicate_count: int
    informed_count: int


@dataclass(frozen=True)
class SeparateXmlResult:
    informed_count: int
    valid_count: int
    found_count: int
    copied_count: int
    not_found_count: int
    invalid_count: int
    duplicate_count: int
    destination: Path
    not_found_keys: list[str]
    invalid_entries: list[str]
    copied_files: list[Path]
    scanned_files: int
    ignored_files: int
    duplicate_xml_count: int

    def summary_text(self) -> str:
        lines = [
            "Busca concluida.",
            "",
            f"Chaves informadas: {self.informed_count}",
            f"Chaves validas: {self.valid_count}",
            f"XML encontrados: {self.found_count}",
            f"Arquivos copiados: {self.copied_count}",
            f"Chaves nao encontradas: {self.not_found_count}",
            f"Chaves invalidas: {self.invalid_count}",
        ]
        if self.duplicate_count:
            lines.append(f"Chaves duplicadas ignoradas: {self.duplicate_count}")
        if self.ignored_files:
            lines.append(f"XML invalidos ou nao fiscais ignorados: {self.ignored_files}")
        if self.duplicate_xml_count:
            lines.append(f"XMLs duplicados ignorados: {self.duplicate_xml_count}")
        lines.append(f"Pasta de destino: {self.destination}")
        return "\n".join(lines)


def _segment_digits(digits: str) -> list[str] | None:
    if not digits:
        return []
    if len(digits) in VALID_KEY_LENGTHS:
        return [digits]

    segments: dict[int, list[str]] = {0: []}
    for index in range(len(digits) + 1):
        current = segments.get(index)
        if current is None:
            continue
        for length in sorted(VALID_KEY_LENGTHS, reverse=True):
            end = index + length
            if end <= len(digits) and end not in segments:
                segments[end] = current + [digits[index:end]]
    return segments.get(len(digits))


def _parse_line_keys(line: str) -> tuple[list[str], list[str]]:
    tokens = [token for token in re.split(r"\s+", line.strip()) if token]
    token_digits = [re.sub(r"\D+", "", token) for token in tokens]
    has_complete_token = any(len(digits) in VALID_KEY_LENGTHS for digits in token_digits)
    if has_complete_token:
        keys: list[str] = []
        invalid: list[str] = []
        for token, digits in zip(tokens, token_digits):
            if not digits:
                continue
            if len(digits) in VALID_KEY_LENGTHS:
                keys.append(digits)
            else:
                invalid.append(token)
        return keys, invalid

    digits = re.sub(r"\D+", "", line)
    keys = _segment_digits(digits)
    if keys is None:
        return [], [line]
    return keys, []


def parse_access_keys(raw_text: str, *, max_keys: int = MAX_ACCESS_KEYS) -> ParsedAccessKeys:
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    duplicate_count = 0
    informed_count = 0

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        keys, invalid_tokens = _parse_line_keys(line)
        if invalid_tokens:
            informed_count += len(invalid_tokens)
            invalid.extend(invalid_tokens)

        for key in keys:
            informed_count += 1
            if key in seen:
                duplicate_count += 1
                continue
            seen.add(key)
            valid.append(key)

    if len(valid) > max_keys:
        raise ValueError(f"Informe no maximo {max_keys} chaves validas por operacao.")

    return ParsedAccessKeys(
        valid_keys=valid,
        invalid_entries=invalid,
        duplicate_count=duplicate_count,
        informed_count=informed_count,
    )


def xml_files_recursive(folder: str | Path) -> list[Path]:
    source = Path(folder).expanduser()
    if not source.exists() or not source.is_dir():
        raise ValueError("Selecione uma pasta de origem valida.")
    return sorted(path for path in source.rglob("*") if path.is_file() and path.suffix.lower() == ".xml")


def _only_valid_access_key_values(values: list[str]) -> list[str]:
    return [value for value in values if len(value) in VALID_KEY_LENGTHS and value.isdigit()]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _digits_from_prefixed_id(value: str, prefix: str) -> str:
    value = value.strip()
    if value.upper().startswith(prefix.upper()):
        value = value[len(prefix) :]
    return re.sub(r"\D+", "", value)


def access_keys_from_xml(xml_path: str | Path) -> list[str]:
    source = Path(xml_path).expanduser()
    content = source.read_text(encoding="utf-8-sig", errors="ignore")
    keys: list[str] = []

    try:
        root = ET.fromstring(content)
        for inf_nfe in root.findall(".//nfe:infNFe", NFE_NAMESPACE):
            key = _digits_from_prefixed_id(inf_nfe.attrib.get("Id", ""), "NFe")
            keys.extend(_only_valid_access_key_values([key]))
        keys.extend(
            _only_valid_access_key_values(
                [re.sub(r"\D+", "", (element.text or "")) for element in root.findall(".//nfe:infProt/nfe:chNFe", NFE_NAMESPACE)]
            )
        )
        for element in root.iter():
            if _local_name(element.tag) == "infNFSe":
                key = _digits_from_prefixed_id(element.attrib.get("Id", ""), "NFS")
                keys.extend(_only_valid_access_key_values([key]))
    except ET.ParseError:
        return []

    if not keys:
        keys.extend(ACCESS_KEY_RE.findall(content))
    return list(dict.fromkeys(keys))


def unique_destination_path(destination_dir: Path, file_name: str) -> Path:
    destination = destination_dir / file_name
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    counter = 2
    while True:
        candidate = destination_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def separate_xml_by_access_keys(
    keys_text: str,
    source_folder: str | Path,
    destination_folder: str | Path,
    *,
    progress_callback=None,
) -> SeparateXmlResult:
    parsed = parse_access_keys(keys_text)
    if not parsed.valid_keys:
        raise ValueError("Cole ao menos uma chave de acesso valida com 44 ou 50 digitos.")

    source = Path(source_folder).expanduser()
    destination = Path(destination_folder).expanduser()
    if not source.exists() or not source.is_dir():
        raise ValueError("Selecione uma pasta de origem valida.")
    if not str(destination):
        raise ValueError("Selecione uma pasta de destino.")
    destination.mkdir(parents=True, exist_ok=True)

    requested_keys = set(parsed.valid_keys)
    found_by_key: dict[str, Path] = {}
    scanned_files = 0
    ignored_files = 0
    duplicate_xml_count = 0
    xml_paths = xml_files_recursive(source)

    for index, xml_path in enumerate(xml_paths, start=1):
        scanned_files += 1
        try:
            file_keys = access_keys_from_xml(xml_path)
        except OSError:
            file_keys = []

        if not file_keys:
            ignored_files += 1
        for key in file_keys:
            if key not in requested_keys:
                continue
            if key in found_by_key:
                if found_by_key[key] != xml_path:
                    duplicate_xml_count += 1
                continue
            found_by_key[key] = xml_path

        if progress_callback:
            progress_callback(index, len(xml_paths), len(found_by_key))

        if len(found_by_key) == len(requested_keys):
            break

    copied_files: list[Path] = []
    copied_sources: set[Path] = set()
    for key in parsed.valid_keys:
        xml_path = found_by_key.get(key)
        if xml_path is None or xml_path in copied_sources:
            continue
        copied_sources.add(xml_path)
        target_path = unique_destination_path(destination, xml_path.name)
        shutil.copy2(xml_path, target_path)
        copied_files.append(target_path)

    not_found = [key for key in parsed.valid_keys if key not in found_by_key]
    return SeparateXmlResult(
        informed_count=parsed.informed_count,
        valid_count=len(parsed.valid_keys),
        found_count=len(found_by_key),
        copied_count=len(copied_files),
        not_found_count=len(not_found),
        invalid_count=len(parsed.invalid_entries),
        duplicate_count=parsed.duplicate_count,
        destination=destination,
        not_found_keys=not_found,
        invalid_entries=parsed.invalid_entries,
        copied_files=copied_files,
        scanned_files=scanned_files,
        ignored_files=ignored_files,
        duplicate_xml_count=duplicate_xml_count,
    )
