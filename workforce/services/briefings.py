from datetime import timedelta
from zoneinfo import ZoneInfo

from workforce.models import Membership, PlanItem, Routine, SourceRecord, Trip, TripSegment
from workforce.services.access import audience_scope, source_visible

REF_MODELS = {
    model.__name__: model for model in (PlanItem, Routine, SourceRecord, Trip, TripSegment)
}


def record_ref(record):
    return {"type": type(record).__name__, "id": record.pk, "revision": record.revision}


def refs_valid(household_id, principal, refs):
    for ref in refs:
        model = REF_MODELS.get(ref.get("type"))
        if not model:
            return False
        record = model.objects.filter(pk=ref["id"], revision=ref["revision"]).first()
        if not record:
            return False
        owned = record.trip if model is TripSegment else record
        if owned.household_id != household_id:
            return False
        if principal == "shared":
            if owned.audience != "shared":
                return False
        elif owned.audience != "shared" and principal != f"user:{owned.owner_id}":
            return False
        if isinstance(record, PlanItem) and not source_visible(record, principal):
            return False
    return True


def travel_preparation(trip):
    if (
        trip.status == "canceled"
        or trip.airport_buffer_minutes is None
        or trip.ground_minutes is None
    ):
        return []
    steps = []
    for flight in trip.segments.filter(kind="flight", verification="confirmed"):
        if not flight.start_at or not flight.origin or not flight.destination:
            continue
        local_start = flight.start_at.astimezone(ZoneInfo(flight.timezone))
        pack_at = local_start.replace(hour=19, minute=0, second=0, microsecond=0) - timedelta(
            days=1
        )
        leave_at = flight.start_at - timedelta(
            minutes=trip.airport_buffer_minutes + trip.ground_minutes
        )
        refs = [record_ref(trip), record_ref(flight)]
        steps.extend(
            [
                ("Packing preparation (suggested evening time)", pack_at, refs),
                ("Leave for the airport using your configured buffers", leave_at, refs),
            ]
        )
    return steps


def build_briefing(household, principal, day):
    from workforce.services.scheduling import routine_occurs

    lines = [f"Your morning overview · {day:%A, %B %d}", ""]
    refs = []
    zone = ZoneInfo(household.timezone)
    for item in (
        audience_scope(PlanItem, household.pk, principal)
        .exclude(status__in=["done", "canceled"])
        .select_related("source")
    ):
        if not source_visible(item, principal):
            continue
        instant = item.start_at or item.due_at
        if instant and instant.astimezone(zone).date() not in (day, day + timedelta(days=1)):
            continue
        timing = instant.astimezone(zone).strftime("%a %-I:%M %p") if instant else "Time not set"
        lines.append(f"• {item.title} — {timing} ({item.get_status_display()})")
        refs.append(record_ref(item))
        if item.source_id:
            refs.append(record_ref(item.source))
    for routine in audience_scope(Routine, household.pk, principal):
        if routine_occurs(routine, day):
            lines.append(f"• {routine.title} — {routine.local_time:%H:%M} ({routine.timezone})")
            refs.append(record_ref(routine))
        if (
            routine_occurs(routine, day + timedelta(days=1))
            and routine.local_time < household.briefing_time
        ):
            lines.append(
                f"• Prepare this evening: {routine.title} tomorrow at {routine.local_time:%H:%M}"
            )
            refs.append(record_ref(routine))
    for trip in audience_scope(Trip, household.pk, principal).exclude(status="canceled"):
        if trip.departure_date and not day <= trip.departure_date <= day + timedelta(days=7):
            continue
        refs.append(record_ref(trip))
        refs.extend(record_ref(segment) for segment in trip.segments.all())
        missing = trip.missing_details
        lines.append(
            f"• {trip.title}: {'still to confirm: ' + ', '.join(missing) if missing else 'flight timing confirmed'}"
        )
        for step, due, _ in travel_preparation(trip):
            if day <= due.astimezone(zone).date() <= day + timedelta(days=1):
                lines.append(f"  {step}: {due.astimezone(zone):%a %H:%M}")
    if len(lines) == 2:
        lines.append("A clear day. Leave some room for rest.")
    lines.extend(["", "Preview only — no messages, purchases, or bookings have been sent."])
    return "\n".join(lines), refs


def recipients(household, principal):
    members = Membership.objects.filter(
        household=household, notifications=True, user__is_active=True
    )
    if principal != "shared":
        members = members.filter(user_id=int(principal.removeprefix("user:")))
    return list(members.values_list("user_id", flat=True))
