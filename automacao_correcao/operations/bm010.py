from dataclasses import dataclass
from datetime import date, timedelta
import os
from pathlib import Path
from time import monotonic, sleep
from typing import Callable

import mysql.connector
import pyautogui as py

TOTVS_LOGIN_URL = "http://137.107.0.249:8080/totvs-login/loginForm"


def previous_business_day(reference_date: date | None = None) -> date:
    current = reference_date or date.today()
    target = current - timedelta(days=1)
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    return target


def datasul_date(value: date) -> str:
    return value.strftime("%d%m%Y")


@dataclass(frozen=True)
class DatasulCredentials:
    usuario: str
    senha: str


class ImageActions:
    def __init__(self, image_dir: str | Path, confidence: float = 0.78, timeout: float = 12):
        self.image_dir = Path(image_dir).expanduser()
        self.confidence = confidence
        self.timeout = timeout

    def path(self, image_name: str) -> str:
        return str(self.image_dir / image_name)

    def validate_images(self, image_names: list[str]) -> None:
        missing = [name for name in image_names if not (self.image_dir / name).exists()]
        if missing:
            raise FileNotFoundError(
                "Imagens do BM010 nao encontradas: "
                + ", ".join(missing)
                + f". Pasta usada: {self.image_dir}"
            )

    def locate(self, image_name: str, confidence: float | None = None, timeout: float | None = None):
        image_path = self.path(image_name)
        deadline = monotonic() + (timeout if timeout is not None else self.timeout)
        last_error: Exception | None = None
        while monotonic() <= deadline:
            try:
                image = py.locateOnScreen(image_path, confidence=confidence or self.confidence)
            except Exception as exc:
                last_error = exc
                image = None
            if image:
                return image
            sleep(0.5)

        details = f"Imagem nao encontrada na tela: {image_name}"
        if last_error:
            details += f" ({last_error})"
        details += "\nConfira se a tela esperada esta aberta e visivel antes de continuar."
        raise RuntimeError(details)

    def locate_once(self, image_name: str, confidence: float | None = None):
        image_path = self.image_dir / image_name
        if not image_path.exists():
            return None
        try:
            return py.locateOnScreen(str(image_path), confidence=confidence or self.confidence)
        except Exception:
            return None

    def wait_for_any(
        self,
        image_names: list[str],
        *,
        confidence: float | None = None,
        timeout: float = 90,
    ) -> tuple[str, object]:
        deadline = monotonic() + timeout
        while monotonic() <= deadline:
            for image_name in image_names:
                image = self.locate_once(image_name, confidence=confidence)
                if image:
                    return image_name, image
            sleep(0.5)

        raise RuntimeError(
            "Nao encontrei nenhum destes itens na tela: "
            + ", ".join(image_names)
            + "\nConfira se o acesso remoto abriu corretamente."
        )

    def click(self, image_name: str, confidence: float | None = None) -> None:
        image = self.locate(image_name, confidence=confidence)
        py.click(py.center(image))

    def try_click(self, image_name: str, confidence: float | None = None, timeout: float = 5) -> bool:
        try:
            image = self.locate(image_name, confidence=confidence, timeout=timeout)
        except RuntimeError:
            return False
        py.click(py.center(image))
        return True

    def double_click(self, image_name: str, confidence: float | None = None) -> None:
        image = self.locate(image_name, confidence=confidence)
        py.doubleClick(py.center(image))


def fetch_datasul_credentials(database_password: str) -> DatasulCredentials:
    database = mysql.connector.connect(
        host="localhost",
        user="root",
        password=database_password,
        database="gerenciador",
        connection_timeout=10,
    )
    try:
        cursor = database.cursor()
        cursor.execute("SELECT usuario, senha FROM userdatasul WHERE id = %s", (1,))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Credenciais do DataSul nao encontradas na tabela userdatasul.")
        return DatasulCredentials(usuario=row[0], senha=row[1])
    finally:
        database.close()


def remote_access_file() -> Path | None:
    candidates = [
        Path.home() / "Desktop" / "Acesso remoto Matriz.rdp",
        Path("C:/Users/BM-USER/Desktop/Acesso remoto Matriz.rdp"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def open_remote_access(actions: ImageActions, notify: Callable[[str], None]) -> None:
    access_file = remote_access_file()
    if access_file:
        notify("BM010: abrindo Acesso remoto Matriz.rdp...")
        os.startfile(str(access_file))
        return

    notify("BM010: abrindo acesso remoto pelo icone...")
    actions.double_click("Datasul.png", confidence=0.65)


def confirm_remote_connection(actions: ImageActions, notify: Callable[[str], None]) -> None:
    notify("BM010: confirmando acesso remoto...")
    if actions.try_click("DTsulconectar.png", confidence=0.55, timeout=6):
        return

    notify("BM010: aviso de conexao nao apareceu, seguindo...")


def confirm_remote_certificate(actions: ImageActions, notify: Callable[[str], None]) -> None:
    notify("BM010: confirmando certificado remoto...")
    if actions.try_click("DTsulentrar.png", confidence=0.55, timeout=8):
        return

    notify("BM010: aviso de certificado nao apareceu, seguindo...")


def activate_remote_window() -> bool:
    for title in ["regina.eco.br", "Conexao de Area de Trabalho Remota", "Conexão de Área de Trabalho Remota"]:
        try:
            windows = py.getWindowsWithTitle(title)
        except Exception:
            windows = []
        for window in windows:
            try:
                if window.isMinimized:
                    window.restore()
                window.activate()
                return True
            except Exception:
                continue
    return False


def wait_remote_ready(actions: ImageActions, notify: Callable[[str], None], timeout: float = 120) -> None:
    notify("BM010: aguardando acesso remoto abrir...")
    deadline = monotonic() + timeout
    remote_seen_at: float | None = None
    while monotonic() <= deadline:
        if actions.try_click("DTsulconectar.png", confidence=0.55, timeout=0.5):
            notify("BM010: conexao remota confirmada...")
            remote_seen_at = None
            continue

        if actions.try_click("DTsulentrar.png", confidence=0.55, timeout=0.5):
            notify("BM010: certificado remoto confirmado...")
            remote_seen_at = None
            continue

        if activate_remote_window():
            if remote_seen_at is None:
                remote_seen_at = monotonic()
            if monotonic() - remote_seen_at >= 2:
                py.press("esc")
                notify("BM010: remoto pronto...")
                return

        sleep(0.5)

    raise RuntimeError("O acesso remoto nao ficou pronto dentro do tempo esperado.")


def open_totvs_login_form(notify: Callable[[str], None]) -> None:
    notify("BM010: abrindo tela de login TOTVS...")
    py.hotkey("ctrl", "l")
    sleep(0.2)
    py.write(TOTVS_LOGIN_URL)
    py.press("enter")


def wait_for_datasul_login(actions: ImageActions, notify: Callable[[str], None]) -> None:
    py.press("esc")
    notify("BM010: procurando DATASUL/login...")
    image_name = ""
    image = None
    try:
        image_name, image = actions.wait_for_any(["image.png", "Brave.png"], confidence=0.60, timeout=8)
    except RuntimeError:
        pass

    if image_name == "Brave.png":
        notify("BM010: abrindo DATASUL NOVO...")
        py.doubleClick(py.center(image))
        sleep(3)

    if image_name == "image.png":
        return

    open_totvs_login_form(notify)
    try:
        actions.locate("image.png", confidence=0.60, timeout=60)
        return
    except RuntimeError:
        notify("BM010: procurando DATASUL NOVO novamente...")
        image_name, image = actions.wait_for_any(["Brave.png", "image.png"], confidence=0.60, timeout=30)
        if image_name == "Brave.png":
            py.doubleClick(py.center(image))
            open_totvs_login_form(notify)
        actions.locate("image.png", confidence=0.60, timeout=60)


def enter_datasul(
    actions: ImageActions,
    credentials: DatasulCredentials,
    progress: Callable[[str], None] | None = None,
) -> None:
    notify = progress or (lambda _message: None)
    sleep(3)
    notify("BM010: abrindo DataSul...")
    open_remote_access(actions, notify)
    wait_remote_ready(actions, notify)
    wait_for_datasul_login(actions, notify)

    notify("BM010: preenchendo login...")
    actions.double_click("image.png")
    for value in [credentials.usuario, credentials.senha]:
        sleep(2)
        py.write(str(value))
        py.press("tab")
        py.press("enter")


def run_bm010(
    *,
    image_dir: str | Path,
    database_password: str,
    target_date: date | None = None,
    progress: Callable[[str], None] | None = None,
) -> date:
    notify = progress or (lambda _message: None)
    execution_date = target_date or previous_business_day()
    formatted_date = datasul_date(execution_date)
    actions = ImageActions(image_dir)
    actions.validate_images(
        [
            "Datasul.png",
            "DTsulconectar.png",
            "DTsulentrar.png",
            "Brave.png",
            "image.png",
            "BM010.png",
            "DI.png",
            "dateBM010.png",
            "flagBM010.png",
            "executarBM010.png",
        ]
    )
    notify("BM010: buscando credenciais no banco...")
    credentials = fetch_datasul_credentials(database_password)

    enter_datasul(actions, credentials, progress=progress)

    sleep(8)
    notify("BM010: abrindo rotina BM010...")
    actions.double_click("BM010.png")
    sleep(10)
    actions.click("DI.png")
    sleep(20)
    actions.double_click("dateBM010.png")
    sleep(2)

    notify(f"BM010: preenchendo data {execution_date.strftime('%d/%m/%Y')}...")
    py.write(formatted_date)
    py.press("tab")
    sleep(1)
    py.write(formatted_date)

    actions.click("flagBM010.png")
    py.press("tab")
    py.write("60")
    notify("BM010: executando...")
    actions.click("executarBM010.png")
    return execution_date
