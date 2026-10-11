import hashlib
import os
from typing import Union

def calculate_hash(data_or_path: Union[bytes, str]) -> str:
    """Calculate SHA-256 cryptographic digest for bytes, string, or existing file path."""
    if isinstance(data_or_path, bytes):
        return hashlib.sha256(data_or_path).hexdigest()
    elif isinstance(data_or_path, str):
        # Check if it refers to a valid physical file
        if os.path.exists(data_or_path) and os.path.isfile(data_or_path):
            sha256 = hashlib.sha256()
            with open(data_or_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        else:
            return hashlib.sha256(data_or_path.encode("utf-8")).hexdigest()
    else:
        raise ValueError(f"Unsupported data type for hashing: {type(data_or_path)}")
