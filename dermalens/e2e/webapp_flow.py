"""End-to-end check of the web app (apps/web) for all four roles, at desktop size.

    python e2e/webapp_flow.py --app http://localhost:4173 --images DIR --shots DIR --api-log FILE

DIR must hold front.jpg, left45.jpg and right45.jpg (see dermalens_inference.testing.synth_face).
The API must be running with the development accounts seeded, without SMTP_HOST,
writing its log to FILE: emailed links (verification, password reset) are read from it.
"""
import argparse
import glob
import os
import re
import time
import uuid

from playwright.sync_api import expect, sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--app", default="http://localhost:4173")
ap.add_argument("--images", required=True)
ap.add_argument("--shots", required=True)
ap.add_argument("--api-log", required=True)
args = ap.parse_args()
os.makedirs(args.shots, exist_ok=True)
n = 0
chrome = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))


def shot(page, name, full=False):
    global n
    n += 1
    page.wait_for_timeout(400)
    page.screenshot(path=os.path.join(args.shots, f"w{n:02d}-{name}.png"), full_page=full)


def login(page, email, pw):
    page.goto(f"{args.app}/#/login")
    page.evaluate("sessionStorage.clear()")
    page.goto(f"{args.app}/#/login")
    page.reload()
    page.get_by_test_id("email").fill(email)
    page.get_by_test_id("password").fill(pw)
    page.get_by_test_id("auth-submit").click()


def emailed_link(to, kind):
    """The newest development email to `to` holding a #/<kind>/<token> link."""
    for _ in range(40):
        text = open(args.api_log, encoding="utf-8", errors="replace").read()
        found = None
        for part in text.split("DEV EMAIL to=")[1:]:
            m = re.search(rf"#/{kind}/([\w-]+)", part)
            if part.startswith(to) and m:
                found = m.group(0)
        if found:
            return found
        time.sleep(0.25)
    raise AssertionError(f"no {kind} email for {to}")


def run_check(page, concerns):
    tid = page.get_by_test_id
    tid("nav-check").click()
    for c in concerns:
        page.get_by_role("button", name=c).click()
    tid("next").click()
    tid("health-all-no").click()
    tid("next").click()
    tid("next").click()
    tid("next").click()
    tid("sun-40").click()
    tid("sunscreen-sometimes").click()
    tid("next").click()
    for v in ("front", "left45", "right45"):
        tid(f"photo-{v}").set_input_files(os.path.join(args.images, f"{v}.jpg"))
        expect(tid(f"ok-{v}")).to_be_visible(timeout=20000)
    tid("submit-check").click()
    expect(page.locator("[data-testid^=route-]")).to_be_visible(timeout=30000)


def sign_out(page):
    page.get_by_test_id("sign-out").click()
    expect(page.get_by_test_id("auth-submit")).to_be_visible()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome[-1] if chrome else None)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.on("dialog", lambda d: d.accept())
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    tid = page.get_by_test_id

    # --- Patient: sign up, onboarding, a full check, results, share --------------
    page.goto(f"{args.app}/#/login")
    expect(tid("auth-submit")).to_be_visible(timeout=20000)
    shot(page, "sign-in")
    tid("to-signup").click()
    patient_email = f"web-{uuid.uuid4().hex[:6]}@example.com"
    tid("email").fill(patient_email)
    tid("password").fill("CorrectHorse9!")
    tid("accept-boundary").check()
    shot(page, "sign-up")
    tid("auth-submit").click()
    tid("consent-image_storage").check()
    tid("consent-share_with_clinic").check()
    tid("consent-continue").click()
    tid("full-name").fill("Maria Clara Santos")
    tid("birth-year").fill("1998")
    tid("skin-type").select_option("oily")
    tid("fitzpatrick").select_option("4")
    tid("profile-save").click()
    expect(tid("new-check")).to_be_visible()
    tid("new-check").click()
    page.get_by_role("button", name="Breakouts and clogged pores").click()
    page.get_by_role("button", name="Oiliness and shine").click()
    shot(page, "patient-concerns")
    tid("next").click()
    tid("health-all-no").click()
    shot(page, "patient-health")
    tid("next").click()
    page.get_by_role("button", name="Fragrance").click()
    tid("next").click()
    tid("next").click()
    tid("sun-40").click()
    tid("sunscreen-sometimes").click()
    tid("next").click()
    for v in ("front", "left45", "right45"):
        tid(f"photo-{v}").set_input_files(os.path.join(args.images, f"{v}.jpg"))
        expect(tid(f"ok-{v}")).to_be_visible(timeout=20000)
    shot(page, "patient-photos")
    tid("submit-check").click()
    expect(page.locator("[data-testid^=route-]")).to_be_visible(timeout=30000)
    page.wait_for_timeout(800)
    shot(page, "patient-results")
    tid("tab-pm").click()
    with page.expect_download() as dl:
        tid("summary-share").click()
    dl.value.save_as(os.path.join(args.shots, "summary.pdf"))
    expect(tid("summary-msg")).to_contain_text("Sent to ICONIC")
    shot(page, "patient-shared")
    tid("nav-home").click()
    expect(page.get_by_role("link", name="Open")).to_be_visible()
    expect(tid("verify-banner")).to_be_visible()
    shot(page, "patient-home")

    # A second check shows progress against the first.
    run_check(page, ["Breakouts and clogged pores"])
    expect(tid("progress")).to_be_visible()
    tid("progress").scroll_into_view_if_needed()
    shot(page, "patient-progress")

    # Confirm the email from the emailed link; the banner goes away.
    page.goto(f"{args.app}/{emailed_link(patient_email, 'verify')}")
    expect(page.get_by_text(f"Thanks, {patient_email} is confirmed.")).to_be_visible(timeout=10000)
    shot(page, "verify-email")
    page.get_by_role("link", name="Continue").click()
    expect(tid("nav-home")).to_be_visible()
    page.reload()
    expect(tid("verify-banner")).to_have_count(0)

    # Unknown page.
    page.goto(f"{args.app}/#/no-such-page")
    expect(tid("not-found")).to_be_visible()
    shot(page, "not-found")
    sign_out(page)

    # --- Forgot password, reset from the emailed link, then change it in My account --------
    tid("to-forgot").click()
    tid("forgot-email").fill(patient_email)
    tid("forgot-submit").click()
    expect(page.get_by_text("If that email has an account")).to_be_visible()
    shot(page, "forgot-password")
    page.goto(f"{args.app}/{emailed_link(patient_email, 'reset')}")
    tid("new-password").fill("ResetPass!2026")
    tid("confirm-password").fill("ResetPass!2026")
    shot(page, "reset-password")
    tid("reset-submit").click()
    expect(page.get_by_text("Your password was changed.")).to_be_visible()
    tid("reset-to-login").click()
    login(page, patient_email, "CorrectHorse9!")
    expect(page.get_by_text("Wrong email or password.")).to_be_visible()
    login(page, patient_email, "ResetPass!2026")
    expect(tid("nav-account")).to_be_visible(timeout=10000)
    tid("nav-account").click()
    tid("current-password").fill("ResetPass!2026")
    tid("new-password").fill("ChangedPass!2026")
    tid("confirm-password").fill("ChangedPass!2026")
    tid("change-submit").click()
    expect(page.get_by_text("Password changed.")).to_be_visible()
    shot(page, "my-account")
    sign_out(page)

    # --- Clinic staff ---------------------------------------------------------------
    login(page, "staff.dev@example.com", "StaffPass!2026")
    expect(page.get_by_role("heading", name="Clinic inbox")).to_be_visible()
    expect(page.locator("[data-testid^=case-]").first).to_be_visible(timeout=10000)
    expect(tid("count-inbox")).to_be_visible()
    shot(page, "staff-inbox")
    page.locator("[data-testid^=case-]").first.click()
    expect(page.get_by_alt_text("Patient photo").first).to_be_visible(timeout=10000)
    tid("follow-booked").click()
    expect(page.get_by_text("Follow-up set to Booked.")).to_be_visible()
    tid("staff-note").fill("Called patient; consult booked for Saturday 10:00.")
    tid("save-note").click()
    expect(page.get_by_text("Note saved.")).to_be_visible()
    tid("mark-reviewed").click()
    expect(page.get_by_text("Marked reviewed.")).to_be_visible()
    shot(page, "staff-case")
    sign_out(page)

    # --- Dermatologist ---------------------------------------------------------------
    login(page, "derm.dev@example.com", "DermPass!2026")
    expect(page.get_by_role("heading", name="Review queue")).to_be_visible()
    expect(page.locator("[data-testid^=case-]").first).to_be_visible(timeout=10000)
    expect(tid("count-queue")).to_be_visible()
    shot(page, "derm-queue")
    page.locator("[data-testid^=case-]").first.click()
    expect(tid("submit-review")).to_be_visible()
    tid("derm-route-iconic_clinic").click()
    for btn in page.locator("[data-testid^=agree-][data-testid$=-yes]").all():
        btn.click()
    shot(page, "derm-review")
    tid("submit-review").click()
    expect(page.get_by_role("heading", name="Review queue")).to_be_visible()
    tid("nav-stats").click()
    expect(page.get_by_text("Cases reviewed")).to_be_visible()
    shot(page, "derm-stats")
    tid("nav-rules").click()
    tid("sign-off").click()
    expect(page.get_by_text("Signed off", exact=True)).to_be_visible(timeout=10000)
    shot(page, "derm-rules")
    sign_out(page)

    # --- Admin --------------------------------------------------------------------
    login(page, "admin.dev@example.com", "AdminPass!2026")
    expect(page.get_by_text("Signed off by a dermatologist")).to_be_visible(timeout=10000)
    shot(page, "admin-dashboard")
    tid("nav-admin/users").click()
    tid("add-user").click()
    email = f"nurse-{uuid.uuid4().hex[:5]}@example.com"
    tid("new-name").fill("Nurse Ana Reyes")
    tid("new-email").fill(email)
    tid("new-password").fill("NursePass!2026")
    tid("create-user").click()
    expect(page.get_by_text(f"Created {email}.")).to_be_visible()
    tid(f"user-{email}").get_by_test_id("disable").click()
    expect(page.get_by_text(f"{email} disabled.")).to_be_visible()
    shot(page, "admin-users")
    tid("nav-admin/catalog").click()
    expect(page.get_by_text("Sample Catalog Balancing Gel Cleanser")).to_be_visible()
    shot(page, "admin-catalog")
    tid("nav-admin/rules").click()
    tid("family-a").select_option("retinoids")
    tid("family-b").select_option("bha")
    tid("rationale").fill("Advised by consulting dermatologist: avoid same-night use")
    shot(page, "admin-rules")
    tid("nav-admin/models").click()
    expect(page.get_by_text("dl-stub-0.1.0").first).to_be_visible()
    shot(page, "admin-models")
    tid("nav-admin/audit").click()
    expect(page.get_by_role("cell", name="update user").first).to_be_visible(timeout=10000)
    shot(page, "admin-audit")
    sign_out(page)

    # A disabled account is refused.
    login(page, email, "NursePass!2026")
    expect(page.get_by_text("This account is disabled")).to_be_visible()
    shot(page, "disabled-login")

    # Five wrong passwords lock the account for 15 minutes, even with the right one after.
    for _ in range(5):
        login(page, patient_email, "not-my-password")
        expect(page.get_by_text("Wrong email or password.")).to_be_visible()
    login(page, patient_email, "ChangedPass!2026")
    expect(page.get_by_text("Too many wrong passwords")).to_be_visible()
    shot(page, "locked-login")

    print("page errors:", errors)
    b.close()
