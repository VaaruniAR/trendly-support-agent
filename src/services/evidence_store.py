"""Small local evidence store for the assignment demo.

Return photos are saved outside the public static directory. A JSON registry
keeps only the metadata needed for a specialist to locate the evidence file.
This is intentionally a simple local persistence layer, not a production
object-storage or case-management system.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import EVIDENCE_DIR, EVIDENCE_INDEX_PATH

_SUFFIX_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class EvidenceStorageError(RuntimeError):
    """Raised when evidence cannot be stored safely."""


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("records", []) if isinstance(data, dict) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"records": records}, indent=2), encoding="utf-8")


def save_evidence(
    raw_image: bytes,
    *,
    mime_type: str,
    order_id: str,
    item_id: str,
    reason: str,
    customer_email: str,
) -> dict[str, Any]:
    """Persist a validated evidence image and its local review metadata."""
    suffix = _SUFFIX_BY_MIME.get(mime_type)
    if not suffix:
        raise EvidenceStorageError("Unsupported evidence image type.")

    evidence_id = f"EVD-{uuid.uuid4().hex[:12].upper()}"
    filename = f"{evidence_id}{suffix}"
    record = {
        "evidence_id": evidence_id,
        "filename": filename,
        "mime_type": mime_type,
        "bytes": len(raw_image),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "order_id": order_id,
        "item_id": item_id,
        "reason": reason,
        "customer_email": customer_email,
        "ticket_id": None,
    }
    try:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (EVIDENCE_DIR / filename).write_bytes(raw_image)
        records = _load_records(EVIDENCE_INDEX_PATH)
        records.append(record)
        _write_records(EVIDENCE_INDEX_PATH, records)
    except OSError as exc:
        raise EvidenceStorageError("I couldn't securely save that photo. Please try uploading it again.") from exc
    return record


def attach_ticket(evidence_id: str, ticket_id: str) -> None:
    """Link an existing evidence record to its human-review ticket."""
    records = _load_records(EVIDENCE_INDEX_PATH)
    for record in records:
        if record.get("evidence_id") == evidence_id:
            record["ticket_id"] = ticket_id
            _write_records(EVIDENCE_INDEX_PATH, records)
            return
