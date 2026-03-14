"""
Content hashing utilities for file-DB sync tracking.

Provides SHA-256 hashing for detecting file changes and preventing
circular updates between the file watcher and pipeline writes.
"""

import hashlib
from pathlib import Path


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA-256 hash of a file's contents.

    Args:
        file_path: Path to the file

    Returns:
        Hex-encoded SHA-256 hash string
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_content_hash(content: str) -> str:
    """
    Compute SHA-256 hash of a string's UTF-8 encoding.

    Args:
        content: String content to hash

    Returns:
        Hex-encoded SHA-256 hash string
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
