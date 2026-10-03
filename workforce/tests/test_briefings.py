from datetime import date

from workforce.models import Delivery, PlanItem, ScheduledJob, SourceRecord
from workforce.services.briefings import build_briefing
from workforce.services.jobs import claim_due, execute, run_once
from workforce.services.scheduling import schedule_day
from workforce.tests.helpers import HouseholdCase


class BriefingTests(HouseholdCase):
    def setUp(self):
        self.shared = PlanItem.objects.create(
            household=self.household, owner=self.alex, title="Shared walk", audience="shared"
        )
        self.private = PlanItem.objects.create(
            household=self.household, owner=self.jamie, title="Surprise present"
        )
        self.day = date(2026, 5, 4)

    def test_shared_context_never_includes_private_records(self):
        content, refs = build_briefing(self.household, "shared", self.day)
        self.assertIn("Shared walk", content)
        self.assertNotIn("Surprise present", content)
        self.assertNotIn(self.private.pk, [ref["id"] for ref in refs if ref["type"] == "PlanItem"])
        private, _ = build_briefing(self.household, f"user:{self.jamie.pk}", self.day)
        self.assertIn("Surprise present", private)

    def test_duplicate_schedule_and_runs_make_one_delivery_per_recipient(self):
        schedule_day(self.household, self.day)
        due = ScheduledJob.objects.filter(kind="briefing").first().due_at
        run_once(due)
        run_once(due)
        self.assertEqual(Delivery.objects.count(), 4)
        self.assertEqual(Delivery.objects.filter(status="previewed").count(), 4)
        self.assertEqual(Delivery.objects.filter(principal="shared").count(), 2)

    def test_source_becoming_private_after_queueing_cancels_delivery(self):
        source = SourceRecord.objects.create(
            household=self.household, owner=self.alex, audience="shared", title="Source"
        )
        self.shared.source = source
        self.shared.save()
        schedule_day(self.household, self.day)
        job = ScheduledJob.objects.get(kind="briefing", principal="shared")
        claimed = claim_due(job.due_at)
        execute(claimed, job.due_at)
        # Select the shared briefing explicitly if another principal was first.
        if claimed.pk != job.pk:
            job.status = "claimed"
            job.lease_token = "test"
            job.save()
            execute(job, job.due_at)
        source.audience = "private"
        source.save()
        run_once(job.due_at)
        self.assertEqual(Delivery.objects.filter(principal="shared", status="canceled").count(), 2)
        self.assertTrue(all(not d.content for d in Delivery.objects.filter(principal="shared")))

    def test_history_rechecks_visibility_and_is_recipient_scoped(self):
        schedule_day(self.household, self.day)
        due = ScheduledJob.objects.first().due_at
        run_once(due)
        self.shared.audience = "private"
        self.shared.save()
        self.client.force_login(self.jamie)
        response = self.client.get("/briefing/")
        self.assertNotContains(response, "Shared walk")
        self.assertContains(response, "out of date")
        self.client.force_login(self.alex)
        self.assertNotContains(self.client.get("/briefing/?scope=private"), "Surprise present")

    def test_paused_household_has_no_processed_jobs(self):
        schedule_day(self.household, self.day)
        self.household.pause_outbound = True
        self.household.save()
        self.assertEqual(run_once(ScheduledJob.objects.first().due_at), 0)

    def test_stale_morning_is_skipped(self):
        from datetime import timedelta

        schedule_day(self.household, self.day)
        due = ScheduledJob.objects.first().due_at
        run_once(due + timedelta(hours=2))
        self.assertEqual(Delivery.objects.count(), 0)
        self.assertEqual(ScheduledJob.objects.filter(status="skipped").count(), 3)
