import os
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

STORAGE_DIR = os.getenv("STORAGE_PATH", "storage/evidence")

def get_storage_path() -> Path:
    """Return absolute Path to evidence storage directory, creating if absent."""
    base_path = Path(__file__).resolve().parent.parent.parent
    p = Path(STORAGE_DIR)
    target_path = p.resolve() if p.is_absolute() else (base_path / p).resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    return target_path

def save_file(filename: str, content: bytes) -> tuple[str, str, int]:
    """
    Safely store evidence file to disk avoiding path traversal vulnerabilities.
    Returns (stored_filename, absolute_filepath_str, file_size_bytes).
    """
    safe_name = os.path.basename(filename)
    unique_prefix = uuid.uuid4().hex[:8]
    stored_name = f"{unique_prefix}_{safe_name}"
    target_dir = get_storage_path()
    file_path = (target_dir / stored_name).resolve()

    with open(file_path, "wb") as f:
        f.write(content)

    return stored_name, str(file_path), len(content)

def get_file_path(filename: str) -> Path | None:
    """
    Safely resolve file path preventing path traversal outside storage directory.
    Returns Path object if valid, None if directory traversal or file not found.
    """
    if not filename or ".." in filename or "/" in filename or "\\" in filename or "\x00" in filename:
        return None

    safe_name = os.path.basename(filename)
    target_dir = get_storage_path()
    file_path = (target_dir / safe_name).resolve()

    # Path traversal protection
    if not str(file_path).startswith(str(target_dir)):
        return None

    if not file_path.exists() or not file_path.is_file():
        return None

    return file_path
