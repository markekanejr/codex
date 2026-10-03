import secrets
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from workforce.connectors.fake import OutcomeUnknown, PreviewTransport
from workforce.models import Delivery, ScheduledJob
from workforce.services.briefings import build_briefing, recipients, refs_valid


@transaction.atomic
def claim_due(now=None):
    now = now or timezone.now()
    expired = list(
        ScheduledJob.objects.select_for_update(skip_locked=True).filter(
            status="claimed", lease_until__lt=now
        )
    )
    for job in expired:
        job.status = "outcome_unknown" if job.submitted_at else "pending"
        job.lease_token = ""
        job.error_code = "lease_expired_after_submission" if job.submitted_at else ""
        job.save(update_fields=["status", "lease_token", "error_code"])
        if job.submitted_at and job.kind == "delivery":
            Delivery.objects.filter(pk=job.payload["delivery_id"]).update(status="outcome_unknown")
        if job.submitted_at and job.kind == "action":
            from workforce.models import ActionProposal

            ActionProposal.objects.filter(pk=job.payload["proposal_id"]).update(
                status="outcome_unknown"
            )
    job = (
        ScheduledJob.objects.select_for_update(skip_locked=True)
        .filter(
            status="pending",
            due_at__lte=now,
        )
        .filter(Q(household__pause_outbound=False))
        .order_by("due_at", "id")
        .first()
    )
    if job:
        job.status = "claimed"
        job.lease_token = secrets.token_hex(16)
        job.lease_until = now + timedelta(minutes=5)
        job.attempts += 1
        job.save(update_fields=["status", "lease_token", "lease_until", "attempts"])
    return job


def finish(job, status, error_code=""):
    ScheduledJob.objects.filter(pk=job.pk, status="claimed", lease_token=job.lease_token).update(
        status=status, error_code=error_code, lease_until=None
    )


@transaction.atomic
def enqueue_deliveries(job, content, refs, now):
    for user_id in recipients(job.household, job.principal):
        key = f"{job.key}:email:{user_id}"
        delivery, _ = Delivery.objects.get_or_create(
            key=key,
            defaults={
                "household": job.household,
                "recipient_id": user_id,
                "principal": job.principal,
                "content": content,
                "refs": refs,
            },
        )
        ScheduledJob.objects.get_or_create(
            key=f"deliver:{delivery.pk}",
            defaults={
                "household": job.household,
                "principal": job.principal,
                "kind": "delivery",
                "due_at": now,
                "payload": {"delivery_id": delivery.pk},
            },
        )


def execute(job, now=None, transport=None):
    now = now or timezone.now()
    job.household.refresh_from_db()
    if job.household.pause_outbound:
        finish(job, "pending")
        return
    try:
        if job.kind in ("briefing", "reminder"):
            if now - job.due_at > timedelta(minutes=90):
                finish(job, "skipped", "catchup_window_expired")
                return
            if job.kind == "briefing":
                content, refs = build_briefing(
                    job.household, job.principal, date.fromisoformat(job.payload["date"])
                )
            else:
                refs = job.payload["refs"]
                if not refs_valid(job.household_id, job.principal, refs):
                    finish(job, "canceled", "record_changed")
                    return
                content = f"{job.payload['purpose']}\n{job.payload['title']}\nPreview only."
            enqueue_deliveries(job, content, refs, now)
            finish(job, "succeeded")
        elif job.kind == "delivery":
            delivery = Delivery.objects.get(pk=job.payload["delivery_id"], household=job.household)
            if delivery.recipient_id not in recipients(
                job.household, job.principal
            ) or not refs_valid(job.household_id, job.principal, delivery.refs):
                Delivery.objects.filter(pk=delivery.pk).update(status="canceled", content="")
                finish(job, "canceled", "record_or_recipient_changed")
                return
            updated = ScheduledJob.objects.filter(
                pk=job.pk, status="claimed", lease_token=job.lease_token
            ).update(submitted_at=now)
            if not updated:
                return
            provider_ref = (transport or PreviewTransport()).send(delivery)
            Delivery.objects.filter(pk=delivery.pk).update(
                status="previewed", previewed_at=now, provider_ref=provider_ref
            )
            finish(job, "succeeded")
        elif job.kind == "action":
            from workforce.services.actions import dispatch_preview

            finish(job, dispatch_preview(job, now))
        else:
            finish(job, "failed", "unsupported_job")
    except OutcomeUnknown:
        if job.kind == "delivery":
            Delivery.objects.filter(pk=job.payload["delivery_id"]).update(status="outcome_unknown")
        finish(job, "outcome_unknown", "submission_outcome_unknown")
    except Exception:
        # Error metadata deliberately omits private source text and exception bodies.
        current = ScheduledJob.objects.get(pk=job.pk)
        if current.submitted_at:
            if job.kind == "delivery":
                Delivery.objects.filter(pk=job.payload["delivery_id"]).update(
                    status="outcome_unknown"
                )
            finish(job, "outcome_unknown", "submission_outcome_unknown")
        elif job.attempts < 3:
            ScheduledJob.objects.filter(pk=job.pk, lease_token=job.lease_token).update(
                status="pending",
                due_at=now + timedelta(seconds=30 * job.attempts),
                error_code="retryable_internal_error",
            )
        else:
            finish(job, "failed", "internal_error")


def run_once(now=None, limit=100):
    count = 0
    while count < limit:
        job = claim_due(now)
        if not job:
            break
        execute(job, now)
        count += 1
    return count
