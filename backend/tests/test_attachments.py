"""Attachments: upload, byte-equal download, size limit, deletion, sanitisation."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Attachment
from app.services.storage import sanitise_filename
from tests.conftest import missing_uuid

PAYLOAD = b"PK\x03\x04 binary \x00\xff payload " + bytes(range(256))


def _upload(
    client: TestClient,
    customer_id: str,
    *,
    content: bytes = PAYLOAD,
    filename: str = "report.bin",
    content_type: str = "application/octet-stream",
    note_id: str | None = None,
) -> dict:
    data = {"note_id": note_id} if note_id else None
    res = client.post(
        f"/api/customers/{customer_id}/attachments",
        files={"file": (filename, content, content_type)},
        data=data,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_upload_records_metadata(client: TestClient, customer: dict) -> None:
    body = _upload(client, customer["id"])
    assert body["filename"] == "report.bin"
    assert body["content_type"] == "application/octet-stream"
    assert body["size_bytes"] == len(PAYLOAD)
    assert body["note_id"] is None
    assert body["customer_id"] == customer["id"]


def test_download_round_trip_is_byte_equal(client: TestClient, customer: dict) -> None:
    created = _upload(client, customer["id"])
    res = client.get(f"/api/attachments/{created['id']}")
    assert res.status_code == 200
    assert res.content == PAYLOAD
    assert 'filename="report.bin"' in res.headers["content-disposition"]


def test_upload_writes_exactly_one_file_under_the_root(
    client: TestClient, customer: dict, attachments_dir: Path
) -> None:
    _upload(client, customer["id"])
    files = [p for p in attachments_dir.rglob("*") if p.is_file()]
    assert len(files) == 1
    assert files[0].read_bytes() == PAYLOAD
    # Stored as <root>/<yyyy>/<mm>/<uuid>_<name>
    assert files[0].parent.parent.parent == attachments_dir


def test_list_attachments(client: TestClient, customer: dict) -> None:
    _upload(client, customer["id"], filename="a.txt", content=b"a")
    _upload(client, customer["id"], filename="b.txt", content=b"b")
    rows = client.get(f"/api/customers/{customer['id']}/attachments").json()
    assert {r["filename"] for r in rows} == {"a.txt", "b.txt"}


def test_attach_to_note(client: TestClient, customer: dict) -> None:
    note = client.post(
        f"/api/customers/{customer['id']}/notes", json={"body": "with file"}
    ).json()
    created = _upload(client, customer["id"], note_id=note["id"])
    assert created["note_id"] == note["id"]


def test_attach_to_note_of_another_customer_returns_404(
    client: TestClient, customer: dict
) -> None:
    other = client.post("/api/customers", json={"display_name": "Other"}).json()
    note = client.post(
        f"/api/customers/{other['id']}/notes", json={"body": "theirs"}
    ).json()

    res = client.post(
        f"/api/customers/{customer['id']}/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
        data={"note_id": note["id"]},
    )
    assert res.status_code == 404


def test_oversize_upload_rejected_with_413(
    client: TestClient, customer: dict, attachments_dir: Path, small_upload_limit: int
) -> None:
    res = client.post(
        f"/api/customers/{customer['id']}/attachments",
        files={"file": ("big.bin", b"x" * (small_upload_limit + 1), "text/plain")},
    )
    assert res.status_code == 413

    # No row and no partial file left behind.
    assert client.get(f"/api/customers/{customer['id']}/attachments").json() == []
    assert [p for p in attachments_dir.rglob("*") if p.is_file()] == []


def test_upload_at_exactly_the_limit_is_accepted(
    client: TestClient, customer: dict, small_upload_limit: int
) -> None:
    body = _upload(client, customer["id"], content=b"y" * small_upload_limit)
    assert body["size_bytes"] == small_upload_limit


def test_delete_removes_row_and_file(
    client: TestClient, customer: dict, attachments_dir: Path, db: Session
) -> None:
    created = _upload(client, customer["id"])
    stored = [p for p in attachments_dir.rglob("*") if p.is_file()]
    assert len(stored) == 1

    assert client.delete(f"/api/attachments/{created['id']}").status_code == 204

    assert not stored[0].exists()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Attachment)) == 0
    assert client.get(f"/api/attachments/{created['id']}").status_code == 404


def test_delete_customer_removes_attachment_rows_and_files(
    client: TestClient, customer: dict, attachments_dir: Path, db: Session
) -> None:
    _upload(client, customer["id"], filename="a.bin", content=b"aaa")
    _upload(client, customer["id"], filename="b.bin", content=b"bbb")
    assert len([p for p in attachments_dir.rglob("*") if p.is_file()]) == 2

    assert client.delete(f"/api/customers/{customer['id']}").status_code == 204

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Attachment)) == 0
    assert [p for p in attachments_dir.rglob("*") if p.is_file()] == []


def test_deleting_note_removes_its_attachments(
    client: TestClient, customer: dict, attachments_dir: Path, db: Session
) -> None:
    note = client.post(
        f"/api/customers/{customer['id']}/notes", json={"body": "doomed"}
    ).json()
    _upload(client, customer["id"], note_id=note["id"])

    assert client.delete(f"/api/notes/{note['id']}").status_code == 204

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Attachment)) == 0
    assert [p for p in attachments_dir.rglob("*") if p.is_file()] == []


def test_unknown_attachment_returns_404(client: TestClient) -> None:
    assert client.get(f"/api/attachments/{missing_uuid()}").status_code == 404
    assert client.delete(f"/api/attachments/{missing_uuid()}").status_code == 404


def test_upload_for_unknown_customer_returns_404(client: TestClient) -> None:
    res = client.post(
        f"/api/customers/{missing_uuid()}/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert res.status_code == 404


def test_hostile_filename_is_sanitised_on_disk_but_preserved_in_metadata(
    client: TestClient, customer: dict, attachments_dir: Path
) -> None:
    hostile = "../../etc/passwd"
    created = _upload(client, customer["id"], filename=hostile, content=b"secret")

    # Original kept for display...
    assert created["filename"].endswith("passwd")
    # ...but nothing escaped the storage root.
    files = [p for p in attachments_dir.rglob("*") if p.is_file()]
    assert len(files) == 1
    assert attachments_dir.resolve() in files[0].resolve().parents
    assert "/" not in files[0].name and "\\" not in files[0].name


def test_sanitise_filename_cases() -> None:
    assert sanitise_filename("report.pdf") == "report.pdf"
    assert "/" not in sanitise_filename("a/b/c.txt")
    assert "\\" not in sanitise_filename("a\\b\\c.txt")
    assert sanitise_filename("../../evil") == "evil"
    assert sanitise_filename("") == "upload"
    assert sanitise_filename("...") == "upload"
    assert len(sanitise_filename("x" * 500)) <= 120


def test_unicode_filename_download(client: TestClient, customer: dict) -> None:
    created = _upload(client, customer["id"], filename="ré—sumé 客戶.txt", content=b"cv")
    assert created["filename"] == "ré—sumé 客戶.txt"
    res = client.get(f"/api/attachments/{created['id']}")
    assert res.status_code == 200
    assert res.content == b"cv"
