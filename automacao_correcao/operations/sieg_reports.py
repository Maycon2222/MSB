from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import sleep
import unicodedata

import mysql.connector
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


SIEG_PAGE_LOAD_TIMEOUT = 180
SIEG_ELEMENT_TIMEOUT = 180
SIEG_DOWNLOAD_TIMEOUT = 600

DESCON_EVENT_CODES_TO_REMOVE = {
    "210220 | 210200",
    "210210 | 210220 | 210200",
    "210210 | 210220 | 210200 | 110110",
    "210220 | 210200 | 110110",
    "210210 | 210220 | 110110 | 210200",
    "210210 | 210240 | 210220 | 210200",
    "210210 | 210220 | 110110 | 210200 | 110110",
    "210210 | 210220 | 210240 | 210200",
    "210210 | 110110 | 210220 | 210200",
    "210210 | 210220 | 110110 | 110110 | 210200",
    "210210 | 110110 | 110110 | 610130 | 210220 | 210200",
}


@dataclass(frozen=True)
class SiegCredentials:
    usuario: str
    senha: str


@dataclass(frozen=True)
class SiegGeneratedFiles:
    cancel_path: Path
    descon_path: Path
    descon_tratado_path: Path
    output_path: Path


@dataclass(frozen=True)
class SiegDownloadedReports:
    cancel_path: Path
    descon_path: Path
    descon_tratado_path: Path


def fetch_sieg_credentials(database_password: str) -> SiegCredentials:
    database = mysql.connector.connect(
        host="localhost",
        user="root",
        password=database_password,
        database="gerenciador",
    )
    try:
        cursor = database.cursor()
        cursor.execute("SELECT usuario, senha FROM sieg WHERE id = %s", (1,))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Credenciais do SIEG nao encontradas na tabela sieg.")
        return SiegCredentials(usuario=row[0], senha=row[1])
    finally:
        database.close()


def build_chrome(download_dir: str | Path):
    target = Path(download_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-background-networking")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(target),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True,
        },
    )
    browser = webdriver.Chrome(options=options)
    browser.set_page_load_timeout(SIEG_PAGE_LOAD_TIMEOUT)
    if len(browser.window_handles) > 1:
        first_handle = browser.window_handles[0]
        for handle in browser.window_handles[1:]:
            browser.switch_to.window(handle)
            browser.close()
        browser.switch_to.window(first_handle)
    return browser

def wait_new_file(folder: str | Path, previous_files: set[str], timeout: int = SIEG_DOWNLOAD_TIMEOUT) -> Path:
    target = Path(folder).expanduser()
    for _ in range(timeout):
        current_files = {item.name for item in target.iterdir()}
        new_files = current_files - previous_files
        for file_name in new_files:
            if not file_name.endswith(".crdownload"):
                return target / file_name
        sleep(1)
    raise TimeoutError("Download do SIEG nao finalizou no tempo esperado.")


class SiegDownloader:
    def __init__(self, download_dir: str | Path, credentials: SiegCredentials):
        self.download_dir = Path(download_dir).expanduser()
        self.credentials = credentials
        self.browser = build_chrome(self.download_dir)
        self.wait = WebDriverWait(self.browser, SIEG_ELEMENT_TIMEOUT)

    def close(self) -> None:
        self.browser.quit()

    def open_sieg_page(self) -> None:
        try:
            self.browser.get("https://cofre.sieg.com/pesquisa-avancada")
        except TimeoutException:
            self.browser.execute_script("window.stop();")
        self.wait.until(
            lambda browser: browser.execute_script("return document.readyState") in {"interactive", "complete"}
        )

    def login(self) -> None:
        self.browser.maximize_window()
        self.open_sieg_page()
        email = self.wait.until(EC.element_to_be_clickable((By.ID, "txtEmail")))
        email.clear()
        email.send_keys(self.credentials.usuario)
        password = self.wait.until(EC.element_to_be_clickable((By.ID, "txtPassword")))
        password.clear()
        password.send_keys(self.credentials.senha)
        self.wait.until(EC.element_to_be_clickable((By.ID, "btnSubmit"))).click()

    def prepare_event_filter(self) -> None:
        self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".fields.form-control")))
        Select(self.browser.find_element(By.CSS_SELECTOR, ".fields.form-control")).select_by_value(
            "ListEvents.EventType"
        )
        Select(self.browser.find_element(By.CSS_SELECTOR, ".conditions.form-control")).select_by_value("$eq")

    def download_event(self, event_code: str, output_name: str) -> Path:
        previous_files = {item.name for item in self.download_dir.iterdir()}
        Select(self.browser.find_element(By.CSS_SELECTOR, ".selectEvent.form-control")).select_by_value(event_code)
        self.browser.find_element(By.ID, "btnSearch").click()
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".table-click")))
        self.wait.until(
            EC.element_to_be_clickable((By.ID, "MainContent_cphMainContent_advancedsearch_ExcelLinkBtn"))
        ).click()
        downloaded = wait_new_file(self.download_dir, previous_files)
        output_path = self.download_dir / f"{output_name}.xlsx"
        if output_path.exists():
            output_path.unlink()
        downloaded.replace(output_path)
        return output_path


def download_cancel_and_descon(download_dir: str | Path, database_password: str) -> tuple[Path, Path]:
    credentials = fetch_sieg_credentials(database_password)
    downloader = SiegDownloader(download_dir, credentials)
    try:
        downloader.login()
        downloader.prepare_event_filter()
        cancel_path = downloader.download_event("110111", "cancel")
        sleep(4)
        descon_path = downloader.download_event("210220", "descon")
        return cancel_path, descon_path
    finally:
        downloader.close()


def download_cancel_descon_and_treat(
    *,
    output_dir: str | Path,
    database_password: str,
) -> SiegDownloadedReports:
    target = Path(output_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    cancel_path, descon_path = download_cancel_and_descon(target, database_password)
    descon_tratado_path = treat_descon(descon_path, target / "desconTratado.xlsx")
    return SiegDownloadedReports(
        cancel_path=cancel_path,
        descon_path=descon_path,
        descon_tratado_path=descon_tratado_path,
    )


def read_excel_with_possible_skiprows(path: str | Path, *, skiprows: int = 0) -> pd.DataFrame:
    return pd.read_excel(Path(path).expanduser(), skiprows=skiprows)


def read_excel_finding_column(path: str | Path, candidates: list[str]) -> tuple[pd.DataFrame, str]:
    source = Path(path).expanduser()
    errors: list[str] = []
    for skiprows in (0, 1, 2, 3, 4, 5):
        try:
            df = pd.read_excel(source, skiprows=skiprows)
            return df, find_column(df, candidates)
        except Exception as exc:
            errors.append(f"skiprows={skiprows}: {exc}")
    raise ValueError(
        f"Nao consegui encontrar as colunas esperadas em {source.name}: "
        + ", ".join(candidates)
        + "\n"
        + "\n".join(errors[-2:])
    )


def read_bm026(path: str | Path) -> pd.DataFrame:
    source = Path(path).expanduser()
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source, encoding="cp1252", sep=";", index_col=False, decimal=",")
    return pd.read_excel(source)


def normalize_key_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()


def normalize_column_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip().casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text if char.isalnum())


def find_column(df: pd.DataFrame, candidates: list[str]) -> str:
    normalized = {normalize_column_name(column): column for column in df.columns}
    for candidate in candidates:
        found = normalized.get(normalize_column_name(candidate))
        if found is not None:
            return found
    raise ValueError(f"Nenhuma destas colunas foi encontrada: {', '.join(candidates)}")


def months_between(reference: date, current: date | None = None) -> int:
    today = current or date.today()
    return (today.year - reference.year) * 12 + (today.month - reference.month)


def parse_brazilian_date(value: object) -> date | None:
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def row_text(row: pd.Series) -> str:
    return " ".join(str(value) for value in row.fillna("").tolist()).casefold()


def classify_cloud_reason(row: pd.Series, *, months_limit: int = 5) -> str:
    text = row_text(row)
    reasons: list[str] = []

    if any(term in text for term in ["peso", "pesagem", "diferenca", "diferenÃ§a", "falta", "faltante"]):
        reasons.append("peso")

    if any(term in text for term in ["validade", "vencimento", "vencido", "troca"]):
        reasons.append("validade")

    emission = parse_brazilian_date(row.get("EmisNota", ""))
    if emission and months_between(emission) > months_limit:
        reasons.append("referencias antigas")

    return " / ".join(dict.fromkeys(reasons))


def add_cloud_reason_column(df: pd.DataFrame, *, months_limit: int = 5) -> pd.DataFrame:
    result = df.copy()
    result["Motivo"] = result.apply(lambda row: classify_cloud_reason(row, months_limit=months_limit), axis=1)
    return result


def treat_descon(descon_path: str | Path, output_path: str | Path) -> Path:
    df, event_column = read_excel_finding_column(
        descon_path,
        ["CÃƒÂ³digo do Evento", "Codigo do Evento", "CÃƒÆ’Ã‚Â³digo do Evento"],
    )
    event_column = find_column(df, ["CÃ³digo do Evento", "Codigo do Evento", "CÃƒÂ³digo do Evento"])
    normalized_events = df[event_column].fillna("").astype(str).str.strip()
    blocked = {value.strip() for value in DESCON_EVENT_CODES_TO_REMOVE}
    result = df.loc[~normalized_events.isin(blocked)].copy()
    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_excel(destination, index=False)
    return destination


def remove_cancel_and_descon_from_bm026(
    bm026_path: str | Path,
    cancel_path: str | Path,
    descon_tratado_path: str | Path,
    output_path: str | Path,
) -> Path:
    bm026 = read_bm026(bm026_path)
    cancel, cancel_key_column = read_excel_finding_column(cancel_path, ["Chave da NFe", "Chave da NFE"])
    descon = pd.read_excel(Path(descon_tratado_path).expanduser())

    bm026_key_column = find_column(bm026, ["ObservaÃ§Ã£o", "Observacao", "ObservaÃƒÂ§ÃƒÂ£o"])
    descon_key_column = find_column(descon, ["Chave da NFe", "Chave da NFE"])

    invalid_keys = set(normalize_key_series(cancel[cancel_key_column]).dropna())
    invalid_keys.update(normalize_key_series(descon[descon_key_column]).dropna())
    invalid_keys.discard("")

    bm026_keys = normalize_key_series(bm026[bm026_key_column])
    result = bm026.loc[~bm026_keys.isin(invalid_keys)].copy()
    result = add_cloud_reason_column(result)

    destination = Path(output_path).expanduser()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_excel(destination, index=False)
    return destination


def clean_bm026_with_existing_reports(
    *,
    bm026_path: str | Path,
    cancel_path: str | Path,
    descon_path: str | Path,
    output_path: str | Path,
) -> SiegGeneratedFiles:
    destination = Path(output_path).expanduser()
    work = destination.with_suffix("").parent / "_sieg_manual"
    work.mkdir(parents=True, exist_ok=True)
    treated = treat_descon(descon_path, work / "desconTratado.xlsx")
    final_output = remove_cancel_and_descon_from_bm026(
        bm026_path,
        cancel_path,
        treated,
        destination,
    )
    return SiegGeneratedFiles(
        cancel_path=Path(cancel_path).expanduser(),
        descon_path=Path(descon_path).expanduser(),
        descon_tratado_path=treated,
        output_path=final_output,
    )


def download_sieg_and_clean_bm026(
    *,
    bm026_path: str | Path,
    output_path: str | Path,
    work_dir: str | Path,
    database_password: str,
) -> SiegGeneratedFiles:
    work = Path(work_dir).expanduser()
    work.mkdir(parents=True, exist_ok=True)
    cancel_path, descon_path = download_cancel_and_descon(work, database_password)
    descon_tratado_path = treat_descon(descon_path, work / "desconTratado.xlsx")
    final_output = remove_cancel_and_descon_from_bm026(
        bm026_path,
        cancel_path,
        descon_tratado_path,
        output_path,
    )
    return SiegGeneratedFiles(
        cancel_path=cancel_path,
        descon_path=descon_path,
        descon_tratado_path=descon_tratado_path,
        output_path=final_output,
    )



