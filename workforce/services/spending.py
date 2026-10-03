import hashlib
import json

from django.utils import timezone

from workforce.models import Approval, WorkflowPolicy


def fingerprint(proposal):
    data = {
        "id": proposal.pk,
        "revision": proposal.revision,
        "household": proposal.household_id,
        "owner": proposal.owner_id,
        "audience": proposal.audience,
        "title": proposal.title,
        "workflow": proposal.workflow,
        "vendor": proposal.vendor,
        "affected_person": proposal.affected_person_id,
        "subtotal": proposal.subtotal_cents,
        "fees": proposal.fees_cents,
        "currency": proposal.currency,
        "terms": proposal.terms,
        "requested_at": str(proposal.requested_at),
        "recurring": proposal.recurring,
        "availability_confirmed": proposal.availability_confirmed,
        "quote_expires_at": str(proposal.quote_expires_at),
        "purchase_group": str(proposal.purchase_group),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def evaluate(proposal, now=None, honor_approval=True):
    now = now or timezone.now()
    if proposal.currency != "USD":
        return "unsupported", "Only USD quotes are supported in this preview."
    if proposal.total_cents is None:
        return "information_required", "The full price is unknown."
    if not proposal.quote_expires_at:
        return "information_required", "Set a quote expiry before proceeding."
    if proposal.quote_expires_at <= now:
        return "information_required", "This quote has expired."
    if proposal.affected_person_id != proposal.owner_id:
        return "unsupported", "This affects another person's commitment; keep it manual."
    if proposal.workflow == "routine_appointment" and (
        not proposal.requested_at or not proposal.availability_confirmed
    ):
        return "information_required", "Confirm an available appointment slot."
    if (
        type(proposal)
        .objects.filter(household=proposal.household, purchase_group=proposal.purchase_group)
        .exclude(pk=proposal.pk)
        .exclude(status__in=["rejected", "canceled"])
        .exists()
    ):
        return "unsupported", "Combine related charges into one complete quote."
    if (
        honor_approval
        and Approval.objects.filter(
            proposal=proposal,
            revision=proposal.revision,
            fingerprint=fingerprint(proposal),
            decision="approved",
            actor__is_active=True,
            actor__membership__household=proposal.household,
            actor__membership__pricing_approver=True,
        ).exists()
    ):
        return "allowed", "Approved exact proposal."
    policy = WorkflowPolicy.objects.filter(
        household=proposal.household,
        owner=proposal.owner,
        workflow=proposal.workflow,
        vendor=proposal.vendor,
        enabled=True,
    ).exists()
    if not policy:
        return "approval_required", "This vendor/workflow has no enabled routine policy."
    if proposal.recurring:
        return "approval_required", "A new recurring commitment needs review."
    if proposal.total_cents > proposal.household.auto_limit_cents:
        return "approval_required", "The all-in price exceeds the automatic spending limit."
    return "allowed", "Eligible routine within the configured all-in price limit."
