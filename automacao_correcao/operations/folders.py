from pathlib import Path
import shutil


def clean_folder(folder: str | Path, *, delete_dirs: bool = False) -> int:
    target = Path(folder).expanduser()
    if not target.exists() or not target.is_dir():
        raise ValueError(f"Pasta nao encontrada: {target}")

    removed = 0
    for item in target.iterdir():
        if item.is_file():
            item.unlink()
            removed += 1
        elif item.is_dir() and delete_dirs:
            shutil.rmtree(item)
            removed += 1
    return removed
