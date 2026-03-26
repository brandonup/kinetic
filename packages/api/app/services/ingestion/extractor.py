"""
Text extraction via unstructured library.

Supports: PDF, DOCX, DOC, PPTX, PPT, TXT, MD, CSV, XLSX, XLS, RTF, JSON, JSONL.
Raises UnsupportedFileTypeError for unsupported content types.
Raises RuntimeError on extraction failure (caller handles retry).
"""

from __future__ import annotations

import io
import json
import logging
from typing import Set

logger = logging.getLogger(__name__)

SUPPORTED_MIME_TYPES: Set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/rtf",
    "text/rtf",
    "application/json",
    "application/jsonl",
    "application/x-jsonlines",
}


class UnsupportedFileTypeError(ValueError):
    """Raised when the file content type is not in the supported set."""


# Extension → MIME type fallback for types browsers send as application/octet-stream
_EXT_TO_MIME: dict[str, str] = {
    ".json": "application/json",
    ".jsonl": "application/jsonl",
}


def _resolve_content_type(content_type: str, filename: str) -> str:
    """Resolve actual content type, falling back to extension for ambiguous MIME types."""
    if content_type in SUPPORTED_MIME_TYPES:
        return content_type
    # Browsers send unknown extensions as application/octet-stream or empty
    if content_type in ("application/octet-stream", ""):
        ext = filename[filename.rfind("."):].lower() if "." in filename else ""
        if ext in _EXT_TO_MIME:
            return _EXT_TO_MIME[ext]
    return content_type


def extract_text(content: bytes, content_type: str, filename: str) -> str:
    """
    Extract plain text from a document using the unstructured library.

    Args:
        content: Raw file bytes.
        content_type: MIME type of the document.
        filename: Original filename (used by unstructured for format hints).

    Returns:
        Extracted text as a single string with double-newline paragraph separators.

    Raises:
        UnsupportedFileTypeError: content_type not in SUPPORTED_MIME_TYPES.
        RuntimeError: Extraction failed (transient — caller should retry).
    """
    content_type = _resolve_content_type(content_type, filename)

    if content_type not in SUPPORTED_MIME_TYPES:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: {content_type!r}. "
            f"Supported: {sorted(SUPPORTED_MIME_TYPES)}"
        )

    # JSON: parse and pretty-print rather than passing to unstructured
    if content_type == "application/json":
        try:
            parsed = json.loads(content)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {filename!r}: {exc}") from exc

    # JSONL: extract text-relevant fields from each line, skip metadata
    # Common patterns: {"content": "..."}, {"text": "..."}, {"body": "..."}
    # Falls back to all string values if no known text field found.
    if content_type in ("application/jsonl", "application/x-jsonlines"):
        _TEXT_KEYS = ("content", "text", "body", "message", "description")
        try:
            raw = content.decode("utf-8")
            segments: list[str] = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    segments.append(str(obj))
                    continue
                # Try known text fields first (title + content body)
                parts: list[str] = []
                if obj.get("title"):
                    parts.append(str(obj["title"]))
                for key in _TEXT_KEYS:
                    val = obj.get(key)
                    if isinstance(val, str) and val.strip():
                        parts.append(val.strip())
                        break
                if parts:
                    segments.append("\n".join(parts))
                else:
                    # Fallback: concatenate all string values
                    all_strings = [str(v) for v in obj.values() if isinstance(v, str) and v.strip()]
                    if all_strings:
                        segments.append("\n".join(all_strings))
            if not segments:
                return ""
            return "\n\n".join(segments)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"Invalid JSONL in {filename!r}: {exc}") from exc

    try:
        from unstructured.partition.auto import partition  # type: ignore[import]

        elements = partition(
            file=io.BytesIO(content),
            content_type=content_type,
            metadata_filename=filename,
        )
        texts = [str(el).strip() for el in elements if str(el).strip()]
        if not texts:
            logger.warning("No text extracted from %s (content_type=%s)", filename, content_type)
            return ""
        return "\n\n".join(texts)

    except UnsupportedFileTypeError:
        raise
    except Exception as exc:
        logger.error("Text extraction failed for %s: %s", filename, exc)
        raise RuntimeError(f"Text extraction failed for {filename!r}: {exc}") from exc
