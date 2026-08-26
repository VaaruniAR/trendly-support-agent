"""Tests for the local demo evidence registry."""

import json

from src.services import evidence_store


def test_evidence_store_writes_image_metadata_and_ticket_link(tmp_path, monkeypatch):
    evidence_dir = tmp_path / "return_evidence"
    index_path = tmp_path / "evidence_records.json"
    monkeypatch.setattr(evidence_store, "EVIDENCE_DIR", evidence_dir)
    monkeypatch.setattr(evidence_store, "EVIDENCE_INDEX_PATH", index_path)

    record = evidence_store.save_evidence(
        b"\x89PNG\r\n\x1a\nexample",
        mime_type="image/png",
        order_id="TR-4521",
        item_id="TR-DRS-014",
        reason="damaged",
        customer_email="customer@example.com",
    )
    evidence_store.attach_ticket(record["evidence_id"], "ESC-TEST-001")

    assert (evidence_dir / record["filename"]).read_bytes().startswith(b"\x89PNG")
    registry = json.loads(index_path.read_text(encoding="utf-8"))
    assert registry["records"][0]["order_id"] == "TR-4521"
    assert registry["records"][0]["ticket_id"] == "ESC-TEST-001"
