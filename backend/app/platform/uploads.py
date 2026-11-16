"""Upload validation by real content (SPEC-016 / T2.3).

An extension allowlist only checks the *claimed* type. This module checks what
the bytes actually are, so a PDF-flavoured payload renamed to ``.md`` — or an
HTML file with a ``.png`` name, the classic stored-XSS vector — is rejected
**before** the content is parsed, indexed or served back.

Deliberately dependency-free: the signatures we care about are a handful of
byte prefixes, and adding python-magic/libmagic would pull a native dependency
into the image for something this small.
"""
from typing import Dict, Optional, Set, Tuple

# Magic-byte signatures: (offset, prefix) → canonical type.
_SIGNATURES: Tuple[Tuple[int, bytes, str], ...] = (
    (0, b"%PDF-", "pdf"),
    (0, b"\x89PNG\r\n\x1a\n", "png"),
    (0, b"\xff\xd8\xff", "jpeg"),
    (0, b"GIF87a", "gif"),
    (0, b"GIF89a", "gif"),
    # docx/xlsx/pptx are ZIP archives (PK\x03\x04)
    (0, b"PK\x03\x04", "zip"),
)

# Extension → the content types that may legitimately back it.
_EXTENSION_TYPES: Dict[str, Set[str]] = {
    ".pdf":  {"pdf"},
    ".txt":  {"text"},
    ".md":   {"text"},
    ".docx": {"zip"},
    ".png":  {"png"},
    ".jpg":  {"jpeg"},
    ".jpeg": {"jpeg"},
    ".gif":  {"gif"},
    ".webp": {"webp"},
}

# Markup that must never be accepted as "text", because it is the payload of a
# stored-XSS attempt when the file is later served or embedded.
_MARKUP_PREFIXES = (b"<!doctype html", b"<html", b"<?xml", b"<svg", b"<script")


def sniff_type(raw: bytes) -> Optional[str]:
    """Return the canonical content type of ``raw``, or ``None`` if unknown.

    ``"text"`` is returned only for payloads that look like plain text: decodable
    as UTF-8, free of NUL bytes, and not starting with markup.
    """
    if not raw:
        return None

    for offset, prefix, kind in _SIGNATURES:
        if raw[offset:offset + len(prefix)] == prefix:
            return kind

    # RIFF....WEBP — the container tag sits after the 4-byte size field.
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"

    head = raw[:4096]
    if b"\x00" in head:                     # binary of some unknown kind
        return None
    stripped = head.lstrip()[:64].lower()
    if any(stripped.startswith(p) for p in _MARKUP_PREFIXES):
        return None
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text"


def validate_upload(filename: str, raw: bytes, allowed_extensions: Set[str]) -> str:
    """Validate an upload by extension **and** real content.

    Returns the canonical content type. Raises ``HTTPException`` (400) when the
    bytes do not match the declared extension, and 415 when the extension itself
    is not allowed — keeping "you may not upload this kind of file" distinct from
    "this file is not what it claims to be".
    """
    from fastapi import HTTPException
    from pathlib import Path

    ext = Path(filename or "").suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Tipo de archivo no soportado '{ext}'. "
                f"Use: {', '.join(sorted(allowed_extensions))}"
            ),
        )

    detected = sniff_type(raw)
    expected = _EXTENSION_TYPES.get(ext, set())
    if detected is None or detected not in expected:
        raise HTTPException(
            status_code=400,
            detail=(
                "El contenido del archivo no corresponde a su extensión "
                f"'{ext}'. Sube un archivo válido."
            ),
        )
    return detected
