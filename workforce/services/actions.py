from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from workforce.connectors.fake import OutcomeUnknown
from workforce.models import ActionProposal, Approval, AuditEvent, ScheduledJob
from workforce.services.access import membership, scoped
from workforce.services.spending import evaluate, fingerprint


def audit(proposal, event, actor=None):
    AuditEvent.objects.create(
        household=proposal.household,
        actor=actor,
        principal="shared" if proposal.audience == "shared" else f"user:{proposal.owner_id}",
        object_id=proposal.pk,
        event=event,
    )


def locked_proposal(actor, pk):
    return scoped(ActionProposal, actor).select_for_update().get(pk=pk)


@transaction.atomic
def submit(actor, pk):
    proposal = locked_proposal(actor, pk)
    if proposal.owner_id != actor.pk:
        raise PermissionDenied("Only the plan owner can submit it.")
    if proposal.status not in ("draft", "needs_information", "awaiting_approval"):
        return proposal
    decision, reason = evaluate(proposal)
    status = {"allowed": "ready", "approval_required": "awaiting_approval"}.get(
        decision, "needs_information"
    )
    ActionProposal.objects.filter(pk=pk).update(
        status=status, ready_by="policy" if decision == "allowed" else ""
    )
    audit(proposal, status, actor)
    proposal.refresh_from_db()
    return proposal


@transaction.atomic
def approve(actor, pk, revision):
    proposal = locked_proposal(actor, pk)
    if not membership(actor).pricing_approver:
        raise PermissionDenied("Only the designated pricing approver can approve.")
    if proposal.revision != revision:
        raise ValidationError("The proposal changed. Review the current version.")
    if (
        proposal.status == "ready"
        and Approval.objects.filter(
            proposal=proposal, revision=revision, fingerprint=fingerprint(proposal)
        ).exists()
    ):
        return proposal
    if proposal.status != "awaiting_approval":
        raise ValidationError("This proposal is not awaiting approval.")
    decision, reason = evaluate(proposal, honor_approval=False)
    if decision in ("unsupported", "information_required"):
        raise ValidationError(reason)
    Approval.objects.create(
        proposal=proposal, actor=actor, revision=revision, fingerprint=fingerprint(proposal)
    )
    ActionProposal.objects.filter(pk=pk).update(status="ready", ready_by="human")
    audit(proposal, "approved", actor)
    proposal.refresh_from_db()
    return proposal


@transaction.atomic
def reject(actor, pk):
    proposal = locked_proposal(actor, pk)
    if actor.pk != proposal.owner_id and not membership(actor).pricing_approver:
        raise PermissionDenied
    if proposal.status in ("executing", "succeeded", "outcome_unknown"):
        raise ValidationError("An already-submitted action cannot be rejected.")
    ActionProposal.objects.filter(pk=pk).update(status="rejected")
    Approval.objects.filter(proposal=proposal).update(decision="rejected")
    ScheduledJob.objects.filter(kind="action", payload__proposal_id=pk, status="pending").update(
        status="canceled"
    )
    audit(proposal, "rejected", actor)


@transaction.atomic
def queue(actor, pk):
    proposal = locked_proposal(actor, pk)
    if actor.pk != proposal.owner_id and not membership(actor).pricing_approver:
        raise PermissionDenied
    if proposal.status == "queued":
        return
    if proposal.status != "ready":
        raise ValidationError("This proposal is not ready.")
    decision, reason = evaluate(proposal)
    if decision != "allowed":
        raise ValidationError(reason)
    ScheduledJob.objects.get_or_create(
        key=f"action:{pk}:{proposal.revision}",
        defaults={
            "household": proposal.household,
            "principal": "shared" if proposal.audience == "shared" else f"user:{proposal.owner_id}",
            "kind": "action",
            "due_at": timezone.now(),
            "payload": {
                "proposal_id": pk,
                "revision": proposal.revision,
                "fingerprint": fingerprint(proposal),
            },
        },
    )
    ActionProposal.objects.filter(pk=pk).update(status="queued")
    audit(proposal, "queued", actor)


def dispatch_preview(job, now, connector=None):
    from workforce.connectors.fake import PreviewActionConnector

    with transaction.atomic():
        proposal = ActionProposal.objects.select_for_update().get(
            pk=job.payload["proposal_id"], household_id=job.household_id
        )
        decision, _ = evaluate(proposal, now)
        if (
            proposal.status != "queued"
            or proposal.revision != job.payload["revision"]
            or fingerprint(proposal) != job.payload["fingerprint"]
            or decision != "allowed"
        ):
            if proposal.status == "queued":
                ActionProposal.objects.filter(pk=proposal.pk).update(status="draft", ready_by="")
            return "canceled"
        # Only the lease owner can cross the submission boundary.
        if not ScheduledJob.objects.filter(
            pk=job.pk, status="claimed", lease_token=job.lease_token
        ).update(submitted_at=now):
            return "canceled"
        ActionProposal.objects.filter(pk=proposal.pk).update(status="executing")
    try:
        receipt = (connector or PreviewActionConnector()).execute(proposal)
    except OutcomeUnknown:
        ActionProposal.objects.filter(pk=proposal.pk).update(status="outcome_unknown")
        return "outcome_unknown"
    except Exception:
        ActionProposal.objects.filter(pk=proposal.pk).update(status="outcome_unknown")
        return "outcome_unknown"
    ActionProposal.objects.filter(pk=proposal.pk).update(status="succeeded", receipt=receipt)
    audit(proposal, "simulated_completion")
    return "succeeded"
