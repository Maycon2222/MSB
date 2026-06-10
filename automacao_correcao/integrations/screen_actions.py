from pathlib import Path

import pyautogui as py


class ScreenActions:
    def __init__(self, image_dir: str | Path):
        self.image_dir = Path(image_dir).expanduser()

    def image(self, name: str) -> str:
        return str(self.image_dir / name)

    def click(self, image_name: str, confidence: float = 0.8) -> bool:
        found = py.locateOnScreen(self.image(image_name), confidence=confidence)
        if not found:
            return False
        py.click(py.center(found))
        return True

    def double_click(self, image_name: str, confidence: float = 0.8) -> bool:
        found = py.locateOnScreen(self.image(image_name), confidence=confidence)
        if not found:
            return False
        py.doubleClick(py.center(found))
        return True
