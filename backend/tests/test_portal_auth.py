"""Portal signup, login, logout, and /auth/me."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.portal import PortalUser


def test_signup_succeeds_for_matching_active_customer_email(
    client: TestClient, customer_email_contact: dict
) -> None:
    res = client.post(
        "/api/portal/auth/signup",
        json={
            "email": customer_email_contact["value"],
            "password": "hunter2pass",
            "display_name": "Acme Owner",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token"]
    assert body["expires_at"]
    assert body["portal_user"]["email"] == customer_email_contact["value"]
    assert body["portal_user"]["customer_id"] == customer_email_contact["customer_id"]


def test_signup_returns_403_when_no_contact_matches(client: TestClient) -> None:
    res = client.post(
        "/api/portal/auth/signup",
        json={
            "email": "nobody@example.com",
            "password": "hunter2pass",
            "display_name": "Nobody",
        },
    )
    assert res.status_code == 403, res.text


def test_signup_returns_same_403_when_matching_customer_is_archived(
    client: TestClient, customer: dict, customer_email_contact: dict
) -> None:
    archived = client.post(f"/api/customers/{customer['id']}/archive")
    assert archived.status_code == 200, archived.text

    res_archived = client.post(
        "/api/portal/auth/signup",
        json={
            "email": customer_email_contact["value"],
            "password": "hunter2pass",
            "display_name": "Acme Owner",
        },
    )
    res_no_match = client.post(
        "/api/portal/auth/signup",
        json={
            "email": "nobody@example.com",
            "password": "hunter2pass",
            "display_name": "Nobody",
        },
    )
    assert res_archived.status_code == 403, res_archived.text
    assert res_no_match.status_code == 403, res_no_match.text
    assert res_archived.json()["detail"] == res_no_match.json()["detail"]


def test_signup_returns_409_on_duplicate_email(
    client: TestClient, portal_auth: dict, customer_email_contact: dict
) -> None:
    res = client.post(
        "/api/portal/auth/signup",
        json={
            "email": customer_email_contact["value"],
            "password": "anotherpass1",
            "display_name": "Second Signup",
        },
    )
    assert res.status_code == 409, res.text


def test_signup_password_shorter_than_8_chars_is_422(
    client: TestClient, customer_email_contact: dict
) -> None:
    res = client.post(
        "/api/portal/auth/signup",
        json={
            "email": customer_email_contact["value"],
            "password": "short",
            "display_name": "Acme Owner",
        },
    )
    assert res.status_code == 422, res.text


def test_login_succeeds_and_returns_a_usable_token(
    client: TestClient, portal_auth: dict, customer_email_contact: dict
) -> None:
    res = client.post(
        "/api/portal/auth/login",
        json={"email": customer_email_contact["value"], "password": "hunter2pass"},
    )
    assert res.status_code == 200, res.text
    token = res.json()["token"]

    me = client.get("/api/portal/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == customer_email_contact["value"]


def test_login_fails_identically_for_unknown_email_wrong_password_and_inactive_user(
    client: TestClient,
    db: Session,
    portal_auth: dict,
    portal_user: dict,
    customer_email_contact: dict,
) -> None:
    unknown = client.post(
        "/api/portal/auth/login",
        json={"email": "unknown@example.com", "password": "whatever12"},
    )
    wrong_password = client.post(
        "/api/portal/auth/login",
        json={"email": customer_email_contact["value"], "password": "wrongpassword"},
    )

    row = db.get(PortalUser, uuid.UUID(portal_user["id"]))
    assert row is not None
    row.is_active = False
    db.commit()

    inactive = client.post(
        "/api/portal/auth/login",
        json={"email": customer_email_contact["value"], "password": "hunter2pass"},
    )

    assert unknown.status_code == 403, unknown.text
    assert wrong_password.status_code == 403, wrong_password.text
    assert inactive.status_code == 403, inactive.text
    assert unknown.json()["detail"] == wrong_password.json()["detail"] == inactive.json()["detail"]


def test_logout_revokes_the_session(portal_client: TestClient, portal_auth: dict) -> None:
    res = portal_client.post("/api/portal/auth/logout")
    assert res.status_code == 204, res.text

    second = portal_client.post("/api/portal/auth/logout")
    assert second.status_code == 401, second.text

    me = portal_client.get("/api/portal/auth/me")
    assert me.status_code == 401, me.text


def test_me_returns_the_callers_own_identity(
    portal_client: TestClient, portal_user: dict
) -> None:
    res = portal_client.get("/api/portal/auth/me")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == portal_user["id"]
    assert body["email"] == portal_user["email"]


def test_unauthenticated_me_is_401(client: TestClient) -> None:
    res = client.get("/api/portal/auth/me")
    assert res.status_code == 401, res.text
