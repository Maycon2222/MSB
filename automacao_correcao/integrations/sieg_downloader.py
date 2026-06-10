from dataclasses import dataclass
from pathlib import Path
from time import sleep

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


@dataclass(frozen=True)
class SiegDownloadRequest:
    event_type: str
    output_name: str


def build_chrome(download_dir: str | Path):
    target = Path(download_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    options = Options()
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
    return webdriver.Chrome(options=options)


def wait_new_file(folder: str | Path, previous_files: set[str], timeout: int = 160) -> Path:
    target = Path(folder).expanduser()
    for _ in range(timeout):
        current_files = {item.name for item in target.iterdir()}
        new_files = current_files - previous_files
        for file_name in new_files:
            if not file_name.endswith(".crdownload"):
                return target / file_name
        sleep(1)
    raise TimeoutError("Download nao finalizou")


class SiegDownloader:
    def __init__(self, navegador, wait_seconds: int = 20):
        self.navegador = navegador
        self.wait = WebDriverWait(navegador, wait_seconds)

    def login(self, usuario: str, senha: str) -> None:
        self.navegador.get("https://cofre.sieg.com/pesquisa-avancada")
        self.navegador.maximize_window()
        self.navegador.find_element(By.ID, "txtEmail").send_keys(usuario)
        self.navegador.find_element(By.ID, "txtPassword").send_keys(senha)
        self.navegador.find_element(By.ID, "btnSubmit").click()

    def prepare_event_search(self) -> None:
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".fields.form-control")))
        Select(self.navegador.find_element(By.CSS_SELECTOR, ".fields.form-control")).select_by_value(
            "ListEvents.EventType"
        )
        Select(self.navegador.find_element(By.CSS_SELECTOR, ".conditions.form-control")).select_by_value("$eq")

    def download_event(self, request: SiegDownloadRequest, download_dir: str | Path) -> Path:
        target = Path(download_dir).expanduser()
        previous_files = {item.name for item in target.iterdir()}
        Select(self.navegador.find_element(By.CSS_SELECTOR, ".selectEvent.form-control")).select_by_value(
            request.event_type
        )
        self.navegador.find_element(By.ID, "btnSearch").click()
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".table-click")))
        self.wait.until(
            EC.element_to_be_clickable((By.ID, "MainContent_cphMainContent_advancedsearch_ExcelLinkBtn"))
        ).click()
        downloaded = wait_new_file(target, previous_files)
        output = target / f"{request.output_name}.xlsx"
        downloaded.replace(output)
        return output
