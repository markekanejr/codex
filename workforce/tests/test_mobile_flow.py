from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import close_old_connections
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from workforce.models import Household, Membership, User
from workforce.services.jobs import run_once


class MobileFlowTests(StaticLiveServerTestCase):
    def test_invited_account_planning_preview_and_approval(self):
        household = Household.objects.create(name="Example household")
        user = User.objects.create_user(
            "alex@example.test", email="alex@example.test", password="Example-browser-pass-438"
        )
        Membership.objects.create(
            household=household, user=user, role="owner", pricing_approver=True
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/chromium", args=["--no-sandbox"]
            )
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(self.live_server_url + "/accounts/login/")
            page.get_by_label("Email").fill(user.email)
            page.get_by_label("Password").fill("Example-browser-pass-438")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.get_by_role("heading", name="A little more room for life.")).to_be_visible()
            for title, audience in [("Weekend walk", "shared"), ("Private gift idea", "private")]:
                page.goto(self.live_server_url + "/plans/new/")
                page.get_by_label("Title").fill(title)
                page.get_by_label("Audience").select_option(audience)
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Plans, with room to breathe.")
                ).to_be_visible()
            page.goto(self.live_server_url + "/briefing/?scope=shared")
            expect(page.locator("pre").first).to_contain_text("Weekend walk")
            expect(page.locator("pre").first).not_to_contain_text("Private gift idea")
            self.assertLessEqual(page.evaluate("document.body.scrollWidth"), 390)
            page.screenshot(path="/tmp/workforce-mobile-preview.png", full_page=True)
            page.goto(self.live_server_url + "/review/new/")
            page.get_by_label("Title").fill("Example purchase")
            page.get_by_label("Audience").select_option("shared")
            page.get_by_label("Workflow").select_option("gift")
            page.get_by_label("Vendor").fill("Example shop")
            page.get_by_label("Quoted price (USD)").fill("160.00")
            page.get_by_label("Taxes and fees (USD)").fill("0.00")
            page.get_by_label("Quote expires at").fill(
                timezone.localtime(timezone.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
            )
            page.get_by_role("button", name="Save", exact=True).click()
            page.get_by_role("button", name="Check proposal", exact=True).click()
            page.get_by_role("button", name="Approve this exact proposal", exact=True).click()
            page.get_by_role("button", name="Queue simulated action", exact=True).click()

            def process_jobs():
                close_old_connections()
                try:
                    return run_once()
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(process_jobs).result()
            page.reload()
            expect(page.get_by_text("Simulated completion", exact=False)).to_be_visible()
            browser.close()
