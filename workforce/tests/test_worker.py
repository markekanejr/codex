from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone

from workforce.connectors.fake import OutcomeUnknown
from workforce.models import Delivery, Household, Membership, ScheduledJob, User
from workforce.services.jobs import claim_due, execute


class UnknownTransport:
    def send(self, delivery):
        raise OutcomeUnknown()


class WorkerTests(TransactionTestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Example")
        self.user = User.objects.create_user("worker@example.test", email="worker@example.test")
        Membership.objects.create(user=self.user, household=self.household, role="owner")
        self.now = timezone.now()

    def job(self, **kwargs):
        defaults = {
            "household": self.household,
            "principal": "shared",
            "kind": "briefing",
            "key": "test-job",
            "due_at": self.now,
            "payload": {"date": self.now.date().isoformat()},
        }
        defaults.update(kwargs)
        return ScheduledJob.objects.create(**defaults)

    def test_two_claimers_only_one_starts_same_job(self):
        job = self.job()
        barrier = Barrier(2)

        def claim():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                result = claim_due(self.now)
                return result.pk if result else None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: claim(), range(2)))
        self.assertEqual(results.count(job.pk), 1)
        self.assertEqual(results.count(None), 1)

    def test_expired_lease_before_submission_is_recovered(self):
        job = self.job(
            status="claimed", lease_token="old", lease_until=self.now - timedelta(seconds=1)
        )
        claimed = claim_due(self.now)
        self.assertEqual(claimed.pk, job.pk)
        self.assertNotEqual(claimed.lease_token, "old")

    def test_expired_lease_after_submission_is_not_retried(self):
        delivery = Delivery.objects.create(
            household=self.household,
            recipient=self.user,
            principal="shared",
            key="delivery",
            content="Example",
        )
        job = self.job(
            kind="delivery",
            payload={"delivery_id": delivery.pk},
            status="claimed",
            lease_token="old",
            lease_until=self.now - timedelta(seconds=1),
            submitted_at=self.now - timedelta(minutes=6),
        )
        self.assertIsNone(claim_due(self.now))
        job.refresh_from_db()
        delivery.refresh_from_db()
        self.assertEqual(job.status, "outcome_unknown")
        self.assertEqual(delivery.status, "outcome_unknown")

    def test_ambiguous_submission_records_unknown_outcome(self):
        delivery = Delivery.objects.create(
            household=self.household,
            recipient=self.user,
            principal="shared",
            key="delivery",
            content="Example",
        )
        job = self.job(kind="delivery", payload={"delivery_id": delivery.pk})
        claimed = claim_due(self.now)
        execute(claimed, self.now, transport=UnknownTransport())
        job.refresh_from_db()
        self.assertEqual(job.status, "outcome_unknown")
        self.assertIsNone(claim_due(self.now))

    def test_internal_failure_has_bounded_retries(self):
        job = self.job(kind="delivery", payload={"delivery_id": 999999})
        for _ in range(3):
            job.refresh_from_db()
            claimed = claim_due(job.due_at)
            execute(claimed, job.due_at)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.attempts, 3)

    def test_deleted_source_cancels_pending_snapshot(self):
        from workforce.models import PlanItem
        from workforce.services.briefings import record_ref

        item = PlanItem.objects.create(
            household=self.household, owner=self.user, audience="shared", title="Removed plan"
        )
        delivery = Delivery.objects.create(
            household=self.household,
            recipient=self.user,
            principal="shared",
            key="delete-test",
            content="Removed plan",
            refs=[record_ref(item)],
        )
        self.job(kind="delivery", payload={"delivery_id": delivery.pk})
        item.delete()
        claimed = claim_due(self.now)
        execute(claimed, self.now)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "canceled")
        self.assertEqual(delivery.content, "")
