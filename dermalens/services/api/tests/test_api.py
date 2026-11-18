import uuid

import pytest

from app import pipeline
from app.db import SessionLocal
from app import models as M
from dermalens_inference.testing import synth_face

API = "/api/v1"
NO_FLAGS = None


def all_flags_no(client):
    return {f["code"]: False for f in client.get(f"{API}/reference/red-flags").json()}


def register(client, email=None):
    email = email or f"p-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(f"{API}/auth/register", json={"email": email, "password": "CorrectHorse9!", "accepted_boundary": True})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()


def login(client, email, pw):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def fake_inference(grades=None, quality=True, refer=0.02, ood=False):
    grades = grades or {}

    def run(images):
        labels = {}
        for c in ("acne", "hyperpigmentation", "erythema", "texture"):
            g = grades.get(c, "none")
            labels[c] = {"p": 0.85 if g != "none" else 0.1, "present": g != "none", "grade": g, "uncertain": False}
        return {"model_version_id": "dl-stub-0.1.0", "quality_pass": quality, "ood_score": 0.9 if ood else 0.1,
                "ood_flag": ood, "refer_out_probability": refer, "thresholds": {"refer_out": 0.3},
                "labels": labels, "quality": {}, "latency_ms": 5}
    return run


def assess(client, h, intake=None, profile=None, images=None):
    client.put(f"{API}/me/profile", headers=h, json=profile or {"full_name": "Maria Clara Santos", "birth_year": 1998,
                                                                 "skin_type": "oily", "self_fitzpatrick": 4})
    body = intake or {"concerns": [{"code": "acne", "self_severity": 2, "duration_weeks": 6}],
                      "red_flags": all_flags_no(client)}
    r = client.post(f"{API}/intakes", headers=h, json=body)
    assert r.status_code == 201, r.text
    intake_id = r.json()["intake_id"]
    r = client.post(f"{API}/sessions", headers=h, json={"intake_id": intake_id})
    assert r.status_code == 201
    sid, urls = r.json()["session_id"], r.json()["upload_urls"]
    upload_views(client, h, sid, urls, images)
    return sid


def upload_views(client, h, sid, urls, images=None):
    images = images or {v: synth_face(n) for n, v in enumerate(("front", "left45", "right45"))}
    for view, url in urls.items():
        up = client.put(url, content=images[view], headers={"Content-Type": "image/jpeg"})
        assert up.status_code == 200, up.text
        reg = client.post(f"{API}/sessions/{sid}/images", headers=h,
                          json={"view": view, **up.json(), "device_checks": {"face_present": True}})
        assert reg.status_code == 201, reg.text


def submit(client, h, sid):
    r = client.post(f"{API}/sessions/{sid}/submit", headers=h)
    assert r.status_code == 202, r.text
    return client.get(f"{API}/sessions/{sid}/result", headers=h).json()


# ----------------------------------------------------------------------------

def test_auth_refresh_rotation_and_reuse(client):
    _, tok = register(client)
    r1 = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r1.status_code == 200
    reuse = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert reuse.status_code == 401
    # Reuse revokes the whole family, including the newest token.
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]}).status_code == 401


def test_register_requires_boundary_ack(client):
    r = client.post(f"{API}/auth/register", json={"email": "x@example.com", "password": "CorrectHorse9!",
                                                  "accepted_boundary": False})
    assert r.status_code == 422


def test_intake_requires_every_red_flag(client):
    h, _ = register(client)
    r = client.post(f"{API}/intakes", headers=h, json={"red_flags": {"changing_mole": False}})
    assert r.status_code == 422


def test_full_flow_with_stub_model_summary_and_clinic(client):
    h, _ = register(client)
    sid = assess(client, h)
    res = submit(client, h, sid)
    assert res["status"] in ("complete", "needs_retake"), res
    if res["status"] == "needs_retake":
        pytest.fail(f"synthetic images should pass quality: {res}")
    assert res["route"]["code"] in ("self_care", "iconic_clinic", "dermatologist")
    assert res["boundary"].startswith("DermaLens provides general skincare information")
    assert res["versions"]["model"] == "dl-stub-0.1.0"
    if res["route"]["code"] != "dermatologist":
        assert res["routine"]["status"] == "ok"
        assert res["routine"]["am"][-1]["slot"] == "sunscreen"
        for step in res["routine"]["am"] + res["routine"]["pm"]:
            assert step["product"]["fda_notification_no"]

    # Sharing needs consent.
    r = client.post(f"{API}/sessions/{sid}/summary", headers=h, json={"share_with_iconic": True})
    assert r.status_code == 403
    client.post(f"{API}/consents", headers=h, json={"purpose": "share_with_clinic", "granted": True})
    r = client.post(f"{API}/sessions/{sid}/summary", headers=h, json={"share_with_iconic": True})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["data"]["patient"]["initials"] == "M.C.S."
    assert s["data"]["patient"]["age_band"].endswith("9")
    pdf = client.get(f"{API}/summaries/{s['summary_id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    # Clinic staff side.
    staff = login(client, "staff.dev@example.com", "StaffPass!2026")
    assert client.get(f"{API}/clinic/summaries", headers=h).status_code == 403  # patient cannot
    lst = client.get(f"{API}/clinic/summaries", headers=staff).json()
    assert any(x["summary_id"] == s["summary_id"] for x in lst)
    token = s["share_url"].rsplit("/", 1)[1]
    assert client.get(f"{API}/clinic/s/{token}", headers=staff).status_code == 200
    assert client.get(f"{API}/clinic/s/{token}").status_code == 401  # QR needs staff login
    rv = client.patch(f"{API}/clinic/summaries/{s['summary_id']}", headers=staff,
                      json={"reviewed": True, "staff_note": "Booked for consult"})
    assert rv.json()["reviewed"] is True
    with SessionLocal() as db:
        actions = {a.action for a in db.query(M.AuditLog).filter_by(entity_id=s["summary_id"])}
    assert {"export_pdf", "download_pdf", "view_summary_qr", "review_summary"} <= actions


def test_moderate_concern_routes_to_iconic_with_routine(client, monkeypatch):
    monkeypatch.setattr(pipeline, "run_inference", fake_inference({"acne": "moderate", "texture": "mild"}))
    h, _ = register(client)
    res = submit(client, h, assess(client, h))
    assert res["route"]["code"] == "iconic_clinic"
    assert res["routine"]["status"] == "ok"
    assert any(f["code"] == "acne" and f["grade"] == "moderate" for f in res["findings"])


def test_allergen_family_never_recommended(client, monkeypatch):
    monkeypatch.setattr(pipeline, "run_inference", fake_inference({"acne": "moderate"}))
    h, _ = register(client)
    body = {"concerns": [{"code": "acne", "self_severity": 2, "duration_weeks": 4}],
            "red_flags": all_flags_no(client), "allergens": [{"family_code": "bha"}, {"raw_text": "kamias soap"}]}
    res = submit(client, h, assess(client, h, intake=body))
    bha_ings = {"salicylic_acid"}
    for step in res["routine"]["am"] + res["routine"]["pm"]:
        assert not bha_ings & set(step["product"]["ingredients"])


def test_urgent_intake_gives_urgent_route_and_no_routine(client):
    h, _ = register(client)
    flags = all_flags_no(client)
    flags["rapid_swelling"] = True
    r = client.post(f"{API}/intakes", headers=h, json={"red_flags": flags})
    assert r.json()["urgent"] is True
    res = submit(client, h, assess(client, h, intake={"red_flags": flags}))
    assert res["route"]["code"] == "urgent_care"
    assert res["routine"] is None
    assert res["findings"] == []


def test_red_flag_routes_to_dermatologist_basics_only(client, monkeypatch):
    monkeypatch.setattr(pipeline, "run_inference", fake_inference({"hyperpigmentation": "moderate"}))
    h, _ = register(client)
    flags = all_flags_no(client)
    flags["changing_mole"] = True
    res = submit(client, h, assess(client, h, intake={"red_flags": flags}))
    assert res["route"]["code"] == "dermatologist"
    assert res["routine"]["basics_only"] is True
    assert {s["slot"] for s in res["routine"]["am"] + res["routine"]["pm"]} <= {"cleanser", "moisturizer", "sunscreen"}


def test_quality_fail_asks_one_retake_then_refers(client):
    h, _ = register(client)
    dark = {v: synth_face(n, brightness=0.3) for n, v in enumerate(("front", "left45", "right45"))}
    sid = assess(client, h, images=dark)
    res = submit(client, h, sid)
    assert res["status"] == "needs_retake"
    assert set(res["retake_views"]) == {"front", "left45", "right45"}
    urls = client.post(f"{API}/sessions/{sid}/upload-urls", headers=h).json()["upload_urls"]
    upload_views(client, h, sid, urls, images=dark)
    res = submit(client, h, sid)
    assert res["status"] == "complete"
    assert res["route"]["code"] == "dermatologist"
    assert res["reasons"][0]["code"] == "quality:failed"


def test_register_falls_back_when_quality_cache_is_empty(client):
    from app.routers.patient import _QUALITY_CACHE

    _QUALITY_CACHE.clear()
    h, _ = register(client)
    sid = assess(client, h)
    assert submit(client, h, sid)["status"] == "complete"


def test_upload_token_tamper_rejected(client):
    h, _ = register(client)
    body = {"red_flags": all_flags_no(client)}
    iid = client.post(f"{API}/intakes", headers=h, json=body).json()["intake_id"]
    urls = client.post(f"{API}/sessions", headers=h, json={"intake_id": iid}).json()["upload_urls"]
    bad = urls["front"][:-1] + ("0" if urls["front"][-1] != "0" else "1")
    assert client.put(bad, content=synth_face()).status_code == 403


def test_other_users_session_hidden(client):
    h1, _ = register(client)
    h2, _ = register(client)
    sid = assess(client, h1)
    assert client.get(f"{API}/sessions/{sid}/result", headers=h2).status_code == 404


def test_admin_catalog_rules_and_jobs(client):
    a = login(client, "admin.dev@example.com", "AdminPass!2026")
    base = {"brand": "Test", "name": "X", "category": "serum", "suitable_skin_types": ["all"]}
    r = client.post(f"{API}/admin/products", headers=a, json={**base, "id": "t-drug", "inci": ["aqua", "tretinoin"]})
    assert r.status_code == 422 and "drug_ingredients" in r.text
    r = client.post(f"{API}/admin/products", headers=a, json={**base, "id": "t-unmapped", "inci": ["aqua", "unobtanium"]})
    assert r.status_code == 422 and "unmapped_inci" in r.text
    r = client.post(f"{API}/admin/products", headers=a, json={**base, "id": "t-ok", "inci": ["Aqua", "Niacinamide"]})
    assert r.status_code == 201 and r.json()["is_listed"] is False
    r = client.post(f"{API}/admin/products/t-ok/verify", headers=a,
                    json={"notification_no": "SAMPLE-T-1", "evidence_uri": "s3://evidence/t-ok.pdf"})
    assert r.json()["is_listed"] is True
    v0 = client.get(f"{API}/admin/rules", headers=a).json()["rule_set_version"]
    r = client.post(f"{API}/admin/rules/conflicts", headers=a, json={"family_a": "retinoids", "family_b": "vitamin_c",
                    "scope": "same_application", "resolution": "split_am_pm", "rationale": "test rule"})
    assert r.json()["rule_set_version"] != v0
    assert client.post(f"{API}/admin/models/dl-stub-0.1.0/activate", headers=a).status_code == 409
    # Stale verification gets delisted.
    from datetime import date, timedelta
    with SessionLocal() as db:
        db.get(M.ProductFdaNotification, "t-ok").verified_on = date.today() - timedelta(days=120)
        db.commit()
    assert "t-ok" in client.post(f"{API}/admin/jobs/delist-stale", headers=a).json()["delisted"]
    # Patients cannot reach admin.
    h, _ = register(client)
    assert client.get(f"{API}/admin/products", headers=h).status_code == 403


def test_restart_frees_sessions_stuck_processing(client):
    from fastapi.testclient import TestClient
    from app.main import app

    h, _ = register(client)
    sid = assess(client, h)
    with SessionLocal() as db:
        db.get(M.CaptureSession, uuid.UUID(sid)).status = "processing"
        db.commit()
    with TestClient(app):
        pass
    with SessionLocal() as db:
        s = db.get(M.CaptureSession, uuid.UUID(sid))
        assert s.status == "failed" and s.error == "interrupted_by_restart"


def test_allergen_search_and_export_and_delete(client):
    h, tok = register(client)
    res = client.get(f"{API}/allergens/search", params={"q": "fragr"}, headers=h).json()
    assert any(x.get("family_code") == "fragrance" for x in res)
    assess(client, h)
    exp = client.get(f"{API}/me/export", headers=h).json()
    assert exp["profile"]["full_name"] == "Maria Clara Santos"
    assert client.delete(f"{API}/me", headers=h).status_code == 202
    assert client.get(f"{API}/me/profile", headers=h).status_code == 401
