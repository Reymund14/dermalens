"""End-to-end check of the staff, dermatologist and admin workspaces in the web build.

Run after web_flow.py (which leaves a shared summary behind):

    python e2e/roles_flow.py --app http://localhost:8081 --shots DIR
"""
import argparse
import os
import uuid

from playwright.sync_api import expect, sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--app", default="http://localhost:8081")
ap.add_argument("--shots", required=True)
args = ap.parse_args()
os.makedirs(args.shots, exist_ok=True)
n = 0
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def shot(page, name):
    global n
    n += 1
    page.wait_for_timeout(400)
    page.screenshot(path=os.path.join(args.shots, f"r{n:02d}-{name}.png"), full_page=False)


def login(page, email, pw):
    page.goto(args.app)
    page.evaluate("sessionStorage.clear()")
    page.goto(args.app)
    expect(page.get_by_text("Welcome to DermaLens")).to_be_visible(timeout=20000)
    page.get_by_text("I already have an account", exact=True).click()
    page.get_by_test_id("email").fill(email)
    page.get_by_test_id("password").fill(pw)
    page.get_by_test_id("auth-submit").click()


def back(page):
    """The app's header back arrow (the stack is in-app, not browser history)."""
    page.locator('a[aria-label$="back" i]:visible').last.click()
    page.wait_for_timeout(400)


def sign_out(page):
    page.get_by_test_id("sign-out").last.click()
    expect(page.get_by_text("Welcome to DermaLens")).to_be_visible(timeout=10000)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME if os.path.exists(CHROME) else None)
    page = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    page.on("dialog", lambda d: d.accept())
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    tid = page.get_by_test_id

    # --- Clinic staff ---------------------------------------------------------
    login(page, "staff.dev@example.com", "StaffPass!2026")
    expect(page.get_by_text("Clinic inbox")).to_be_visible(timeout=15000)
    expect(page.locator("[data-testid^=case-]").first).to_be_visible(timeout=10000)
    shot(page, "staff-inbox")
    page.locator("[data-testid^=case-]").first.click()
    expect(page.get_by_text("Shared summary")).to_be_visible()
    expect(page.get_by_role("img", name="Patient photo").first).to_be_visible(timeout=10000)
    shot(page, "staff-case")
    page.get_by_role("checkbox", name="Booked").last.click()
    expect(page.get_by_text("Follow-up set to Booked.")).to_be_visible()
    tid("mark-reviewed").click()
    expect(page.get_by_text("Marked reviewed.")).to_be_visible()
    page.mouse.wheel(0, 4000)
    shot(page, "staff-case-reviewed")
    back(page)
    expect(page.get_by_text("Clinic inbox")).to_be_visible()
    sign_out(page)

    # --- Dermatologist --------------------------------------------------------
    login(page, "derm.dev@example.com", "DermPass!2026")
    expect(page.get_by_text("Review queue")).to_be_visible(timeout=15000)
    expect(page.locator("[data-testid^=case-]").first).to_be_visible(timeout=10000)
    shot(page, "derm-queue")
    page.locator("[data-testid^=case-]").first.click()
    expect(page.get_by_text("Your review")).to_be_visible()
    page.get_by_text("Your review").scroll_into_view_if_needed()
    page.get_by_text("Dermatologist", exact=True).last.click()
    for yes in page.get_by_text("Yes", exact=True).all():
        yes.click()
    shot(page, "derm-case-review")
    tid("submit-review").click()
    expect(page.get_by_text("Review queue")).to_be_visible()
    tid("derm-stats").click()
    expect(page.get_by_text("Agreement with the app").last).to_be_visible()
    shot(page, "derm-stats")
    back(page)
    tid("derm-rules").click()
    expect(page.get_by_text("Rules and sign-off").last).to_be_visible()
    tid("sign-off").click()
    expect(page.get_by_text("Signed off", exact=True)).to_be_visible(timeout=10000)
    shot(page, "derm-rules-signed")
    back(page)
    sign_out(page)

    # --- Admin ----------------------------------------------------------------
    login(page, "admin.dev@example.com", "AdminPass!2026")
    expect(page.get_by_text("Signed off by a dermatologist")).to_be_visible(timeout=15000)
    shot(page, "admin-home")
    tid("admin-users").click()
    expect(page.get_by_text("Staff accounts").last).to_be_visible()
    email = f"nurse-{uuid.uuid4().hex[:5]}@example.com"
    tid("new-name").fill("Nurse Ana")
    tid("new-email").fill(email)
    tid("new-password").fill("NursePass!2026")
    tid("create-user").click()
    expect(page.get_by_text(f"Created {email}.")).to_be_visible()
    tid(f"user-{email}").click()
    tid("toggle-disabled").click()
    expect(page.get_by_text("Account disabled.")).to_be_visible()
    shot(page, "admin-users")
    back(page)
    tid("admin-catalog").click()
    expect(page.get_by_text("Product catalog").last).to_be_visible()
    shot(page, "admin-catalog")
    back(page)
    tid("admin-audit").click()
    expect(page.get_by_text("Audit log").last).to_be_visible()
    expect(page.get_by_text("update user · user").first).to_be_visible(timeout=10000)
    shot(page, "admin-audit")
    back(page)
    sign_out(page)

    # Disabled account cannot sign in.
    login(page, email, "NursePass!2026")
    expect(page.get_by_text("this account is disabled", exact=False)).to_be_visible(timeout=10000)
    shot(page, "disabled-login")

    print("page errors:", errors)
    b.close()
