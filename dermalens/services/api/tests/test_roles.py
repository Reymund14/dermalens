"""Role-based access: clinic staff, dermatologist and admin."""
from app import models as M
from app import pipeline
from app.db import SessionLocal

from .test_api import API, assess, fake_inference, login, register, submit


def shared_case(client, monkeypatch, grades):
    monkeypatch.setattr(pipeline, "run_inference", fake_inference(grades))
    h, _ = register(client)
    sid = assess(client, h)
    res = submit(client, h, sid)
    client.post(f"{API}/consents", headers=h, json={"purpose": "share_with_clinic", "granted": True})
    client.post(f"{API}/consents", headers=h, json={"purpose": "image_storage", "granted": True})
    s = client.post(f"{API}/sessions/{sid}/summary", headers=h, json={"share_with_iconic": True}).json()
    return h, res, s


def accounts(client):
    return (login(client, "staff.dev@example.com", "StaffPass!2026"),
            login(client, "derm.dev@example.com", "DermPass!2026"),
            login(client, "admin.dev@example.com", "AdminPass!2026"))


def test_me_reports_role(client):
    h, _ = register(client)
    staff, derm, admin = accounts(client)
    assert client.get(f"{API}/auth/me", headers=h).json()["role"] == "patient"
    assert client.get(f"{API}/auth/me", headers=staff).json()["role"] == "clinic_staff"
    assert client.get(f"{API}/auth/me", headers=derm).json()["role"] == "dermatologist"
    me = client.get(f"{API}/auth/me", headers=admin).json()
    assert me["role"] == "admin" and me["display_name"] == "Dev Admin"


def test_role_boundaries(client):
    h, _ = register(client)
    staff, derm, admin = accounts(client)
    for path in ("/derm/queue", "/derm/stats", "/derm/rules"):
        for who in (h, staff, admin):
            assert client.get(f"{API}{path}", headers=who).status_code == 403, path
        assert client.get(f"{API}{path}", headers=derm).status_code == 200
    for path in ("/admin/dashboard", "/admin/users", "/admin/audit", "/admin/models", "/admin/products"):
        for who in (h, staff, derm):
            assert client.get(f"{API}{path}", headers=who).status_code == 403, path
        assert client.get(f"{API}{path}", headers=admin).status_code == 200
    assert client.get(f"{API}/clinic/summaries", headers=h).status_code == 403
    for who in (staff, derm, admin):
        assert client.get(f"{API}/clinic/summaries", headers=who).status_code == 200
    # Staff and clinicians cannot use patient endpoints.
    assert client.get(f"{API}/sessions", headers=staff).status_code == 403


def test_staff_follow_up_and_photos(client, monkeypatch):
    _, _, s = shared_case(client, monkeypatch, {"acne": "moderate"})
    staff, _, _ = accounts(client)
    sid = s["summary_id"]
    d = client.get(f"{API}/clinic/summaries/{sid}", headers=staff).json()
    assert d["follow_up_status"] == "new" and set(d["views"]) == {"front", "left45", "right45"}
    assert "full_name" not in str(d["data"]["patient"])  # initials only
    img = client.get(f"{API}/clinic/summaries/{sid}/images/front", headers=staff)
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"
    r = client.patch(f"{API}/clinic/summaries/{sid}", headers=staff, json={"follow_up_status": "booked"}).json()
    assert r["follow_up_status"] == "booked" and r["reviewed"] is False
    r = client.patch(f"{API}/clinic/summaries/{sid}", headers=staff, json={"reviewed": True}).json()
    assert r["reviewed"] is True and r["reviewed_by"] == "Dev Front Desk" and r["follow_up_status"] == "booked"
    lst = client.get(f"{API}/clinic/summaries?follow_up=booked", headers=staff).json()
    assert [x["summary_id"] for x in lst] == [sid]
    assert client.patch(f"{API}/clinic/summaries/{sid}", headers=staff,
                        json={"follow_up_status": "lost"}).status_code == 422


def test_dermatologist_review_and_agreement(client, monkeypatch):
    _, res_a, a = shared_case(client, monkeypatch, {"acne": "moderate"})          # app: iconic_clinic
    _, res_b, b = shared_case(client, monkeypatch, {"hyperpigmentation": "mild"})  # app: self_care or iconic
    _, derm, _ = accounts(client)
    q = client.get(f"{API}/derm/queue", headers=derm).json()
    assert {a["summary_id"], b["summary_id"]} <= {x["summary_id"] for x in q}

    r = client.post(f"{API}/derm/summaries/{a['summary_id']}/review", headers=derm,
                    json={"derm_route": "dermatologist", "concern_agreement": {"acne": True}, "note": "nodules"})
    assert r.status_code == 201, r.text
    assert r.json()["app_route"] == res_a["route"]["code"] == "iconic_clinic"
    client.post(f"{API}/derm/summaries/{b['summary_id']}/review", headers=derm,
                json={"derm_route": res_b["route"]["code"], "concern_agreement": {"hyperpigmentation": False}})
    # Editing a review replaces it rather than adding a second one.
    client.post(f"{API}/derm/summaries/{b['summary_id']}/review", headers=derm,
                json={"derm_route": res_b["route"]["code"], "concern_agreement": {"hyperpigmentation": True}})
    bad = client.post(f"{API}/derm/summaries/{b['summary_id']}/review", headers=derm,
                      json={"derm_route": "self_care", "concern_agreement": {"rosacea_x": True}})
    assert bad.status_code == 422

    q = client.get(f"{API}/derm/queue", headers=derm).json()
    assert a["summary_id"] not in {x["summary_id"] for x in q}  # reviewed cases leave the queue
    st = client.get(f"{API}/derm/stats", headers=derm).json()
    assert st["reviews"] == 2 and st["route_agreement"] == 0.5
    assert st["missed_referrals"] == 1 and st["missed_referral_cases"] == [a["summary_id"]]
    assert st["concern_agreement"]["acne"]["rate"] == 1.0
    assert st["concern_agreement"]["hyperpigmentation"] == {"agree": 1, "of": 1, "rate": 1.0}


def test_rule_signoff_tracks_version(client):
    _, derm, admin = accounts(client)
    r = client.get(f"{API}/derm/rules", headers=derm).json()
    assert r["signed_off"] is False and len(r["red_flags"]) == 11 and r["conflicts"]
    s = client.post(f"{API}/derm/rules/signoff", headers=derm, json={"note": "Reviewed red flags"})
    assert s.status_code == 201
    assert client.get(f"{API}/derm/rules", headers=derm).json()["signed_off"] is True
    assert client.get(f"{API}/admin/dashboard", headers=admin).json()["rules_signed_off"] is True
    # A rule change by the admin bumps the version and voids the sign-off.
    client.post(f"{API}/admin/rules/conflicts", headers=admin,
                json={"family_a": "aha", "family_b": "vitamin_c", "scope": "same_routine",
                      "resolution": "split_am_pm", "rationale": "test"})
    r = client.get(f"{API}/derm/rules", headers=derm).json()
    assert r["signed_off"] is False and len(r["signoffs"]) == 1


def test_admin_accounts(client):
    staff, _, admin = accounts(client)
    r = client.post(f"{API}/admin/users", headers=admin,
                    json={"email": "nurse@example.com", "role": "clinic_staff", "display_name": "Nurse Ana",
                          "password": "NursePass!2026"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert client.post(f"{API}/admin/users", headers=admin,
                       json={"email": "x@example.com", "role": "patient", "display_name": "X",
                             "password": "Whatever!2026"}).status_code == 422
    nurse = login(client, "nurse@example.com", "NursePass!2026")
    assert client.get(f"{API}/clinic/summaries", headers=nurse).status_code == 200

    # Disable: existing token stops working, login refused, refresh refused.
    rt = client.post(f"{API}/auth/login", json={"email": "nurse@example.com", "password": "NursePass!2026"}).json()
    assert client.patch(f"{API}/admin/users/{uid}", headers=admin, json={"disabled": True}).json()["disabled"]
    assert client.get(f"{API}/clinic/summaries", headers=nurse).status_code == 401
    assert client.post(f"{API}/auth/login",
                       json={"email": "nurse@example.com", "password": "NursePass!2026"}).status_code == 403
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": rt["refresh_token"]}).status_code == 401

    # Re-enable with a reset password and a new role.
    client.patch(f"{API}/admin/users/{uid}", headers=admin,
                 json={"disabled": False, "password": "NewNursePass!2026", "role": "dermatologist"})
    assert client.post(f"{API}/auth/login",
                       json={"email": "nurse@example.com", "password": "NursePass!2026"}).status_code == 401
    d = login(client, "nurse@example.com", "NewNursePass!2026")
    assert client.get(f"{API}/derm/queue", headers=d).status_code == 200

    me = client.get(f"{API}/auth/me", headers=admin).json()["id"]
    assert client.patch(f"{API}/admin/users/{me}", headers=admin, json={"disabled": True}).status_code == 409
    assert client.patch(f"{API}/admin/users/{me}", headers=admin, json={"role": "clinic_staff"}).status_code == 409
    users = client.get(f"{API}/admin/users", headers=admin).json()
    assert all(u["role"] != "patient" for u in users)
    log = client.get(f"{API}/admin/audit?action=update_user", headers=admin).json()
    assert len(log) >= 2 and log[0]["actor"]["name"] == "Dev Admin"


def test_admin_dashboard_and_audit_hide_patients(client, monkeypatch):
    shared_case(client, monkeypatch, {"acne": "moderate"})
    _, _, admin = accounts(client)
    d = client.get(f"{API}/admin/dashboard", headers=admin).json()
    assert d["users"]["patient"] >= 1 and d["users"]["dermatologist"] >= 1
    assert d["shared_summaries"] >= 1 and d["unreviewed_summaries"] >= 1
    with SessionLocal() as db:
        assert d["products_listed"] == db.query(M.Product).filter_by(is_listed=True).count() > 0
    log = client.get(f"{API}/admin/audit?action=register", headers=admin).json()
    assert log and all(r["actor"]["name"] == "patient" for r in log)
    with SessionLocal() as db:
        emails = {u.email for u in db.query(M.User).filter_by(role="patient")}
    assert not emails & {str(r) for r in log}
