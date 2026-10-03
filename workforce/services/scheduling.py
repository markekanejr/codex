from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from workforce.models import Membership, PlanItem, Routine, ScheduledJob, Trip
from workforce.services.briefings import record_ref, refs_valid, travel_preparation


def local_instant(day, local_time, zone_name):
    """First fold, or next valid minute after a nonexistent wall time."""
    zone = ZoneInfo(zone_name)
    naive = datetime.combine(day, local_time)
    for _ in range(181):
        candidate = naive.replace(tzinfo=zone, fold=0)
        instant = candidate.astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == naive:
            return instant
        naive += timedelta(minutes=1)
    raise ValueError("Local time could not be resolved.")


def routine_occurs(routine, day):
    return (
        routine.active
        and day >= routine.active_from
        and (not routine.active_until or day <= routine.active_until)
        and (routine.rule == "daily" or day.weekday() in routine.weekdays)
    )


def put_job(household, principal, kind, key, due_at, payload):
    job, created = ScheduledJob.objects.get_or_create(
        key=key,
        defaults={
            "household": household,
            "principal": principal,
            "kind": kind,
            "due_at": due_at,
            "payload": payload,
        },
    )
    if not created and job.status == "pending":
        job.due_at, job.payload = due_at, payload
        job.save(update_fields=["due_at", "payload"])
    return job


def schedule_day(household, day):
    principals = ["shared"] + [
        f"user:{pk}"
        for pk in Membership.objects.filter(household=household).values_list("user_id", flat=True)
    ]
    for principal in principals:
        put_job(
            household,
            principal,
            "briefing",
            f"brief:{household.pk}:{principal}:{day}",
            local_instant(day, household.briefing_time, household.timezone),
            {"date": day.isoformat()},
        )
    # Early plans need a preparation note the prior evening, before the morning overview.
    for model in (PlanItem, Routine):
        for item in model.objects.filter(household=household):
            if model is Routine:
                if not routine_occurs(item, day):
                    continue
                start = local_instant(day, item.local_time, item.timezone)
            else:
                if item.status != "confirmed" or not item.start_at:
                    continue
                start = item.start_at
            local_start = start.astimezone(ZoneInfo(household.timezone))
            if local_start.date() != day or local_start.time() >= household.briefing_time:
                continue
            principal = "shared" if item.audience == "shared" else f"user:{item.owner_id}"
            refs = [record_ref(item)]
            if model is PlanItem and item.source_id:
                refs.append(record_ref(item.source))
            if not refs_valid(household.pk, principal, refs):
                continue
            due = local_instant(
                day - timedelta(days=1), datetime.min.replace(hour=19).time(), household.timezone
            )
            put_job(
                household,
                principal,
                "reminder",
                f"early:{model.__name__}:{item.pk}:{item.revision}:{day}",
                due,
                {
                    "refs": refs,
                    "title": item.title,
                    "purpose": "Prepare this evening for tomorrow's early plan.",
                },
            )
    for trip in Trip.objects.filter(household=household).exclude(status="canceled"):
        principal = "shared" if trip.audience == "shared" else f"user:{trip.owner_id}"
        for step, due, refs in travel_preparation(trip):
            if due.astimezone(ZoneInfo(household.timezone)).date() == day:
                put_job(
                    household,
                    principal,
                    "reminder",
                    f"trip:{trip.pk}:{trip.revision}:{step}:{due.isoformat()}",
                    due,
                    {"refs": refs, "title": trip.title, "purpose": step},
                )
