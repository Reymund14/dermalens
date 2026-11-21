"""Account safety and running-in-production features."""
import re
import uuid

import pytest

from app import mailer, pipeline, ratelimit
from app import config
from app.config import settings
from app.schema_upgrade import upgrade

from .test_api import API, assess, fake_inference, login, register, submit
from .test_roles import accounts, shared_case


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, kind, subject, body: sent.append(
        {"to": to, "kind": kind, "subject": subject, "body": body}) or "logged")
    return sent


def link_token(mail, path):
    m = re.search(rf"/#/{path}/([\w-]+)", mail["body"])
    assert m, mail["body"]
    return m.group(1)


def test_signup_sends_verification_and_link_works_once(client, outbox):
    email = f"v-{uuid.uuid4().hex[:8]}@example.com"
    h, _ = register(client, email)
    assert client.get(f"{API}/auth/me", headers=h).json()["email_verified"] is False
    mail = [m for m in outbox if m["to"] == email and m["kind"] == "verify_email"][-1]
    token = link_token(mail, "verify")
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    assert client.get(f"{API}/auth/me", headers=h).json()["email_verified"] is True
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400
    # Staff accounts made by an admin, and seeded ones, count as verified.
    staff, _, _ = accounts(client)
    assert client.get(f"{API}/auth/me", headers=staff).json()["email_verified"] is True


def test_forgot_and_reset_password(client, outbox):
    email = f"r-{uuid.uuid4().hex[:8]}@example.com"
    _, tok = register(client, email)
    unknown = client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"})
    known = client.post(f"{API}/auth/forgot-password", json={"email": email.upper()})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()  # no hint about who has an account
    assert not any(m["to"] == "nobody@example.com" for m in outbox)
    token = link_token([m for m in outbox if m["kind"] == "password_reset"][-1], "reset")

    assert client.post(f"{API}/auth/reset-password", json={"token": token, "password": "short"}).status_code == 422
    assert client.post(f"{API}/auth/reset-password",
                       json={"token": token, "password": "BrandNewPass!42"}).status_code == 200
    assert client.post(f"{API}/auth/reset-password",
                       json={"token": token, "password": "AnotherPass!42"}).status_code == 400
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "CorrectHorse9!"}).status_code == 401
    login(client, email, "BrandNewPass!42")
    # Every earlier session is signed out.
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_lockout_after_repeated_wrong_passwords(client):
    email = f"l-{uuid.uuid4().hex[:8]}@example.com"
    register(client, email)
    for _ in range(settings.max_failed_logins):
        assert client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    r = client.post(f"{API}/auth/login", json={"email": email, "password": "CorrectHorse9!"})
    assert r.status_code == 423 and "locked" in r.json()["detail"]


def test_admin_password_reset_unlocks_staff(client):
    _, _, admin = accounts(client)
    email = f"s-{uuid.uuid4().hex[:8]}@example.com"
    uid = client.post(f"{API}/admin/users", headers=admin, json={
        "email": email, "role": "clinic_staff", "display_name": "Front Desk 2", "password": "FrontDesk!2026"}).json()["id"]
    for _ in range(settings.max_failed_logins):
        client.post(f"{API}/auth/login", json={"email": email, "password": "nope-nope-nope"})
    users = {u["id"]: u for u in client.get(f"{API}/admin/users", headers=admin).json()}
    assert users[uid]["locked"] is True
    assert client.get(f"{API}/notifications", headers=admin).json()["locked_accounts"] >= 1
    client.patch(f"{API}/admin/users/{uid}", headers=admin, json={"password": "FrontDesk!2027"})
    login(client, email, "FrontDesk!2027")


def test_change_password_needs_current_and_signs_out_others(client):
    email = f"c-{uuid.uuid4().hex[:8]}@example.com"
    h, tok = register(client, email)
    bad = client.post(f"{API}/auth/change-password", headers=h,
                      json={"current_password": "not-it-at-all", "new_password": "NewPassword!77"})
    assert bad.status_code == 400
    ok = client.post(f"{API}/auth/change-password", headers=h,
                     json={"current_password": "CorrectHorse9!", "new_password": "NewPassword!77"})
    assert ok.status_code == 200 and ok.json()["refresh_token"]
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": ok.json()["refresh_token"]}).status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401
    login(client, email, "NewPassword!77")


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limits", True)
    ratelimit.reset()
    try:
        codes = [client.post(f"{API}/auth/login", json={"email": "ghost@example.com", "password": "x"}).status_code
                 for _ in range(11)]
    finally:
        ratelimit.reset()
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_rate_limit_header(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limits", True)
    ratelimit.reset()
    try:
        for _ in range(3):
            client.post(f"{API}/auth/forgot-password", json={"email": "ghost2@example.com"})
        r = client.post(f"{API}/auth/forgot-password", json={"email": "ghost2@example.com"})
    finally:
        ratelimit.reset()
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_security_headers_and_health(client):
    r = client.get(f"{API}/reference/red-flags")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert "x-request-id" in r.headers
    h = client.get("/health")
    assert h.status_code == 200 and h.json()["database"] == "ok"
    assert "content-security-policy" not in client.get("/docs").headers  # Swagger needs its scripts


def test_production_mode_refuses_dev_settings(monkeypatch):
    # The original build has no development defaults: missing secrets fail outright.
    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        config.Settings()
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("DATA_KEY", "")
    with pytest.raises(RuntimeError, match="DATA_KEY"):
        config.Settings()


def test_schema_upgrade_is_repeatable():
    assert upgrade() == []


def test_notifications_and_clinic_email(client, monkeypatch, outbox):
    monkeypatch.setattr(settings, "clinic_notify_email", "frontdesk@iconic.example")
    staff, derm, admin = accounts(client)
    before = client.get(f"{API}/notifications", headers=staff).json()
    shared_case(client, monkeypatch, {"acne": "moderate"})
    after = client.get(f"{API}/notifications", headers=staff).json()
    assert after["inbox_new"] == before["inbox_new"] + 1
    assert client.get(f"{API}/notifications", headers=derm).json()["queue_todo"] >= 1
    assert "catalog_due" in client.get(f"{API}/notifications", headers=admin).json()
    mail = [m for m in outbox if m["kind"] == "clinic_new_case"][-1]
    assert mail["to"] == "frontdesk@iconic.example"
    assert "acne" not in mail["body"].lower()  # no health details by email


def test_second_check_compares_with_previous(client, monkeypatch):
    monkeypatch.setattr(pipeline, "run_inference", fake_inference({"acne": "moderate", "texture": "mild"}))
    h, _ = register(client)
    first = submit(client, h, assess(client, h))
    assert first["compare"] is None
    monkeypatch.setattr(pipeline, "run_inference", fake_inference({"acne": "mild", "texture": "mild",
                                                                    "erythema": "mild"}))
    second = submit(client, h, assess(client, h))
    trends = {c["code"]: c["trend"] for c in second["compare"]["concerns"]}
    assert trends["acne"] == "better"
    assert trends["texture"] == "same"
    assert trends["erythema"] == "worse"
    assert second["compare"]["previous_session_id"] == first["session_id"]
