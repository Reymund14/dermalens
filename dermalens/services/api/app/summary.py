"""Exportable pre-screening consultation summary (JSON + two-page A4 PDF)."""
from __future__ import annotations

import base64
import io
from datetime import datetime
from html import escape

from PIL import Image
from sqlalchemy.orm import Session

from dermalens_rules import copy as C

from . import models as M
from . import storage
from .config import settings
from .pipeline import current_images
from .present import session_result
from .security import decrypt


def _initials(name: str | None) -> str:
    if not name:
        return "—"
    return "".join(part[0].upper() + "." for part in name.split() if part)[:6]


def _age_band(birth_year: int | None) -> str:
    if not birth_year:
        return "not given"
    age = datetime.now().year - birth_year
    lo = (age // 10) * 10
    return f"{lo}–{lo + 9}"


def build_data(db: Session, s: M.CaptureSession, summary_id: str) -> dict:
    res = session_result(db, s)
    intake = db.get(M.IntakeRow, s.intake_id)
    profile = db.get(M.PatientProfile, s.user_id)
    concerns = {c.code: c.display_name for c in db.query(M.Concern)}
    flags = {f.code: f.question_text for f in db.query(M.RedFlagDefinition)}
    allergens = db.query(M.UserAllergen).filter_by(user_id=s.user_id).all()
    imgs = current_images(s)
    return {
        "summary_id": summary_id,
        "title": "Pre-screening summary — not a diagnosis",
        "generated_at": datetime.now().isoformat(timespec="minutes"),
        "patient": {
            "initials": _initials(decrypt(profile.full_name_enc) if profile else None),
            "age_band": _age_band(profile.birth_year if profile else None),
            "skin_type": profile.skin_type if profile else None,
            "self_fitzpatrick": profile.self_fitzpatrick if profile else None,
            "pregnant_or_breastfeeding": bool(profile and profile.is_pregnant_or_breastfeeding),
        },
        "route": res.get("route"),
        "reasons": res.get("reasons", []),
        "patient_reported": {
            "concerns": [{"name": concerns.get(c.concern_code, c.concern_code), "bothersome_1to3": c.self_severity,
                          "duration_weeks": c.duration_weeks} for c in intake.concerns],
            "red_flags": [{"question": flags[f.red_flag_code], "answer": "Yes" if f.answer else "No"}
                          for f in intake.red_flags],
            "allergies": [a.ingredient_id or a.family_code or f"(unmapped) {a.raw_text}" for a in allergens],
            "current_routine": [{"time": r.time_of_day, "product": r.product_id or r.free_text_name,
                                 "reaction": r.reaction_reported} for r in intake.routine_items],
            "on_isotretinoin": intake.on_isotretinoin, "rx_topicals": intake.current_rx_topicals,
            "lifestyle": {"sleep_hours": float(intake.sleep_hours) if intake.sleep_hours is not None else None,
                          "sun_minutes_per_day": intake.daily_sun_exposure_min,
                          "sunscreen_use": intake.sunscreen_use, "smoker": intake.smoker,
                          "stress_1to5": intake.stress_level, "water_glasses": intake.water_glasses_per_day},
        },
        "visual_prescreen": res.get("findings", []),
        "image_quality": {v: {"pass": i.quality_pass, "checks": i.server_checks or i.device_checks}
                          for v, i in imgs.items()},
        "routine": res.get("routine"),
        "versions": res.get("versions"),
        "heatmaps": "Not available for this model version.",
        "footer": {"boundary": C.BOUNDARY_STATEMENT, "clinic_contact": settings.clinic_contact,
                   "dermatologist_note": "For persistent or changing skin problems, consult a board-certified "
                                         "dermatologist."},
    }


def _thumb(key: str) -> str:
    img = Image.open(io.BytesIO(storage.get(key))).convert("RGB")
    img.thumbnail((220, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _qr(url: str) -> str:
    import qrcode

    buf = io.BytesIO()
    qrcode.make(url, box_size=4, border=1).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def render_pdf(data: dict, image_keys: dict[str, str], share_url: str | None) -> bytes:
    from weasyprint import HTML

    e = lambda x: escape("" if x is None else str(x))  # noqa: E731
    route = data["route"] or {"title": "No route", "code": "-"}
    rows = lambda pairs: "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>" for k, v in pairs)  # noqa: E731
    pr = data["patient_reported"]
    findings = "".join(
        f"<tr><td>{e(f['name'])}</td><td>{e(f['grade_name'])}</td><td>{e(f['band'])}</td>"
        f"<td>{'uncertain' if f['uncertain'] else ''}</td></tr>" for f in data["visual_prescreen"]
    ) or "<tr><td colspan=4>Not shown for this route.</td></tr>"
    routine_html = "<p>No routine generated.</p>"
    r = data["routine"]
    if r and r.get("status") == "ok":
        def lst(items):
            return "".join(
                f"<li><b>{e(i['product']['brand'])} {e(i['product']['name'])}</b> "
                f"(FDA notif. {e(i['product']['fda_notification_no'])}) — {e(i['frequency'].replace('_', ' '))}. "
                f"{e(i['why'])}</li>" for i in items)
        routine_html = (f"<table class='cols'><tr><td><h3>AM</h3><ol>{lst(r['am'])}</ol></td>"
                        f"<td><h3>PM</h3><ol>{lst(r['pm'])}</ol></td></tr></table>")
    elif r:
        routine_html = "<p>" + e(" ".join(r.get("notes", []))) + "</p>"
    thumbs = "".join(f"<figure><img src='{_thumb(k)}'/><figcaption>{e(v)}</figcaption></figure>"
                     for v, k in image_keys.items())
    quality = "".join(
        f"<tr><td>{e(v)}</td><td>{'pass' if q['pass'] else 'fail'}</td>"
        f"<td>{e(', '.join(f'{k}: {chr(10003) if ok else chr(10007)}' for k, ok in (q['checks'] or {}).items()))}</td></tr>"
        for v, q in data["image_quality"].items())
    qr = f"<img class='qr' src='{_qr(share_url)}'/>" if share_url else ""
    ver = data["versions"] or {}
    html = f"""<!doctype html><html><head><meta charset='utf-8'><style>
      @page {{ size: A4; margin: 12mm 12mm 14mm; @bottom-center {{ content: "DermaLens pre-screening summary · page " counter(page) " of " counter(pages); font-size: 8pt; color: #666; }} }}
      body {{ font-family: sans-serif; font-size: 8.8pt; color: #1b1b1b; }}
      h1 {{ font-size: 15pt; margin: 0 0 2mm; }} h2 {{ font-size: 10.5pt; margin: 3.5mm 0 1.5mm; border-bottom: 1px solid #ccc; }}
      h3 {{ font-size: 10pt; margin: 2mm 0 1mm; }}
      table {{ border-collapse: collapse; width: 100%; }} th, td {{ text-align: left; padding: 0.7mm 2mm; vertical-align: top; border-bottom: 1px solid #eee; }}
      th {{ width: 34%; color: #444; font-weight: 600; }}
      .route {{ padding: 3mm; border-radius: 2mm; background: #eef3fb; border: 1px solid #b9cbe8; }}
      .route.urgent {{ background: #fbeaea; border-color: #e3a0a0; }} .route.caution {{ background: #fdf5e4; border-color: #e8cf94; }}
      .route.ok {{ background: #eaf6ec; border-color: #a6d3ae; }}
      figure {{ display: inline-block; margin: 0 3mm 0 0; text-align: center; }} figure img {{ height: 26mm; }}
      .qr {{ float: right; width: 26mm; }} .muted {{ color: #666; }} .boundary {{ font-size: 8.5pt; color: #444; border-top: 1px solid #ccc; padding-top: 2mm; margin-top: 4mm; }}
      .pb {{ page-break-before: always; }} table.cols td {{ width: 50%; border: none; padding: 0 3mm 0 0; }} ol {{ margin: 0; padding-left: 5mm; }} li {{ margin-bottom: 1mm; }}
    </style></head><body>
    {qr}
    <h1>{e(data['title'])}</h1>
    <p class='muted'>Patient {e(data['patient']['initials'])} · age {e(data['patient']['age_band'])} · {e(data['generated_at'])} · summary {e(data['summary_id'][:8])}</p>
    <div class='route {e(route.get('tone', ''))}'><b>Route: {e(route['title'])}</b>
      <ul>{''.join(f"<li>{e(x['text'])}</li>" for x in data['reasons'])}</ul></div>
    <h2>Patient-reported</h2>
    <table>{rows([
        ('Concerns', e('; '.join(f"{c['name']} (bothersome {c['bothersome_1to3']}/3, {c['duration_weeks']} wk)" for c in pr['concerns']) or 'none')),
        ('Health questions answered yes', e('; '.join(f['question'] for f in pr['red_flags'] if f['answer'] == 'Yes') or 'none')),
        ('Allergies', e(', '.join(pr['allergies']) or 'none declared')),
        ('Current routine', e('; '.join(f"{x['time']}: {x['product']}{' (reaction)' if x['reaction'] else ''}" for x in pr['current_routine']) or 'none')),
        ('Pregnant / breastfeeding', 'Yes' if data['patient']['pregnant_or_breastfeeding'] else 'No'),
        ('Isotretinoin / prescription topicals', f"{'Yes' if pr['on_isotretinoin'] else 'No'} / {'Yes' if pr['rx_topicals'] else 'No'}"),
        ('Skin type (self)', e(data['patient']['skin_type'])),
        ('Lifestyle', e(', '.join(f"{k.replace('_', ' ')}: {v}" for k, v in pr['lifestyle'].items() if v is not None))),
    ])}</table>
    <h2>Visual pre-screen</h2>
    <div>{thumbs}</div>
    <table><tr><th>Concern</th><th>Grade</th><th>Likelihood band</th><th></th></tr>{findings}</table>
    <h2>Suggested routine</h2>{routine_html}
    <div class='pb'></div>
    <h2>Image quality</h2><table><tr><th>View</th><th>Result</th><th>Checks</th></tr>{quality}</table>
    <h2>For clinic staff</h2><p>Heat maps: {e(data['heatmaps'])}</p>
    <h2>Versions</h2><table>{rows([
        ('Model', e(ver.get('model'))), ('Triage rules', e(ver.get('triage_rules'))),
        ('Recommendation rules', e(ver.get('recommendation_rules'))), ('Catalog snapshot', e(ver.get('catalog_snapshot_at'))),
        ('Input hash', e(ver.get('input_hash'))),
    ])}</table>
    <div class='boundary'><p>{e(data['footer']['boundary'])}</p><p>{e(data['footer']['dermatologist_note'])}</p>
    <p>{e(data['footer']['clinic_contact'])}</p></div>
    </body></html>"""
    return HTML(string=html).write_pdf()
