"""End-to-end check of the mobile app's web build against a running API.

    python e2e/web_flow.py --app http://localhost:8081 --images DIR --shots DIR

DIR must hold front.jpg, left45.jpg and right45.jpg (see dermalens_inference.testing.synth_face).
"""
import argparse
import os
import time
import uuid

from playwright.sync_api import expect, sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("--app", default="http://localhost:8081")
ap.add_argument("--images", required=True)
ap.add_argument("--shots", required=True)
args = ap.parse_args()
os.makedirs(args.shots, exist_ok=True)
n = 0


def shot(page, name):
    global n
    n += 1
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(args.shots, f"{n:02d}-{name}.png"))


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
                          if os.path.exists("/opt/pw-browsers/chromium-1194/chrome-linux/chrome") else None)
    page = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    page.on("dialog", lambda d: d.accept())
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(args.app)

    tid = page.get_by_test_id
    expect(page.get_by_text("Welcome to DermaLens")).to_be_visible(timeout=20000)
    shot(page, "welcome")
    tid("get-started").click()
    expect(page.get_by_text("Before you start")).to_be_visible()
    tid("boundary-ack").click()
    shot(page, "boundary")
    tid("boundary-continue").click()

    tid("email").fill(f"e2e-{uuid.uuid4().hex[:6]}@example.com")
    tid("password").fill("CorrectHorse9!")
    tid("auth-submit").click()
    expect(page.get_by_text("Your privacy choices")).to_be_visible()
    tid("consent-share_with_clinic").click()
    page.wait_for_timeout(500)
    shot(page, "consent")
    tid("consent-continue").click()

    tid("full-name").fill("Maria Clara Santos")
    tid("birth-year").fill("1998")
    page.get_by_text("Oily", exact=True).click()
    page.get_by_text("Rarely burns", exact=True).click()
    shot(page, "profile")
    tid("profile-save").click()

    expect(tid("new-assessment")).to_be_visible()
    shot(page, "home-empty")
    tid("new-assessment").click()
    page.get_by_text("Breakouts and clogged pores", exact=True).click()
    page.get_by_text("Oiliness and shine", exact=True).click()
    shot(page, "intake-concerns")
    tid("concerns-next").click()

    expect(page.get_by_text("A quick health check")).to_be_visible()
    tid("health-all-no").click()
    shot(page, "intake-health")
    tid("health-next").click()

    page.get_by_text("Fragrance", exact=True).click()
    tid("allergen-search").fill("salicy")
    page.get_by_text("Salicylic Acid", exact=True).first.click()
    shot(page, "intake-allergies")
    tid("allergies-next").click()
    shot(page, "intake-routine")
    tid("routine-next").click()
    page.get_by_text("1–3 hours", exact=True).click()
    page.get_by_text("Sometimes", exact=True).click()
    shot(page, "intake-lifestyle")
    tid("lifestyle-next").click()

    expect(page.get_by_text("Taking good photos")).to_be_visible()
    shot(page, "capture-guide")
    tid("guide-start").click()
    for view, title in (("front", "Front view"), ("left45", "Left side"), ("right45", "Right side")):
        expect(page.get_by_text(title, exact=True).last).to_be_visible(timeout=15000)
        with page.expect_file_chooser() as fc:
            tid("pick-photo").last.click()
        fc.value.set_files(os.path.join(args.images, f"{view}.jpg"))
        if view == "front":
            page.wait_for_timeout(600)
            shot(page, "capture-front")

    expect(page.get_by_text("Review your photos")).to_be_visible(timeout=20000)
    shot(page, "review")
    tid("review-submit").click()

    expect(page.get_by_text("Your results")).to_be_visible(timeout=30000)
    page.wait_for_timeout(500)
    shot(page, "results")
    route = page.locator("[data-testid^=route-]").first.get_attribute("data-testid")
    print("route:", route)

    if page.get_by_test_id("see-routine").count():
        tid("see-routine").click()
    else:
        tid("cta").click()
    expect(page.get_by_text("Your routine").or_(page.get_by_text("Gentle basics"))).to_be_visible()
    shot(page, "routine-am")
    if tid("tab-pm").count():
        tid("tab-pm").click()
        shot(page, "routine-pm")
    tid("to-summary").click()
    expect(page.get_by_text("Pre-screening summary", exact=True)).to_be_visible()
    with page.expect_download() as dl:
        tid("summary-pdf").click()
    path = os.path.join(args.shots, "summary.pdf")
    dl.value.save_as(path)
    tid("summary-share").click()
    expect(tid("summary-done")).to_be_visible(timeout=20000)
    shot(page, "summary-shared")
    print("pdf bytes:", os.path.getsize(path))
    print("page errors:", errors)
    b.close()
