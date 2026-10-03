from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.utils import timezone

from workforce.connectors.fake import OutcomeUnknown
from workforce.models import ActionProposal, Approval, ScheduledJob, WorkflowPolicy
from workforce.services.actions import approve, dispatch_preview, queue, reject, submit
from workforce.services.jobs import claim_due, run_once
from workforce.services.spending import evaluate
from workforce.tests.helpers import HouseholdCase


class ActionTests(HouseholdCase):
    def setUp(self):
        WorkflowPolicy.objects.create(
            household=self.household,
            owner=self.alex,
            workflow="routine_appointment",
            vendor="Example provider",
            enabled=True,
        )

    def proposal(self, **kwargs):
        fields = {
            "household": self.household,
            "owner": self.alex,
            "audience": "shared",
            "title": "Routine appointment",
            "workflow": "routine_appointment",
            "vendor": "Example provider",
            "affected_person": self.alex,
            "subtotal_cents": 5000,
            "requested_at": timezone.now() + timedelta(days=1),
            "availability_confirmed": True,
            "quote_expires_at": timezone.now() + timedelta(hours=1),
        }
        fields.update(kwargs)
        return ActionProposal.objects.create(**fields)

    def test_all_in_price_boundaries(self):
        for subtotal, fees, expected in [
            (10000, 0, "ready"),
            (10001, 0, "awaiting_approval"),
            (9500, 800, "awaiting_approval"),
        ]:
            with self.subTest(subtotal=subtotal, fees=fees):
                proposal = self.proposal(subtotal_cents=subtotal, fees_cents=fees)
                result = submit(self.alex, proposal.pk)
                self.assertEqual(result.status, expected)

    def test_unknown_quote_and_availability_do_not_become_ready(self):
        for fields in [
            {"subtotal_cents": None},
            {"quote_expires_at": None},
            {"availability_confirmed": False},
            {"requested_at": None},
            {"quote_expires_at": timezone.now() - timedelta(seconds=1)},
        ]:
            self.assertEqual(
                submit(self.alex, self.proposal(**fields).pk).status, "needs_information"
            )

    def test_new_vendor_and_recurring_commitment_require_review(self):
        self.assertEqual(
            submit(self.alex, self.proposal(vendor="New provider").pk).status, "awaiting_approval"
        )
        self.assertEqual(
            submit(self.alex, self.proposal(recurring=True).pk).status, "awaiting_approval"
        )

    def test_related_charges_cannot_evade_threshold(self):
        first = self.proposal(subtotal_cents=6000)
        second = self.proposal(subtotal_cents=6000, purchase_group=first.purchase_group)
        self.assertEqual(evaluate(first)[0], "unsupported")
        self.assertEqual(evaluate(second)[0], "unsupported")

    def test_other_persons_commitment_stays_manual(self):
        proposal = self.proposal(affected_person=self.jamie)
        self.assertEqual(submit(self.alex, proposal.pk).status, "needs_information")

    def test_only_pricing_approver_can_approve(self):
        proposal = self.proposal(subtotal_cents=14000)
        submit(self.alex, proposal.pk)
        with self.assertRaises(PermissionDenied):
            approve(self.jamie, proposal.pk, proposal.revision)
        approved = approve(self.alex, proposal.pk, proposal.revision)
        self.assertEqual(approved.status, "ready")

    def test_pricing_authority_does_not_reveal_private_partner_action(self):
        proposal = self.proposal(
            owner=self.jamie, affected_person=self.jamie, audience="private", subtotal_cents=14000
        )
        submit(self.jamie, proposal.pk)
        with self.assertRaises(ActionProposal.DoesNotExist):
            approve(self.alex, proposal.pk, proposal.revision)
        self.client.force_login(self.alex)
        self.assertEqual(self.client.get(f"/review/{proposal.pk}/").status_code, 404)

    def test_changed_quote_invalidates_exact_approval(self):
        proposal = self.proposal(subtotal_cents=14000)
        submit(self.alex, proposal.pk)
        approve(self.alex, proposal.pk, proposal.revision)
        proposal.refresh_from_db()
        proposal.subtotal_cents = 15000
        proposal.terms = "Different cancellation conditions"
        proposal.save()
        with self.assertRaises(ValidationError):
            queue(self.alex, proposal.pk)

    def test_revoked_approver_invalidates_approval(self):
        proposal = self.proposal(subtotal_cents=14000)
        submit(self.alex, proposal.pk)
        approve(self.alex, proposal.pk, proposal.revision)
        member = self.alex.membership
        member.pricing_approver = False
        member.save()
        with self.assertRaises(ValidationError):
            queue(self.alex, proposal.pk)

    def test_repeat_approval_and_queue_are_idempotent(self):
        proposal = self.proposal(subtotal_cents=14000)
        submit(self.alex, proposal.pk)
        approve(self.alex, proposal.pk, proposal.revision)
        approve(self.alex, proposal.pk, proposal.revision)
        queue(self.alex, proposal.pk)
        queue(self.alex, proposal.pk)
        self.assertEqual(Approval.objects.count(), 1)
        self.assertEqual(ScheduledJob.objects.filter(kind="action").count(), 1)
        run_once()
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "succeeded")
        self.assertTrue(proposal.receipt.startswith("simulated:"))

    def test_rejection_retires_pending_execution(self):
        proposal = self.proposal()
        submit(self.alex, proposal.pk)
        queue(self.alex, proposal.pk)
        reject(self.alex, proposal.pk)
        run_once()
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "rejected")
        self.assertEqual(proposal.receipt, "")

    def test_changed_queued_proposal_is_not_executed(self):
        proposal = self.proposal()
        submit(self.alex, proposal.pk)
        queue(self.alex, proposal.pk)
        proposal.refresh_from_db()
        proposal.terms = "Changed"
        proposal.save()
        run_once()
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "draft")
        self.assertEqual(proposal.receipt, "")

    def test_unknown_external_outcome_is_not_retried(self):
        class UnknownConnector:
            def execute(self, proposal):
                raise OutcomeUnknown()

        proposal = self.proposal()
        submit(self.alex, proposal.pk)
        queue(self.alex, proposal.pk)
        job = claim_due()
        result = dispatch_preview(job, timezone.now(), connector=UnknownConnector())
        self.assertEqual(result, "outcome_unknown")
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "outcome_unknown")

    def test_get_and_missing_csrf_cannot_approve(self):
        proposal = self.proposal(subtotal_cents=14000)
        submit(self.alex, proposal.pk)
        self.client.force_login(self.alex)
        self.assertEqual(
            self.client.get(f"/review/{proposal.pk}/decide/?operation=approve").status_code, 405
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.alex)
        self.assertEqual(
            csrf_client.post(
                f"/review/{proposal.pk}/decide/",
                {"operation": "approve", "revision": proposal.revision},
            ).status_code,
            403,
        )
        self.assertEqual(Approval.objects.count(), 0)

    def test_action_form_preserves_unknown_price(self):
        self.client.force_login(self.alex)
        response = self.client.post(
            "/review/new/",
            {
                "title": "Gift idea",
                "audience": "private",
                "workflow": "gift",
                "vendor": "Example shop",
                "affected_person": self.alex.pk,
                "currency": "USD",
                "fees": "2.35",
            },
        )
        self.assertEqual(response.status_code, 302)
        proposal = ActionProposal.objects.get(title="Gift idea")
        self.assertIsNone(proposal.subtotal_cents)
        self.assertEqual(proposal.fees_cents, 235)
